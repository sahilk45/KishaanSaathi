"""
chatbot/graph/state.py — AgriSageState TypedDict
=================================================
The shared state object that flows through every node of the LangGraph StateGraph.

Adapted to the ACTUAL Neon DB schema used in this project:
  farmers        → id, name, state_name, dist_name
  farm_fields    → id, farmer_id, city_name, state_name, area_hectares,
                   center_lat, center_lon
  field_predictions → crop_type, npk_input, irrigation_ratio, wdi_used,
                      ndvi_value, final_health_score, predicted_yield,
                      climate_score, kharif_temp_used, kharif_rain_used,
                      rabi_temp_used, soil_score_used
  district_climate_history → district_soil_health_score, kharif_avg_maxtemp,
                             kharif_total_rain, rabi_avg_maxtemp

Key design:
  - `messages` uses the add_messages reducer so LangGraph APPENDS new messages
    instead of replacing the whole list. This prevents the tool-call loop where
    the LLM lost all history after each ToolNode execution.
  - load_context_node rebuilds the full list once per turn by returning the
    complete initial list — add_messages handles this correctly via ID dedup.
  - All other fields are simple values set by load_context_node once per turn.
  - Mandi-selection fields track the multi-turn market price conversation flow.
"""

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages   # ← BUG FIX: append reducer


class AgriSageState(TypedDict):
    # ── Core message list ─────────────────────────────────────────────────────
    # add_messages reducer: LangGraph APPENDS returned messages instead of
    # replacing the whole list. This is the fix for the infinite tool-call loop.
    # load_context_node returns the full rebuilt list — add_messages deduplicates
    # by message ID so there are no duplicates even on full rebuild.
    messages: Annotated[list[BaseMessage], add_messages]   # ← BUG FIX

    # ── Routing / session keys ─────────────────────────────────────────────────
    farmer_id: str
    thread_id: str

    # ── Farmer profile (populated by load_context_node) ───────────────────────
    farmer_name: str
    farmer_state: str        # e.g. "Punjab"
    farmer_district: str     # e.g. "Ludhiana"
    farmer_language: str     # e.g. "Hindi"

    # ── Farm / season data ─────────────────────────────────────────────────────
    current_crop: str
    centroid_lat: float
    centroid_lng: float
    area_ha: float
    ndvi: float
    health_score: float
    climate_score: float
    predicted_yield: float
    npk_intensity_kgha: float
    irr_ratio: float
    wdi: float
    district_soil_score: float
    kharif_avg_maxtemp: float
    rabi_avg_maxtemp: float
    kharif_total_rain: float

    # ── Memory ─────────────────────────────────────────────────────────────────
    existing_summary: Optional[str]  # Loaded from chat_threads.summary

    # ── Mandi selection state (multi-turn market price flow) ──────────────────
    selected_mandi: Optional[str]          # Set after farmer picks a mandi
    awaiting_mandi_selection: bool          # True when bot listed mandis, awaiting choice
    available_mandis: Optional[list[str]]  # List shown to farmer

    # ── Safety counters — prevents infinite agent↔tool loops ──────────────────
    tool_call_count: int            # Total tool calls this turn (global cap)
    tool_call_counts: dict          # Per-tool counts e.g. {"get_farmer_data": 2} — blocks retries
