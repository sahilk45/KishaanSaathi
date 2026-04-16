"""
chatbot/agent.py — LangGraph ReAct Agent
=========================================
Builds a conversational ReAct-style agent using LangGraph's create_react_agent.
Uses ChatGroq (llama-3.3-70b-versatile) as the LLM backbone.
Every run is traced via LangSmith.

Features:
  - Dynamic system prompt from live DB context (context_builder)
  - 4 tools: get_farmer_data, get_weather, get_market_price, get_crop_advice
  - Streaming support for low-latency mobile responses
  - Max 6 tool-call iterations (prevents infinite loops)
  - Async-first design for FastAPI compatibility

Environment variables required:
  GROQ_API_KEY (or GROK_API_KEY) — Groq API key
  LANGCHAIN_TRACING_V2  — 'true' to enable LangSmith tracing
  LANGCHAIN_API_KEY     — LangSmith API key
  LANGCHAIN_PROJECT     — LangSmith project name (e.g. 'AgriSage-Chatbot')
"""

import os
import logging
from typing import AsyncIterator

from dotenv import load_dotenv

load_dotenv()

# -- Fix GROQ key alias: .env uses typo 'GROK_API_KEY', SDK needs 'GROQ_API_KEY' --
if os.getenv("GROK_API_KEY") and not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = os.environ["GROK_API_KEY"]

# -- LangSmith tracing -- must be set before any langchain imports ------------
os.environ.setdefault("LANGCHAIN_TRACING_V2", os.getenv("LANGCHAIN_TRACING_V2", "false"))

from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langsmith import traceable

from chatbot.tools import get_farmer_data, get_weather, get_market_price, get_crop_advice
from chatbot.context_builder import build_system_prompt

logger = logging.getLogger(__name__)

# -- LLM configuration --------------------------------------------------------
# Prefer GROQ_API_KEY (canonical Groq SDK name); fall back to GROK_API_KEY (typo in .env)
_GROQ_API_KEY = (
    os.getenv("GROQ_API_KEY")
    or os.getenv("GROK_API_KEY")
    or ""
)

if not _GROQ_API_KEY:
    logger.warning(
        "GROQ_API_KEY not set in .env -- chatbot will not be able to call the LLM."
    )


def _get_llm() -> ChatGroq:
    """Creates a fresh ChatGroq client (lightweight -- no expensive initialization)."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        api_key=_GROQ_API_KEY,
        streaming=True,
    )


# -- Tool registry ------------------------------------------------------------
TOOLS = [get_farmer_data, get_weather, get_market_price, get_crop_advice]


def _build_message_history(history: list[dict]) -> list:
    """Converts the JSON history (from the API request) to LangChain message objects."""
    messages = []
    for entry in history:
        role    = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role in ("assistant", "ai"):
            messages.append(AIMessage(content=content))
        # system messages from history are skipped -- we inject our own
    return messages


@traceable(name="AgriSage-Chat-Turn", metadata={"version": "1.0", "llm": "llama-3.3-70b-versatile"})
async def run_agent(
    farmer_id: str,
    message: str,
    history: list[dict] | None = None,
) -> str:
    """
    Main entry point for the chatbot.  Called by FastAPI POST /chat.

    Args:
        farmer_id: UUID string of the authenticated farmer
        message:   The farmer's current message
        history:   List of previous turns: [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        The agent's final text response as a string.
    """
    if history is None:
        history = []

    # -- Build dynamic system prompt from live DB ----------------------------
    system_prompt = await build_system_prompt(farmer_id)

    # -- Create LangGraph ReAct agent ----------------------------------------
    llm = _get_llm()

    # prompt injects system prompt before the message list
    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        prompt=system_prompt,
    )

    # -- Assemble messages ----------------------------------------------------
    prior_messages = _build_message_history(history)
    prior_messages.append(HumanMessage(content=message))

    # -- Invoke agent (max 6 tool iterations) ---------------------------------
    try:
        result = await agent.ainvoke(
            {"messages": prior_messages},
            config={"recursion_limit": 6},
        )
        response = result["messages"][-1].content
    except Exception as exc:
        logger.error("Agent invocation error: %s", exc, exc_info=True)
        response = (
            "Maafi karo -- abhi ek technical issue aa gaya hai. "
            "Thodi der mein phir se try karo. "
            f"(Error: {type(exc).__name__})"
        )

    logger.info(
        "Chat turn complete -- farmer=%s  tokens_estimated=%d",
        farmer_id, len(response.split()),
    )
    return response


async def run_agent_streaming(
    farmer_id: str,
    message: str,
    history: list[dict] | None = None,
) -> AsyncIterator[str]:
    """
    Streaming variant -- yields text chunks as they are generated.
    Used by FastAPI POST /chat/stream for low-latency mobile delivery.

    Args:
        farmer_id: UUID of the farmer
        message:   Current message text
        history:   Prior conversation turns

    Yields:
        Text chunks (strings) -- stream them directly to the HTTP response.
    """
    if history is None:
        history = []

    system_prompt = await build_system_prompt(farmer_id)

    llm = _get_llm()
    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        prompt=system_prompt,
    )

    prior_messages = _build_message_history(history)
    prior_messages.append(HumanMessage(content=message))

    try:
        async for chunk in agent.astream(
            {"messages": prior_messages},
            config={"recursion_limit": 6},
            stream_mode="values",
        ):
            # Yield the last AI message content if it changed
            last_msg = chunk["messages"][-1]
            if hasattr(last_msg, "content") and isinstance(last_msg, AIMessage):
                yield last_msg.content
    except Exception as exc:
        logger.error("Streaming agent error: %s", exc, exc_info=True)
        yield f"[Error: {type(exc).__name__} -- {exc}]"
