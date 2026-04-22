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
  - `messages` is a plain list managed explicitly by each node.
    load_context_node fully rebuilds it each turn (system prompt + history +
    current human message).  Subsequent nodes append to it.
  - All other fields are simple values set by load_context_node once per turn.
  - Mandi-selection fields track the multi-turn market price conversation flow.
"""

from typing import Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


class AgriSageState(TypedDict):
    # ── Core message list — replaced wholesale each turn by load_context_node ──
    # agent_node, memory_check_node, save_message_node append to it.
    messages: list[BaseMessage]

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

    # ── Safety counter — prevents infinite agent↔tool loops ───────────────────
    tool_call_count: int  # Incremented by agent_node each time it fires a tool call
