"""
chatbot/tools/get_crop_advice.py — Tool D (What-If Engine)
==========================================================
Runs a mathematical sensitivity analysis over controllable farm inputs
(NPK intensity, irrigation ratio) to find the top score-improving changes.

Key design principle:
  The Python engine (XGBoost + health score formula) CALCULATES.
  The LLM only EXPLAINS the returned numbers in simple language.
  The LLM must NEVER compute score deltas itself.

Adapts to ACTUAL schema:
  farmers / farm_fields / field_predictions / district_climate_history

Called when farmer asks:
  "Mera score kaise badhega?"
  "Loan nahi mila — kya karu?"
  "Score improve karne ke liye kya change karu?"
"""

import logging
import asyncio
import numpy as np
import pandas as pd

from langchain_core.tools import tool
from chatbot.db import get_db_connection
from chatbot.models_loader import get_models, prepare_features, BENCHMARK_YIELDS

logger = logging.getLogger(__name__)

# ── Health Score formula (must be identical to services/health_score.py) ─────
def _compute_health_score(
    predicted_yield: float,
    soil_health_score: float,
    npk: float,
    wdi: float,
    irr_ratio: float,
    kharif_rain: float,
    kharif_temp: float,
    rabi_temp: float,
    ndvi: float | None,
    crop_type: str,
    benchmark_yields: dict,
) -> float:
    """
    5-component KisanSaathi health score (0–100).
    Weights: Yield 25% | Soil 20% | Water 25% | Climate 15% | NDVI 15%
    """
    # 1. Yield Performance Score (25%)
    benchmark = benchmark_yields.get(crop_type, 2000.0)
    yield_score = min((predicted_yield / benchmark) * 100.0, 100.0) if benchmark > 0 else 50.0

    # 2. Soil Health Score (20%)
    soil_base   = min((soil_health_score / 200.0) * 100.0, 100.0)
    npk_penalty = min((abs(npk - 120.0) / 120.0) * 30.0, 30.0)
    soil_score  = max(soil_base - npk_penalty, 0.0)

    # 3. Water Stress Score (25%)
    wdi_score   = (1.0 - wdi) * 100.0
    irr_score   = max((1.0 - abs(1.0 - irr_ratio)) * 100.0, 0.0)
    rain_score  = min((kharif_rain / 600.0) * 100.0, 100.0)
    water_score = 0.5 * wdi_score + 0.3 * irr_score + 0.2 * rain_score

    # 4. Climate Risk Score (15%)
    kharif_stress = max(0.0, kharif_temp - 35.0) * 5.0
    rabi_stress   = max(0.0, rabi_temp   - 25.0) * 5.0
    climate_score = max(100.0 - kharif_stress - rabi_stress, 0.0)

    # 5. NDVI Score (15%)
    if ndvi is not None:
        ndvi_score = min(ndvi * 125.0, 100.0)
    else:
        ndvi_score = min(yield_score * 0.8, 100.0)

    return round(
        yield_score   * 0.25 +
        soil_score    * 0.20 +
        water_score   * 0.25 +
        climate_score * 0.15 +
        ndvi_score    * 0.15,
        2,
    )


def _what_if_engine(
    base_inputs: dict,
    current_score: float,
    xgb_model,
    le_crop,
    le_state,
    benchmark_yields: dict,
) -> list[dict]:
    """
    Runs 12 what-if scenarios by varying controllable features.
    Returns up to 5 improvements sorted by score gain (descending).

    Controllable features:
      - NPK_Intensity_KgHa (fertilizer)
      - Irrigation_Intensity_Ratio
    """
    suggestions = []

    def evaluate(modified: dict) -> tuple[float, float]:
        feats = prepare_features(modified, le_crop, le_state)
        feat_df = pd.DataFrame([{
            "year":                       modified.get("year", 2026),
            "State_Encoded":              feats[1],
            "Crop_Encoded":               feats[2],
            "NPK_Intensity_KgHa":         feats[3],
            "Irrigation_Intensity_Ratio": feats[4],
            "WDI":                        feats[5],
            "Kharif_Avg_MaxTemp":         feats[6],
            "Kharif_Total_Rain":          feats[7],
            "Rabi_Avg_MaxTemp":           feats[8],
            "District_Soil_Health_Score": feats[9],
        }])
        log_pred = float(xgb_model.predict(feat_df)[0])
        log_pred = min(max(log_pred, 0.0), 11.0)
        new_yield = float(np.expm1(log_pred))

        new_score = _compute_health_score(
            predicted_yield=new_yield,
            soil_health_score=modified["District_Soil_Health_Score"],
            npk=modified["NPK_Intensity_KgHa"],
            wdi=modified["WDI"],
            irr_ratio=modified["Irrigation_Intensity_Ratio"],
            kharif_rain=modified["Kharif_Total_Rain"],
            kharif_temp=modified["Kharif_Avg_MaxTemp"],
            rabi_temp=modified["Rabi_Avg_MaxTemp"],
            ndvi=modified.get("ndvi"),
            crop_type=modified["Crop_Type"],
            benchmark_yields=benchmark_yields,
        )
        return new_score, new_yield

    orig_npk = base_inputs["NPK_Intensity_KgHa"]
    orig_irr = base_inputs["Irrigation_Intensity_Ratio"]

    # Scenario group 1: NPK variations
    for npk_val in [60, 80, 100, 120, 140, 160]:
        if abs(npk_val - orig_npk) < 5:
            continue
        m = base_inputs.copy()
        m["NPK_Intensity_KgHa"] = float(npk_val)
        try:
            new_score, new_yield = evaluate(m)
        except Exception as exc:
            logger.warning("NPK scenario %s failed: %s", npk_val, exc)
            continue
        gain = new_score - current_score
        if gain > 0.5:
            suggestions.append({
                "change": f"Change NPK from {orig_npk:.0f} → {npk_val} kg/ha",
                "new_score": new_score,
                "new_yield_kg_ha": round(new_yield, 0),
                "score_gain": round(gain, 1),
                "category": "fertilizer",
                "action": (
                    f"Reduce fertilizer to {npk_val} kg/ha. Excess NPK degrades soil quality "
                    "and increases climate score penalty."
                ),
            })

    # Scenario group 2: Irrigation ratio variations
    for irr_val in [0.3, 0.5, 0.7, 0.85, 1.0]:
        if abs(irr_val - orig_irr) < 0.05:
            continue
        m = base_inputs.copy()
        m["Irrigation_Intensity_Ratio"] = float(irr_val)
        try:
            new_score, new_yield = evaluate(m)
        except Exception as exc:
            logger.warning("Irrigation scenario %s failed: %s", irr_val, exc)
            continue
        gain = new_score - current_score
        if gain > 0.5:
            suggestions.append({
                "change": f"Change irrigation ratio from {orig_irr:.2f} → {irr_val:.2f}",
                "new_score": new_score,
                "new_yield_kg_ha": round(new_yield, 0),
                "score_gain": round(gain, 1),
                "category": "irrigation",
                "action": (
                    f"Adjust irrigated area to {irr_val * 100:.0f}% of your farm. "
                    "Optimal ratio is 1.0 (100% irrigated)."
                ),
            })

    # Sort by gain, deduplicate by category (best per category)
    suggestions.sort(key=lambda x: x["score_gain"], reverse=True)
    return suggestions[:5]


async def _fetch_farmer_inputs(farmer_id: str) -> dict | None:
    """Fetches all necessary inputs for the What-If engine from the DB."""
    async with get_db_connection() as conn:
        farm = await conn.fetchrow(
            """
            SELECT ff.id        AS field_id,
                   ff.city_name, ff.state_name,
                   f.state_name AS farmer_state,
                   f.dist_name  AS farmer_dist
            FROM   farm_fields ff
            JOIN   farmers f ON f.id = ff.farmer_id
            WHERE  ff.farmer_id = $1
            ORDER  BY ff.created_at DESC LIMIT 1
            """,
            farmer_id,
        )
        if not farm:
            return None

        season = await conn.fetchrow(
            """
            SELECT crop_type, npk_input, irrigation_ratio, wdi_used,
                   ndvi_value, final_health_score, predicted_yield, year,
                   kharif_temp_used, kharif_rain_used, rabi_temp_used,
                   soil_score_used
            FROM   field_predictions
            WHERE  field_id = $1
            ORDER  BY year DESC, calculated_at DESC LIMIT 1
            """,
            str(farm["field_id"]),
        )
        if not season:
            return None

        # Fetch district climate data for static features
        dist_name = (farm["city_name"] or farm["farmer_dist"] or "").lower().strip()
        state_name = farm["state_name"] or farm["farmer_state"] or ""

        climate = await conn.fetchrow(
            """
            SELECT AVG(kharif_avg_maxtemp) AS kharif_temp,
                   AVG(kharif_total_rain)  AS kharif_rain,
                   AVG(rabi_avg_maxtemp)   AS rabi_temp,
                   AVG(wdi)                AS wdi,
                   AVG(district_soil_health_score) AS soil_score
            FROM   district_climate_history
            WHERE  LOWER(dist_name) = $1
            """,
            dist_name,
        )

    # Use stored values from the prediction row first, then fall back to climate history
    kharif_temp  = season["kharif_temp_used"]  or (climate["kharif_temp"] if climate else 32.0)
    kharif_rain  = season["kharif_rain_used"]  or (climate["kharif_rain"] if climate else 900.0)
    rabi_temp    = season["rabi_temp_used"]    or (climate["rabi_temp"]   if climate else 26.0)
    wdi          = season["wdi_used"]          or (climate["wdi"]         if climate else 0.5)
    soil_score   = season["soil_score_used"]   or (climate["soil_score"]  if climate else 50.0)

    return {
        "State_Name":                 state_name,
        "Crop_Type":                  season["crop_type"],
        "year":                       season["year"],
        "NPK_Intensity_KgHa":         float(season["npk_input"] or 120.0),
        "Irrigation_Intensity_Ratio": float(season["irrigation_ratio"] or 0.5),
        "WDI":                        float(wdi),
        "Kharif_Avg_MaxTemp":         float(kharif_temp),
        "Kharif_Total_Rain":          float(kharif_rain),
        "Rabi_Avg_MaxTemp":           float(rabi_temp),
        "District_Soil_Health_Score": float(soil_score),
        "ndvi":                       season["ndvi_value"],
        "_current_score":             float(season["final_health_score"]),
        "_predicted_yield":           float(season["predicted_yield"]),
    }


@tool
async def get_crop_advice(farmer_id: str) -> dict:
    """
    Runs a What-If sensitivity analysis on the farmer's controllable inputs
    (NPK fertilizer intensity, irrigation ratio) to find which changes improve
    their Climate/Health Score the most.
    Use when farmer asks how to improve their score, get better loan eligibility,
    or what farming practice changes they should make.
    Returns top 5 suggestions with exact score gains — the LLM must explain
    these in simple, actionable language.

    Args:
        farmer_id: UUID string of the farmer
    """
    # ── Load farmer inputs ────────────────────────────────────────────────────
    try:
        inputs = await _fetch_farmer_inputs(farmer_id)
    except Exception as exc:
        logger.error("get_crop_advice DB error: %s", exc)
        return {"error": True, "message": f"Database error: {str(exc)}"}

    if not inputs:
        return {
            "error": True,
            "message": (
                "No prediction data found for this farmer. "
                "Please run a prediction first via POST /predict."
            ),
        }

    current_score = inputs.pop("_current_score")
    current_yield = inputs.pop("_predicted_yield")

    # ── Score band labels ────────────────────────────────────────────────────
    def score_band(s: float) -> tuple[str, str]:
        if s >= 65:
            return ("Low Risk", "ELIGIBLE for Standard Loan")
        elif s >= 45:
            return ("Medium Risk", "ELIGIBLE for Small Loan (REVIEW status)")
        else:
            return ("High Risk", "INELIGIBLE — loan rejected")

    risk, loan = score_band(current_score)

    # ── Load models ───────────────────────────────────────────────────────────
    try:
        xgb_model, le_crop, le_state, benchmark_yields = get_models()
    except Exception as exc:
        logger.error("get_crop_advice model load error: %s", exc)
        return {
            "error": True,
            "message": f"ML model not available: {str(exc)}",
        }

    # ── Run What-If engine ────────────────────────────────────────────────────
    try:
        suggestions = _what_if_engine(
            base_inputs=inputs,
            current_score=current_score,
            xgb_model=xgb_model,
            le_crop=le_crop,
            le_state=le_state,
            benchmark_yields=benchmark_yields,
        )
    except Exception as exc:
        logger.error("What-If engine error: %s", exc)
        suggestions = []

    if not suggestions:
        return {
            "error": False,
            "current_score": round(current_score, 1),
            "current_yield_kg_ha": round(current_yield, 0),
            "score_band": risk,
            "loan_eligibility": loan,
            "top_improvements": [],
            "message": (
                "No significant improvements found from NPK/irrigation changes alone. "
                "Your current farm management appears optimal for your district conditions. "
                "Consider talking to a local KVK (Krishi Vigyan Kendra) for crop-switch advice."
            ),
            "instruction_for_llm": (
                "Tell the farmer their score is already well-optimized for these controllable factors. "
                "Suggest they consult their local KVK and check weather-related tools."
            ),
        }

    return {
        "error": False,
        "crop": inputs["Crop_Type"],
        "state": inputs["State_Name"],
        "current_score": round(current_score, 1),
        "current_yield_kg_ha": round(current_yield, 0),
        "score_band": risk,
        "loan_eligibility": loan,
        "top_improvements": suggestions,
        "instruction_for_llm": (
            "Explain each suggestion in simple, encouraging language. "
            "Tell the farmer EXACTLY what to do (e.g., 'fertilizer 215 se 120 kg/ha karo') "
            "and WHY it helps (e.g., 'excess NPK reduces soil quality score'). "
            "Mention the score they will reach and what loan it qualifies for."
        ),
    }
