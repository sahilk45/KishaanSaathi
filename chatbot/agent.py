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

        # astream yields one dict per node execution: {"node_name": state_update}
        async for node_output in agrisage_graph.astream(
            initial_state,
            config={"recursion_limit": 50},
        ):
            for node_name, state_update in node_output.items():
                updated_msgs = state_update.get("messages", [])

                if node_name == "tools":
                    # Emit tool results with markers for the frontend
                    for msg in updated_msgs:
                        if isinstance(msg, ToolMessage):
                            tool_name = msg.name or "tool"
                            content_str = msg.content or ""
                            tool_messages.append({"name": tool_name, "content": content_str})
                            if content_str:
                                yield f"\x00TOOL:{tool_name}\x00{content_str}\x00/TOOL\x00"

                elif node_name == "agent":
                    # Emit the AI's final text response
                    for msg in updated_msgs:
                        if (
                            isinstance(msg, AIMessage)
                            and msg.content
                            and not getattr(msg, "tool_calls", None)
                        ):
                            full_reply = msg.content
                            yield msg.content

        if full_reply or tool_messages:
            await save_turn(thread_id, message, full_reply, tool_messages, pool)

    except Exception as exc:
        logger.error("run_agent_streaming error: %s", exc, exc_info=True)
        yield f"\n[Error: {type(exc).__name__} — {exc}]"
