"""
chatbot/graph/workflow.py — LangGraph StateGraph assembly
=========================================================

Graph structure:
────────────────────────────────────────────────────────
START
  │
  ▼
load_context  ──────────────────────────────────────────┐
  │                                                     │
  ▼                                                     │
agent_node ──[has tool_calls?]──YES──► tool_node ───────┘
  │                                    (loops back to agent)
  NO (final response)
  │
  ▼
memory_check_node
  │
  ▼
save_message_node
  │
  ▼
END
────────────────────────────────────────────────────────

Design notes:
  - StateGraph(AgriSageState) — NOT ReAct, NOT MessageGraph.
  - ToolNode from langgraph.prebuilt handles all tool dispatch.
  - We do NOT use LangGraph's built-in checkpointer — persistence is
    handled manually via Neon DB in memory.py.
  - LangSmith tracing is automatic via LANGCHAIN_TRACING_V2 env var.
  - agrisage_graph is a module-level singleton compiled once at import time.
"""

import os
import logging

from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from chatbot.graph.state import AgriSageState
from chatbot.graph.nodes import (
    load_context_node,
    agent_node,
    sanitize_tool_args_node,
    block_tool_node,
    memory_check_node,
    save_message_node,
    should_use_tool,
)
from chatbot.tools import (
    get_farmer_data,
    get_weather,
    get_market_price,
    get_crop_advice,
)

logger = logging.getLogger(__name__)


def _get_tools() -> list:
    """Returns the list of all 4 LangChain tools (called by agent_node too)."""
    return [get_farmer_data, get_weather, get_market_price, get_crop_advice]


def build_graph():
    """
    Assembles and compiles the AgriSage StateGraph.
    Called once at module import time.
    """
    graph = StateGraph(AgriSageState)

    tools       = _get_tools()
    tool_node   = ToolNode(tools)

    # ── Add nodes ──────────────────────────────────────────────────────────────
    graph.add_node("load_context",  load_context_node)
    graph.add_node("agent",         agent_node)
    graph.add_node("sanitize",      sanitize_tool_args_node)
    graph.add_node("block_tool",    block_tool_node)
    graph.add_node("tools",         tool_node)
    graph.add_node("memory_check",  memory_check_node)
    graph.add_node("save_message",  save_message_node)

    # ── Add edges ──────────────────────────────────────────────────────────────
    graph.add_edge(START,          "load_context")
    graph.add_edge("load_context", "agent")

    # Conditional: tool calls → sanitize → tools, else → memory check
    # Fix #2: route through sanitize node first to correct any bad farmer_ids
    graph.add_conditional_edges(
        "agent",
        should_use_tool,
        {
            "tools":        "sanitize",
            "block_tool":   "block_tool",
            "memory_check": "memory_check",
        },
    )

    # After blocking, proceed to memory check
    graph.add_edge("block_tool", "memory_check")

    # After sanitization, run the actual tool
    graph.add_edge("sanitize",     "tools")    # Fix #2: sanitize then dispatch

    # After tool execution, loop back to agent
    graph.add_edge("tools",        "agent")

    # Final path: memory check → persist → done
    graph.add_edge("memory_check", "save_message")
    graph.add_edge("save_message", END)

    compiled = graph.compile()
    logger.info(" AgriSage LangGraph StateGraph compiled successfully.")
    return compiled


# ── Singleton — compiled once at import time ───────────────────────────────────
agrisage_graph = build_graph()
