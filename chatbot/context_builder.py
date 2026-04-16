"""
chatbot/context_builder.py — Dynamic system prompt builder
===========================================================
Fetches the farmer's live context from Neon PostgreSQL before EVERY
chat turn and injects it into the LLM system prompt.

Maps to the ACTUAL schema in database.py:
  farmers       → id, name, phone, state_name, dist_name
  farm_fields   → id, farmer_id, state_name, city_name, area_hectares
  field_predictions → the latest prediction row (health score, yield, ndvi, etc.)

There is no separate alerts table in the production schema — we surface
important data signals as inline alerts within the prompt.
"""

import logging
from chatbot.db import get_db_connection

logger = logging.getLogger(__name__)


async def build_system_prompt(farmer_id: str) -> str:
    """
    Builds and returns the KisanSaathi system prompt customised
    with this farmer's live data from Neon DB.

    Falls back to a generic context-less prompt if the farmer has no
    data yet (e.g., brand-new registration with no predictions made).
    """
    try:
        async with get_db_connection() as conn:
            # ── Farmer profile ────────────────────────────────────────────────
            farmer = await conn.fetchrow(
                "SELECT name, state_name, dist_name FROM farmers WHERE id = $1",
                farmer_id,
            )
            if not farmer:
                return _generic_prompt()

            # ── Latest farm field ─────────────────────────────────────────────
            farm = await conn.fetchrow(
                """
                SELECT id, city_name, state_name, area_hectares, center_lat, center_lon
                FROM   farm_fields
                WHERE  farmer_id = $1
                ORDER  BY created_at DESC
                LIMIT  1
                """,
                farmer_id,
            )

            if not farm:
                # Farmer registered but no farm yet
                return _farmer_only_prompt(farmer)

            # ── Latest prediction (the "current season") ───────────────────────
            season = await conn.fetchrow(
                """
                SELECT crop_type, npk_input, irrigation_ratio, wdi_used,
                       ndvi_value, final_health_score, predicted_yield,
                       kharif_temp_used, kharif_rain_used, rabi_temp_used,
                       soil_score_used, risk_level, loan_decision,
                       yield_score, soil_score, water_score, climate_score,
                       ndvi_score, year
                FROM   field_predictions
                WHERE  field_id = $1
                ORDER  BY year DESC, calculated_at DESC
                LIMIT  1
                """,
                str(farm["id"]),
            )

    except Exception as exc:
        logger.warning("context_builder: DB error — %s. Using generic prompt.", exc)
        return _generic_prompt()

    if not season:
        return _farm_no_season_prompt(farmer, farm)

    # ── NDVI label ────────────────────────────────────────────────────────────
    ndvi_val = season["ndvi_value"]
    if ndvi_val is None:
        ndvi_label = "N/A"
        ndvi_band  = "Unknown"
    else:
        ndvi_label = f"{ndvi_val:.3f}"
        ndvi_band  = (
            "Healthy 🟢" if ndvi_val > 0.6 else
            "Moderate 🟡" if ndvi_val > 0.3 else
            "Stressed 🔴"
        )

    # ── Irrigation label ──────────────────────────────────────────────────────
    irr = season["irrigation_ratio"]
    irr_label = f"{irr:.2f}" if irr is not None else "N/A"

    # ── Inline alerts based on data signals ──────────────────────────────────
    alerts = []
    if ndvi_val is not None and ndvi_val < 0.3:
        alerts.append("⚠️  CROP STRESS: NDVI below 0.3 — crop shows severe vegetation stress.")
    if season["final_health_score"] < 45:
        alerts.append("🔴 LOAN RISK: Health Score below 45 — HIGH risk, loan INELIGIBLE currently.")
    if irr is not None and irr > 1.2:
        alerts.append("💧 OVER-IRRIGATION: Irrigation ratio > 1.2 — excess water may harm soil.")
    if season["wdi_used"] is not None and season["wdi_used"] > 0.7:
        alerts.append("☀️  DROUGHT RISK: High Water Deficit Index — consider drought-resistant practices.")
    alerts_text = "\n    ".join(alerts) if alerts else "None"

    state  = farm["state_name"] or farmer["state_name"]
    city   = farm["city_name"]  or farmer["dist_name"]
    area   = farm["area_hectares"] or 1.0

    prompt = f"""You are KisanSaathi (किसान साथी), an expert AI agricultural advisor for Indian farmers.
You have deep knowledge of Indian agriculture, crop management, climate science, and government schemes.
Always give specific, actionable advice grounded in the farmer's actual data below.
Never give generic responses — every answer must reference the farmer's real numbers.
Reply in simple, warm language. Keep answers under 150 words unless farmer explicitly asks for more detail.

=== FARMER PROFILE ===
Name: {farmer['name']}
District/City: {city}, State: {state}
Farm Area: {area:.1f} hectares

=== CURRENT SEASON (Year {season['year']}) ===
Crop: {season['crop_type']}
NDVI: {ndvi_label}  ({ndvi_band})
Health / Climate Score: {season['final_health_score']:.1f} / 100  → {season['risk_level']} RISK
Loan Decision: {season['loan_decision']}
Predicted Yield: {season['predicted_yield']:.0f} kg/ha
NPK Intensity: {season['npk_input']} kg/ha
Irrigation Ratio: {irr_label}
Water Deficit Index (WDI): {season['wdi_used'] if season['wdi_used'] is not None else 'N/A'}
Kharif Temp: {season['kharif_temp_used']}°C  |  Kharif Rain: {season['kharif_rain_used']} mm
Rabi Temp: {season['rabi_temp_used']}°C

Score Breakdown:
  Yield Score:   {season['yield_score']:.1f}/100   (25% weight)
  Soil Score:    {season['soil_score']:.1f}/100    (20% weight)
  Water Score:   {season['water_score']:.1f}/100   (25% weight)
  Climate Score: {season['climate_score']:.1f}/100 (15% weight)
  NDVI Score:    {season['ndvi_score']:.1f}/100    (15% weight)

=== ACTIVE ALERTS ===
    {alerts_text}

=== RULES FOR YOU (KisanSaathi) ===
- ALWAYS use tools to fetch live data. Never guess weather, prices, or score changes.
- When farmer asks about price → call get_market_price tool (ask which mandi if not mentioned).
- When farmer asks about weather, irrigation timing, rain → call get_weather tool.
- When farmer asks how to improve score / get loan → call get_crop_advice tool (What-If engine).
- When farmer asks about their farm status, alerts, NDVI → call get_farmer_data tool.
- All numbers in your answer MUST come from tool return values, not your internal knowledge.
- The LLM (you) explains; the Python engine calculates. Never guess a score delta.
- For Hindi/mixed-language queries, respond in Hinglish (Hindi + English mix).
"""
    return prompt


# ── Fallback prompts ──────────────────────────────────────────────────────────

def _generic_prompt() -> str:
    return """You are KisanSaathi (किसान साथी), an expert AI agricultural advisor for Indian farmers.
Help farmers with crop advice, weather queries, market prices, and loan eligibility.
Always use tools to fetch live data. Never guess. Keep answers concise and actionable.
For Hindi queries, respond in Hinglish.
"""


def _farmer_only_prompt(farmer) -> str:
    return f"""You are KisanSaathi (किसान साथी), an AI agricultural advisor.
Farmer {farmer['name']} from {farmer['dist_name']}, {farmer['state_name']} has just registered.
They have not yet registered a farm field. Guide them to register a field first via POST /farm/register.
For any crop/weather/price questions, use the available tools.
"""


def _farm_no_season_prompt(farmer, farm) -> str:
    return f"""You are KisanSaathi (किसान साथी), an AI agricultural advisor.
Farmer {farmer['name']} has registered a {farm['area_hectares'] or '?'}-hectare farm
in {farm['city_name'] or farmer['dist_name']}, {farm['state_name'] or farmer['state_name']}.
No prediction has been run yet. Advise them to run POST /predict to get their health score.
For weather/price questions, use the available tools.
"""
