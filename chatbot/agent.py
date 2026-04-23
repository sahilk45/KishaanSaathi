"""
chatbot/agent.py — AgriSage LangGraph StateGraph Agent
=======================================================
Entry point for the chatbot. Called by FastAPI POST /chat and /chat/stream.

Replaces the previous create_react_agent (ReAct) approach with a proper
LangGraph StateGraph workflow:
  load_context → agent → [tools ↺] → memory_check → save_message → END

Key design:
  - run_agent()           — full response as string (for POST /chat)
  - run_agent_streaming() — token-by-token generator (for POST /chat/stream)
  - All state management, DB persistence, and memory summarisation handled
    inside the graph nodes (chatbot/graph/).
  - LangSmith tracing is automatic via LANGCHAIN_TRACING_V2 env var.
  - Thread ID enables session resumption and rolling memory.

Environment variables required (from .env):
  GROQ_API_KEY (or GROK_API_KEY) — Groq API key
  LANGCHAIN_TRACING_V2            — 'true' to enable LangSmith tracing
  LANGCHAIN_API_KEY               — LangSmith API key
  LANGCHAIN_PROJECT               — LangSmith project name
  DATABASE_URL                    — Neon PostgreSQL connection string
"""

import os
import logging
from typing import AsyncIterator

from dotenv import load_dotenv

load_dotenv()

# ── Fix GROQ key alias: .env sometimes uses 'GROK_API_KEY' ──────────────────
if os.getenv("GROK_API_KEY") and not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = os.environ["GROK_API_KEY"]

# ── LangSmith tracing — must be set before any langchain imports ─────────────
_tracing = os.getenv("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", _tracing)
if os.getenv("LANGCHAIN_API_KEY"):
    os.environ.setdefault("LANGCHAIN_API_KEY", os.getenv("LANGCHAIN_API_KEY"))
if os.getenv("LANGCHAIN_PROJECT"):
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGCHAIN_PROJECT", "AgriSage-Chatbot"))

from langchain_core.messages import HumanMessage, AIMessage

# ── Import the compiled StateGraph (singleton, built at import time) ──────────
from chatbot.graph.workflow import agrisage_graph

logger = logging.getLogger(__name__)


def _build_initial_state(
    farmer_id: str,
    thread_id: str,
    message: str,
) -> dict:
    """
    Constructs the initial state dict passed into the graph.
    load_context_node will overwrite most fields with live DB data.
    The HumanMessage is placed in messages so load_context can append
    system/history messages before it during its execution.
    """
    return {
        "messages":                [HumanMessage(content=message)],
        "farmer_id":               farmer_id,
        "thread_id":               thread_id,
        # Placeholders — all overwritten by load_context_node
        "farmer_name":             "",
        "farmer_state":            "",
        "farmer_district":         "",
        "farmer_language":         "Hindi",
        "current_crop":            "",
        "centroid_lat":            20.5937,
        "centroid_lng":            78.9629,
        "area_ha":                 1.0,
        "ndvi":                    0.5,
        "health_score":            50.0,
        "climate_score":           50.0,
        "predicted_yield":         1500.0,
        "npk_intensity_kgha":      120.0,
        "irr_ratio":               0.5,
        "wdi":                     0.3,
        "district_soil_score":     50.0,
        "kharif_avg_maxtemp":      32.0,
        "rabi_avg_maxtemp":        26.0,
        "kharif_total_rain":       900.0,
        "existing_summary":        None,
        "selected_mandi":          None,
        "awaiting_mandi_selection": False,
        "available_mandis":        None,
        "tool_call_count":         0,   # Safety counter — reset each turn
    }


async def run_agent(
    farmer_id: str,
    message: str,
    history: list[dict] | None = None,
    thread_id: str | None = None,
) -> str:
    """
    Main entry point for the chatbot. Called by FastAPI POST /chat.

    Args:
        farmer_id: UUID string of the authenticated farmer.
        message:   The farmer's current message text.
        history:   (legacy / unused) Prior conversation turns.
                   History is now loaded from Neon DB via thread_id.
        thread_id: Chat session identifier. Defaults to f"thread-{farmer_id}".

    Returns:
        The agent's final text response as a string.
    """
    if thread_id is None:
        thread_id = f"thread-{farmer_id}"

    initial_state = _build_initial_state(farmer_id, thread_id, message)

    try:
        result = await agrisage_graph.ainvoke(
            initial_state,
            config={"recursion_limit": 50},
        )
        # Extract final AI response (last non-tool AIMessage)
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
                return str(msg.content)
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
    history: list[dict] | None = None,
    thread_id: str | None = None,
) -> AsyncIterator[str]:
    """
    Streaming variant — yields text chunks as they are generated.
    Used by FastAPI POST /chat/stream.

    Streams using astream_events() which gives token-level granularity.
    Only tokens from the FINAL answer (not tool call arguments) are yielded.

    Args:
        farmer_id: UUID of the farmer.
        message:   Current message text.
        history:   (legacy / unused) loaded from DB via thread_id.
        thread_id: Chat session identifier.

    Yields:
        Text chunks (strings) to stream directly to the HTTP response.
    """
    if thread_id is None:
        thread_id = f"thread-{farmer_id}"

    initial_state = _build_initial_state(farmer_id, thread_id, message)

    try:
        final_answer_started = False

        async for event in agrisage_graph.astream_events(
            initial_state,
            config={"recursion_limit": 50},
            version="v2",
        ):
            event_name = event.get("event", "")
            event_data = event.get("data", {})

            # We only want token chunks from the agent node (not tool calls)
            if event_name == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if chunk is None:
                    continue
                # Skip if this is a tool-call chunk (no text content)
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    continue
                content = chunk.content if hasattr(chunk, "content") else ""
                if isinstance(content, str) and content:
                    final_answer_started = True
                    yield content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")
                            if text:
                                final_answer_started = True
                                yield text

    except Exception as exc:
        logger.error("run_agent_streaming error: %s", exc, exc_info=True)
        yield f"\n[Error: {type(exc).__name__} — {exc}]"
