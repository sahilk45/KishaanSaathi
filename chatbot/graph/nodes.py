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
MAX_TOOL_CALLS = 5   # increased from 3 — allow more complex multi-step reasoning
MAX_PER_TOOL   = 2   # increased from 1 — allow re-trying or multi-value retrieval

# ── LLM singleton ──────────────────────────────────────────────────────────────
_GROQ_API_KEY = (
    os.getenv("GROQ_API_KEY")
    or os.getenv("GROK_API_KEY")
    or ""
)


_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "groq").lower().strip()  # 'groq' or 'gemini'


def _get_llm(streaming: bool = False):
    """
    Returns the configured LLM client.

    Controlled by LLM_PROVIDER in .env:
      - 'groq'   → ChatGroq (llama-3.3-70b-versatile) — default
      - 'gemini' → ChatGoogleGenerativeAI (gemini-2.0-flash) — best tool-calling Gemini model

    Model overrides:
      - GROQ_MODEL   = e.g. llama-3.3-70b-versatile
      - GEMINI_MODEL = e.g. gemini-2.0-flash (default) or gemini-1.5-pro
    """
    if _LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        logger.info("LLM provider: Gemini (%s)", model)
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=_GEMINI_API_KEY,
            temperature=0.2,
            # streaming not supported in the same way — ignore flag for Gemini
        )
    else:  # default: groq
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        logger.info("LLM provider: Groq (%s)", groq_model)
        return ChatGroq(
            model=groq_model,
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
            # ── Farmer basic info ─────────────────────────────────────────────────
            import uuid as _uuid_mod
            try:
                farmer_uuid = _uuid_mod.UUID(str(farmer_id))  # Fix #1
            except ValueError:
                logger.error("_fetch_farmer_profile: invalid farmer_id '%s'", farmer_id)
                return None

            farmer = await conn.fetchrow(
                "SELECT name, state_name, dist_name FROM farmers WHERE id = $1",
                farmer_uuid,  # ← Fix #1: uuid.UUID object
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
                farmer_uuid,  # ← Fix #1: uuid.UUID object
            )
            if not farm:
                # Farmer exists but has no farm field registered
                return {
                    "farmer_id":          farmer_id,
                    "farmer_name":        farmer["name"],
                    "farmer_state":       farmer["state_name"],
                    "farmer_district":    farmer["dist_name"],
                    "farmer_language":    "Hindi",
                    "current_crop":       "Unknown",
                    "centroid_lat":       20.5937,
                    "centroid_lng":       78.9629,
                    "area_ha":            1.0,
                    "ndvi":               None,
                    "health_score":       None,
                    "climate_score":      None,
                    "predicted_yield":    None,
                    "npk_intensity_kgha": None,
                    "irr_ratio":          None,
                    "wdi":                None,
                    "district_soil_score": None,
                    "kharif_avg_maxtemp": None,
                    "rabi_avg_maxtemp":   None,
                    "kharif_total_rain":  None,
                    "data_status":        "no_farm",  # ← tells prompt what's missing
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
            # Bug #4 fix: Use farmer["dist_name"] (registered district, matches DB)
            # NOT farm["city_name"] (reverse-geocoded city, often won't match district names)
            dist_name = (farmer["dist_name"] or "").lower().strip()
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
            "farmer_id":          farmer_id,
            "farmer_name":        farmer["name"],
            "farmer_state":       state,
            "farmer_district":    district,
            "farmer_language":    "Hindi",
            "current_crop":       season["crop_type"] or "Unknown",
            "centroid_lat":       _safe(farm["center_lat"], 20.59),
            "centroid_lng":       _safe(farm["center_lon"], 78.96),
            "area_ha":            _safe(farm["area_hectares"], 1.0),
            "ndvi":               _safe(season["ndvi_value"], 0.5),
            "health_score":       _safe(season["final_health_score"], 50.0),
            "climate_score":      _safe(season["climate_score"], 50.0),
            "predicted_yield":    _safe(season["predicted_yield"], 1500.0),
            "npk_intensity_kgha": _safe(season["npk_input"], 120.0),
            "irr_ratio":          _safe(season["irrigation_ratio"], 0.5),
            "wdi":                _safe(season["wdi_used"], 0.3),
            "district_soil_score": _safe(
                season["soil_score_used"],
                _safe(climate["soil_score"] if climate else None, 50.0),
            ),
            "kharif_avg_maxtemp": _safe(
                season["kharif_temp_used"],
                _safe(climate["kharif_temp"] if climate else None, 32.0),
            ),
            "rabi_avg_maxtemp":   _safe(
                season["rabi_temp_used"],
                _safe(climate["rabi_temp"] if climate else None, 26.0),
            ),
            "kharif_total_rain":  _safe(
                season["kharif_rain_used"],
                _safe(climate["kharif_rain"] if climate else None, 900.0),
            ),
            "data_status":        "complete",  # ← full data available
        }
    else:
        return {
            "farmer_id":          farmer_id,
            "farmer_name":        farmer["name"],
            "farmer_state":       state,
            "farmer_district":    district,
            "farmer_language":    "Hindi",
            "current_crop":       "Unknown",
            "centroid_lat":       _safe(farm["center_lat"], 20.59),
            "centroid_lng":       _safe(farm["center_lon"], 78.96),
            "area_ha":            _safe(farm["area_hectares"], 1.0),
            "ndvi":               None,
            "health_score":       None,
            "climate_score":      None,
            "predicted_yield":    None,
            "npk_intensity_kgha": _safe(climate["soil_score"] if climate else None, 120.0),
            "irr_ratio":          None,
            "wdi":                None,
            "district_soil_score": _safe(climate["soil_score"] if climate else None, 50.0),
            "kharif_avg_maxtemp": _safe(climate["kharif_temp"] if climate else None, 32.0),
            "rabi_avg_maxtemp":   _safe(climate["rabi_temp"] if climate else None, 26.0),
            "kharif_total_rain":  _safe(climate["kharif_rain"] if climate else None, 900.0),
            "data_status":        "no_prediction",  # ← farm exists but no prediction run
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

    # ── Unconditional farmer_id injection — foolproof hallucination prevention ───────────
    # The LLM may hallucinate any UUID (commonly 123e4567-e89b-12d3-a456-426614174000).
    # Instead of detecting & comparing, we ALWAYS overwrite farmer_id with the correct
    # one from state. The LLM never needs to get this right — we guarantee it for it.
    correct_farmer_id = state.get("farmer_id", "")
    if isinstance(response, AIMessage) and response.tool_calls and correct_farmer_id:
        fixed_calls = []
        for tc in response.tool_calls:
            tc_dict = dict(tc)
            args = dict(tc_dict.get("args") or {})
            if "farmer_id" in args:                    # tool expects a farmer_id arg
                args["farmer_id"] = correct_farmer_id  # always inject — no comparison
                tc_dict = {**tc_dict, "args": args}
            fixed_calls.append(tc_dict)
        response = AIMessage(
            content=response.content or "",
            tool_calls=fixed_calls,
            response_metadata=getattr(response, "response_metadata", {}),
        )

    # Track TOTAL tool call count only.
    # Per-tool counts (tool_call_counts) are updated in should_use_tool AFTER
    # the decision to allow — so they reflect tools that actually ran, not
    # tools the LLM merely requested. This prevents first-call false blocking.
    current_count = state.get("tool_call_count", 0)
    if isinstance(response, AIMessage) and response.tool_calls:
        new_count = current_count + 1
    else:
        new_count = current_count

    return {
        "messages": [response],   # ← BUG FIX: return ONLY the new message
        # add_messages reducer in state.py will append it to existing history.
        # Returning state["messages"] + [response] would cause duplicates.
        "tool_call_count": new_count,
    }



# ═════════════════════════════════════════════════════════════════════════════
# Node 2b: sanitize_tool_args_node
# ═════════════════════════════════════════════════════════════════════════════

async def sanitize_tool_args_node(state: AgriSageState) -> dict:
    """
    Safety node — runs BETWEEN agent_node and the ToolNode.

    ALWAYS injects the correct farmer_id from state into every tool call,
    unconditionally. The LLM never needs to get farmer_id right — this node
    guarantees the correct value reaches every tool before it executes.
    """
    import copy
    correct_farmer_id = state.get("farmer_id", "")
    messages = state["messages"]
    last = messages[-1] if messages else None

    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {}  # nothing to sanitize

    if not correct_farmer_id:
        return {}  # no farmer_id in state — skip

    new_tool_calls = []
    for tc in last.tool_calls:
        tc_copy = copy.deepcopy(dict(tc))
        args = dict(tc_copy.get("args") or {})
        if "farmer_id" in args:              # only inject into tools that expect it
            args["farmer_id"] = correct_farmer_id  # unconditional overwrite
            tc_copy["args"] = args
        new_tool_calls.append({
            "id":   tc_copy.get("id", ""),
            "name": tc_copy.get("name", ""),
            "args": tc_copy.get("args", {}),
            "type": tc_copy.get("type", "tool_call"),
        })

    # Rebuild the AIMessage with guaranteed-correct tool call args
    corrected_msg = AIMessage(
        content=last.content or "",
        tool_calls=new_tool_calls,
    )
    # ← BUG FIX: return only the corrected message as a 1-item list.
    # add_messages reducer will REPLACE the old last AIMessage (same ID)
    # and keep everything else — no manual slicing needed.
    return {"messages": [corrected_msg]}






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
                # ← BUG FIX: return the full new list directly.
                # add_messages will REPLACE all existing messages (different IDs)
                # effectively compressing the history as intended.
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
    Conditional edge: routes the graph after agent_node.
    Returns 'tools', 'block_tool', or 'memory_check'.

    Per-tool run counts are derived from ToolMessages already in the message
    history (since the last HumanMessage). This is reliable because:
      - ToolMessages are only added by the ToolNode after a tool ACTUALLY runs
      - No state mutation needed (which does not persist in conditional edges)
      - Reads from immutable message history — always accurate

    Blocking: if a tool already ran this turn, strip its call from the AIMessage
    and route to memory_check. NO ToolMessages injected (causes BadRequestError).
    
    FIX #5: Check for awaiting_user_input flags in ToolMessages to prevent re-calling
    tools when they explicitly indicate they're waiting for user input.
    """
    from langchain_core.messages import ToolMessage, HumanMessage as HM

    messages        = list(state["messages"])
    # No tool calls in last message — plain text answer, we are done
    last_msg = messages[-1] if messages else None
    if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
        return "memory_check"
    
    # FIX #5: Check if the last ToolMessage indicates awaiting user input
    # If so, block any further tool calls until the user responds
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            try:
                import json
                # Try to parse ToolMessage content as JSON
                if isinstance(msg.content, str):
                    content_json = json.loads(msg.content)
                    if content_json.get("awaiting_user_input") or content_json.get("status") == "awaiting_mandi_selection":
                        logger.warning(
                            "should_use_tool: tool is awaiting user input (%s) — blocking re-call",
                            content_json.get("status", "unknown")
                        )
                        return "block_tool"
            except (json.JSONDecodeError, AttributeError):
                # Not JSON or can't parse — continue checking
                pass
            # Stop after first ToolMessage (most recent)
            break

    # Count tools that ALREADY RAN this turn from ToolMessages in history
    # (ToolMessages are only added by the ToolNode after actual execution)
    last_human_idx = -1
    for i, m in enumerate(messages):
        if isinstance(m, HM):
            last_human_idx = i
    current_turn = messages[last_human_idx + 1:] if last_human_idx >= 0 else messages

    tool_name_run_counts = {}
    turn_tool_calls = 0
    for m in current_turn:
        if isinstance(m, ToolMessage):
            t_name = getattr(m, "name", None) or "unknown"
            tool_name_run_counts[t_name] = tool_name_run_counts.get(t_name, 0) + 1
            turn_tool_calls += 1

    # Guard 1: total iteration cap for the current turn
    if turn_tool_calls >= MAX_TOOL_CALLS:
        logger.warning(
            "should_use_tool: MAX_TOOL_CALLS (%d) reached this turn — forcing block.",
            MAX_TOOL_CALLS,
        )
        return "block_tool"

    # Separate allowed vs. blocked calls
    allowed_calls = []
    blocked_names = []

    for tc in last_msg.tool_calls:
        tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
        run_count = tool_name_run_counts.get(tool_name, 0)

        if run_count >= MAX_PER_TOOL:
            logger.warning(
                "should_use_tool: blocking '%s' — already ran %d time(s) this turn",
                tool_name, run_count,
            )
            blocked_names.append(tool_name)
        else:
            allowed_calls.append(tc)

    # All blocked: route to block_tool_node to strip calls
    if not allowed_calls:
        logger.warning(
            "should_use_tool: all tool calls blocked %s — routing to block_tool.",
            blocked_names,
        )
        return "block_tool"

    # Some blocked, some allowed — let it proceed to tools.
    return "tools"


# ═════════════════════════════════════════════════════════════════════════════
# Node 2c: block_tool_node
# ═════════════════════════════════════════════════════════════════════════════

async def block_tool_node(state: AgriSageState) -> dict:
    """
    Called when should_use_tool decides to block all tool calls (to prevent loops).
    Since conditional edges cannot mutate state, this dedicated node replaces the
    last AIMessage with a version that has NO tool_calls and adds a plain-text fallback.
    """
    messages = state["messages"]
    last_msg = messages[-1] if messages else None

    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        content = last_msg.content or (
            "Mujhe lagatar tools call karne ki zaroorat nahi hai. "
            "Aapke FARMER PROFILE se seedha jawab deta hoon: "
            f"Health Score {state.get('health_score', 'N/A')}, "
            f"Crop: {state.get('current_crop', 'N/A')}, "
            f"District: {state.get('farmer_district', 'N/A')}."
        )
        fallback_msg = AIMessage(
            content=content,
            tool_calls=[],
        )
        # ← BUG FIX: return only the fallback message.
        # add_messages replaces the old AIMessage (same ID) and keeps history.
        return {"messages": [fallback_msg]}

    return {}
