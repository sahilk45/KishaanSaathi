import os
import logging
from typing import AsyncIterator
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from chatbot.graph import agrisage_graph, llm_model
from chatbot.memory import ensure_thread_exists, apply_memory_pressure, save_turn
from chatbot.db import get_pool

logger = logging.getLogger(__name__)

async def run_agent(
    farmer_id: str,
    message: str,
    thread_id: str | None = None,
) -> str:
    if thread_id is None:
        thread_id = f"thread-{farmer_id}"

    pool = await get_pool()
    await ensure_thread_exists(thread_id, farmer_id, pool)
    
    recent_messages, _ = await apply_memory_pressure(thread_id, pool, llm_model)
    
    messages = recent_messages + [HumanMessage(content=message)]
    
    initial_state = {
        "messages": messages,
        "farmer_id": farmer_id
    }

    try:
        result = await agrisage_graph.ainvoke(
            initial_state,
            config={"recursion_limit": 50},
        )
        
        # Extract new messages generated in this turn
        new_messages = result["messages"][len(messages):]
        
        # Save this turn
        ai_reply = ""
        tool_messages = []
        
        for msg in new_messages:
            if isinstance(msg, AIMessage) and msg.content:
                ai_reply = msg.content
            elif isinstance(msg, ToolMessage):
                tool_messages.append({"name": msg.name or "tool", "content": msg.content})
        
        await save_turn(thread_id, message, ai_reply, tool_messages, pool)
        
        if ai_reply:
            return ai_reply
            
        return "Koi response generate nahi hua. Dobara try karo."

    except Exception as exc:
        logger.error("run_agent error: %s", exc, exc_info=True)
        return (
            "Maafi karo — abhi ek technical issue aa gaya hai. "
            "Thodi der mein phir se try karo. "
            f"(Error: {type(exc).__name__})"
        )

async def run_agent_streaming(
    farmer_id: str,
    message: str,
    thread_id: str | None = None,
) -> AsyncIterator[str]:
    if thread_id is None:
        thread_id = f"thread-{farmer_id}"

    pool = await get_pool()
    await ensure_thread_exists(thread_id, farmer_id, pool)
    
    recent_messages, _ = await apply_memory_pressure(thread_id, pool, llm_model)
    
    messages = recent_messages + [HumanMessage(content=message)]
    
    initial_state = {
        "messages": messages,
        "farmer_id": farmer_id
    }

    try:
        full_reply = ""
        tool_messages = []

        async for event in agrisage_graph.astream_events(
            initial_state,
            config={"recursion_limit": 50},
            version="v2",
        ):
            event_name = event.get("event", "")
            event_data = event.get("data", {})

            # When a tool finishes, emit its result with a special marker
            # so the frontend can render mandi lists, advice, etc. explicitly
            if event_name == "on_tool_end":
                output = event_data.get("output", "")
                tool_name = event.get("name", "tool")
                content_str = ""
                if isinstance(output, ToolMessage):
                    content_str = output.content
                    tool_messages.append({"name": tool_name, "content": content_str})
                elif isinstance(output, str):
                    content_str = output
                    tool_messages.append({"name": tool_name, "content": content_str})
                if content_str:
                    # Emit as a parseable marker for the frontend
                    yield f"\x00TOOL:{tool_name}\x00{content_str}\x00/TOOL\x00"

            # Stream LLM tokens
            if event_name == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if chunk is None:
                    continue
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    continue
                content = chunk.content if hasattr(chunk, "content") else ""
                if isinstance(content, str) and content:
                    full_reply += content
                    yield content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")
                            if text:
                                full_reply += text
                                yield text

        if full_reply or tool_messages:
            await save_turn(thread_id, message, full_reply, tool_messages, pool)

    except Exception as exc:
        logger.error("run_agent_streaming error: %s", exc, exc_info=True)
        yield f"\n[Error: {type(exc).__name__} — {exc}]"
