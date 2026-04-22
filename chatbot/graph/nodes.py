"""
chatbot/graph/nodes.py — LangGraph StateGraph node functions
=============================================================

Node pipeline:
  load_context_node  → agent_node → [tool_node | memory_check_node]
                                         ↑              ↓
                                    (loop back)   save_message_node → END

Node responsibilities:
  load_context_node  : Fetch farmer profile from DB; build system prompt +
                       history; populate AgriSageState.
  agent_node         : LLM (ChatGroq) decides which tool to call or generates
                       the final response.
  memory_check_node  : Check if summarisation is needed; generate summary.
  save_message_node  : Persist new messages to Neon DB.
  should_use_tool    : Conditional edge — "tools" vs "memory_check".

ToolNode from langgraph.prebuilt handles actual tool dispatch.
"""

import os
import logging
from typing import Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from chatbot.db import get_db_connection
from chatbot.graph.state import AgriSageState
from chatbot.graph.memory import (
    get_or_create_thread,
    fetch_thread_summary,
    build_initial_messages,
    should_summarize,
    generate_and_save_summary,
    save_message,
    count_thread_messages,
    SUMMARY_KEEP_RECENT,
    MESSAGES_TO_SUMMARIZE,
)

logger = logging.getLogger(__name__)

# ── Safety cap: max tool calls per conversation turn ─────────────────────────
MAX_TOOL_CALLS = 8

# ── LLM singleton ──────────────────────────────────────────────────────────────
_GROQ_API_KEY = (
    os.getenv("GROQ_API_KEY")
    or os.getenv("GROK_API_KEY")
    or ""
)


def _get_llm(streaming: bool = False) -> ChatGroq:
    """Returns a ChatGroq client (llama-3.3-70b-versatile)."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        api_key=_GROQ_API_KEY,
        streaming=streaming,
    )


# ── Helper: fetch full farmer profile from real DB schema ─────────────────────

async def _fetch_farmer_profile(farmer_id: str) -> Optional[dict]:
    """
    JOINs farmers → farm_fields → field_predictions (latest) →
    district_climate_history to produce a flat profile dict.
    Returns None if farmer or farm not found.
    """
    try:
        async with get_db_connection() as conn:
            # ── Farmer basic info ─────────────────────────────────────────────
            farmer = await conn.fetchrow(
                "SELECT name, state_name, dist_name FROM farmers WHERE id = $1",
                farmer_id,
            )
            if not farmer:
                return None

            # ── Latest farm field ─────────────────────────────────────────────
            farm = await conn.fetchrow(
                """
                SELECT id, city_name, state_name, area_hectares,
                       center_lat, center_lon
                FROM   farm_fields
                WHERE  farmer_id = $1
                ORDER  BY created_at DESC
                LIMIT  1
                """,
                farmer_id,
            )
            if not farm:
                # Return minimal profile with just farmer data
                return {
                    "farmer_id":       farmer_id,
                    "farmer_name":     farmer["name"],
                    "farmer_state": farmer["state_name"],
                    "farmer_district": farmer["dist_name"],
                    "farmer_language": "Hindi",
                    "current_crop": "Unknown",
                    "centroid_lat": 20.5937,
                    "centroid_lng": 78.9629,
                    "area_ha": 1.0,
                    "ndvi": 0.5,
                    "health_score": 50.0,
                    "climate_score": 50.0,
                    "predicted_yield": 1500.0,
                    "npk_intensity_kgha": 120.0,
                    "irr_ratio": 0.5,
                    "wdi": 0.3,
                    "district_soil_score": 50.0,
                    "kharif_avg_maxtemp": 32.0,
                    "rabi_avg_maxtemp": 26.0,
                    "kharif_total_rain": 900.0,
                }

            # ── Latest prediction row ─────────────────────────────────────────
            season = await conn.fetchrow(
                """
                SELECT crop_type, npk_input, irrigation_ratio, wdi_used,
                       ndvi_value, final_health_score, predicted_yield,
                       climate_score, kharif_temp_used, kharif_rain_used,
                       rabi_temp_used, soil_score_used
                FROM   field_predictions
                WHERE  field_id = $1
                ORDER  BY year DESC, calculated_at DESC
                LIMIT  1
                """,
                str(farm["id"]),
            )

            # ── District climate (fallback for missing season data) ───────────
            dist_name = (farm["city_name"] or farmer["dist_name"] or "").lower().strip()
            climate = await conn.fetchrow(
                """
                SELECT AVG(kharif_avg_maxtemp) AS kharif_temp,
                       AVG(kharif_total_rain)  AS kharif_rain,
                       AVG(rabi_avg_maxtemp)   AS rabi_temp,
                       AVG(district_soil_health_score) AS soil_score
                FROM   district_climate_history
                WHERE  LOWER(dist_name) = $1
                """,
                dist_name,
            )

    except Exception as exc:
        logger.error("_fetch_farmer_profile error: %s", exc)
        return None

    state  = farm["state_name"]  or farmer["state_name"]  or "Unknown"
    district = farm["city_name"] or farmer["dist_name"]   or "Unknown"

    def _safe(val, fallback):
        return float(val) if val is not None else fallback

    if season:
        return {
            "farmer_id":        farmer_id,   # ← passed to system prompt for LLM tool calls
            "farmer_name":      farmer["name"],
            "farmer_state":     state,
            "farmer_district":  district,
            "farmer_language":  "Hindi",
            "current_crop":     season["crop_type"] or "Unknown",
            "centroid_lat":     _safe(farm["center_lat"], 20.59),
            "centroid_lng":     _safe(farm["center_lon"], 78.96),
            "area_ha":          _safe(farm["area_hectares"], 1.0),
            "ndvi":             _safe(season["ndvi_value"], 0.5),
            "health_score":     _safe(season["final_health_score"], 50.0),
            "climate_score":    _safe(season["climate_score"], 50.0),
            "predicted_yield":  _safe(season["predicted_yield"], 1500.0),
            "npk_intensity_kgha": _safe(season["npk_input"], 120.0),
            "irr_ratio":        _safe(season["irrigation_ratio"], 0.5),
            "wdi":              _safe(season["wdi_used"], 0.3),
            "district_soil_score": _safe(
                season["soil_score_used"],
                _safe(climate["soil_score"] if climate else None, 50.0),
            ),
            "kharif_avg_maxtemp": _safe(
                season["kharif_temp_used"],
                _safe(climate["kharif_temp"] if climate else None, 32.0),
            ),
            "rabi_avg_maxtemp": _safe(
                season["rabi_temp_used"],
                _safe(climate["rabi_temp"] if climate else None, 26.0),
            ),
            "kharif_total_rain": _safe(
                season["kharif_rain_used"],
                _safe(climate["kharif_rain"] if climate else None, 900.0),
            ),
        }
    else:
        return {
            "farmer_id":        farmer_id,
            "farmer_name":      farmer["name"],
            "farmer_state":     state,
            "farmer_district":  district,
            "farmer_language":  "Hindi",
            "current_crop":     "Unknown",
            "centroid_lat":     _safe(farm["center_lat"], 20.59),
            "centroid_lng":     _safe(farm["center_lon"], 78.96),
            "area_ha":          _safe(farm["area_hectares"], 1.0),
            "ndvi":             0.5,
            "health_score":     50.0,
            "climate_score":    50.0,
            "predicted_yield":  1500.0,
            "npk_intensity_kgha": _safe(climate["soil_score"] if climate else None, 120.0),
            "irr_ratio":        0.5,
            "wdi":              0.3,
            "district_soil_score": _safe(climate["soil_score"] if climate else None, 50.0),
            "kharif_avg_maxtemp": _safe(climate["kharif_temp"] if climate else None, 32.0),
            "rabi_avg_maxtemp": _safe(climate["rabi_temp"] if climate else None, 26.0),
            "kharif_total_rain": _safe(climate["kharif_rain"] if climate else None, 900.0),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Node 1: load_context_node
# ═════════════════════════════════════════════════════════════════════════════

async def load_context_node(state: AgriSageState) -> dict:
    """
    Entry node. Called once per conversation turn.

    1. Ensure chat_threads row exists.
    2. Fetch farmer profile from DB → populate state fields.
    3. Load existing summary from DB → set existing_summary.
    4. Build initial message list [system prompt + summary + recent history].
    5. Return partial state update (only fields that change).
    """
    farmer_id = state["farmer_id"]
    thread_id = state["thread_id"]

    # ── Ensure thread exists ──────────────────────────────────────────────────
    try:
        await get_or_create_thread(thread_id, farmer_id)
    except Exception as exc:
        logger.warning("load_context: could not create thread: %s", exc)

    # ── Fetch farmer profile ──────────────────────────────────────────────────
    profile = await _fetch_farmer_profile(farmer_id)
    if not profile:
        profile = {
            "farmer_id":       farmer_id,
            "farmer_name":     "Farmer",
            "farmer_state": "Unknown",
            "farmer_district": "Unknown",
            "farmer_language": "Hindi",
            "current_crop": "Unknown",
            "centroid_lat": 20.59,
            "centroid_lng": 78.96,
            "area_ha": 1.0,
            "ndvi": 0.5,
            "health_score": 50.0,
            "climate_score": 50.0,
            "predicted_yield": 1500.0,
            "npk_intensity_kgha": 120.0,
            "irr_ratio": 0.5,
            "wdi": 0.3,
            "district_soil_score": 50.0,
            "kharif_avg_maxtemp": 32.0,
            "rabi_avg_maxtemp": 26.0,
            "kharif_total_rain": 900.0,
        }

    # ── Load existing summary ─────────────────────────────────────────────────
    try:
        existing_summary = await fetch_thread_summary(thread_id)
    except Exception as exc:
        logger.warning("load_context: could not fetch summary: %s", exc)
        existing_summary = None

    # ── Build initial messages (system + summary + recent history) ────────────
    try:
        # Pass farmer_id into context so system prompt includes the real UUID
        profile["farmer_id"] = farmer_id
        initial_messages = await build_initial_messages(
            thread_id=thread_id,
            farmer_context=profile,
            existing_summary=existing_summary,
        )
    except Exception as exc:
        logger.warning("load_context: could not build history: %s", exc)
        # Minimal fallback: just the system prompt
        initial_messages = [
            SystemMessage(content=f"You are KisanSaathi, an AI agricultural advisor. Farmer ID: {farmer_id}")
        ]

    return {
        # Farmer context fields
        "farmer_name":       profile["farmer_name"],
        "farmer_state":      profile["farmer_state"],
        "farmer_district":   profile["farmer_district"],
        "farmer_language":   profile["farmer_language"],
        "current_crop":      profile["current_crop"],
        "centroid_lat":      profile["centroid_lat"],
        "centroid_lng":      profile["centroid_lng"],
        "area_ha":           profile["area_ha"],
        "ndvi":              profile["ndvi"],
        "health_score":      profile["health_score"],
        "climate_score":     profile["climate_score"],
        "predicted_yield":   profile["predicted_yield"],
        "npk_intensity_kgha": profile["npk_intensity_kgha"],
        "irr_ratio":         profile["irr_ratio"],
        "wdi":               profile["wdi"],
        "district_soil_score": profile["district_soil_score"],
        "kharif_avg_maxtemp":  profile["kharif_avg_maxtemp"],
        "rabi_avg_maxtemp":    profile["rabi_avg_maxtemp"],
        "kharif_total_rain":   profile["kharif_total_rain"],
        # Memory
        "existing_summary":  existing_summary,
        # Full message list: [system context messages] + [current human message]
        # The current human message is the LAST item in state.messages
        # (placed there by agent.py before invoking the graph).
        "messages": initial_messages + [state["messages"][-1]],
    }


# ═════════════════════════════════════════════════════════════════════════════
# Node 2: agent_node
# ═════════════════════════════════════════════════════════════════════════════

async def agent_node(state: AgriSageState) -> dict:
    """
    Core LLM node.

    1. Takes the current message list from state.
    2. Calls ChatGroq with all 4 tools bound.
    3. Returns the AIMessage (may have tool_calls → graph routes to ToolNode).
    """
    from chatbot.tools import (
        get_farmer_data,
        get_weather,
        get_market_price,
        get_crop_advice,
    )
    tools = [get_farmer_data, get_weather, get_market_price, get_crop_advice]

    llm = _get_llm(streaming=False)
    llm_with_tools = llm.bind_tools(tools)

    messages = state["messages"]

    try:
        response = await llm_with_tools.ainvoke(messages)
    except Exception as exc:
        logger.error("agent_node LLM error: %s", exc)
        response = AIMessage(
            content=(
                "Maafi karo — abhi ek technical issue aa gaya hai. "
                "Thodi der mein phir se try karo. "
                f"(Error: {type(exc).__name__})"
            )
        )

    # Increment tool_call_count if this response includes tool calls
    current_count = state.get("tool_call_count", 0)
    new_count = current_count + (1 if (isinstance(response, AIMessage) and response.tool_calls) else 0)

    return {"messages": state["messages"] + [response], "tool_call_count": new_count}


# ═════════════════════════════════════════════════════════════════════════════
# Node 3: memory_check_node
# ═════════════════════════════════════════════════════════════════════════════

async def memory_check_node(state: AgriSageState) -> dict:
    """
    Called after every final agent response.
    Checks if message count in DB has hit MAX_MESSAGES.
    If yes: generates a summary, saves to DB, and compresses the message list
    in state (replaces oldest 45 with a SystemMessage containing the summary).
    """
    thread_id = state["thread_id"]

    try:
        if await should_summarize(thread_id):
            messages = state["messages"]
            llm = _get_llm()
            # Compress only the non-system messages to avoid summarising the system prompt
            non_system = [m for m in messages if not isinstance(m, SystemMessage)]
            if len(non_system) >= MESSAGES_TO_SUMMARIZE:
                summary = await generate_and_save_summary(thread_id, non_system, llm)
                # Rebuild messages: keep system messages + summary + recent non-system
                system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
                kept_recent = non_system[-SUMMARY_KEEP_RECENT:]
                new_messages = (
                    system_msgs
                    + [SystemMessage(content=f"CONVERSATION SUMMARY:\n{summary}")]
                    + kept_recent
                )
                return {"messages": new_messages, "existing_summary": summary}
    except Exception as exc:
        logger.warning("memory_check_node error (non-fatal): %s", exc)

    return {}   # no changes


# ═════════════════════════════════════════════════════════════════════════════
# Node 4: save_message_node
# ═════════════════════════════════════════════════════════════════════════════

async def save_message_node(state: AgriSageState) -> dict:
    """
    Persists the latest HumanMessage and AIMessage to Neon DB.
    Skips SystemMessages (those are ephemeral context, not user-visible turns).
    """
    thread_id = state["thread_id"]
    messages   = state["messages"]

    try:
        # Find the last human message and last AI message
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
        )
        last_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage) and not m.tool_calls),
            None,
        )

        if last_human and last_human.content:
            await save_message(thread_id, "human", str(last_human.content))
        if last_ai and last_ai.content:
            await save_message(thread_id, "ai", str(last_ai.content))

    except Exception as exc:
        logger.warning("save_message_node error (non-fatal): %s", exc)

    return {}   # no state changes


# ═════════════════════════════════════════════════════════════════════════════
# Conditional edge: should_use_tool
# ═════════════════════════════════════════════════════════════════════════════

def should_use_tool(state: AgriSageState) -> str:
    """
    Reads the last message in state.messages.
    Returns:
      "tools"        → LLM produced tool_calls → route to ToolNode
      "memory_check" → LLM produced a plain text response → we're done

    Safety: if tool_call_count >= MAX_TOOL_CALLS, force exit to prevent
    the graph from hitting LangGraph's hard recursion limit (25 hops).
    This happens when a tool keeps failing and the LLM retries indefinitely.
    """
    # Safety guard — break out of the tool loop if we've called too many times
    tool_call_count = state.get("tool_call_count", 0)
    if tool_call_count >= MAX_TOOL_CALLS:
        logger.warning(
            "should_use_tool: MAX_TOOL_CALLS (%d) reached — forcing exit to memory_check.",
            MAX_TOOL_CALLS,
        )
        # Inject a fallback message so the user gets a response rather than silence
        messages = state["messages"]
        last = messages[-1] if messages else None
        if last is None or (isinstance(last, AIMessage) and last.tool_calls):
            # The last message is still a tool call — inject a plain text fallback
            state["messages"].append(
                AIMessage(
                    content=(
                        "Main abhi yeh jaankari obtain karne mein samarth nahi hoon. "
                        "Kripya thodi der baad phir try karein ya seedha apne "
                        "krishi vibhag se sampark karein."
                    )
                )
            )
        return "memory_check"

    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "memory_check"
