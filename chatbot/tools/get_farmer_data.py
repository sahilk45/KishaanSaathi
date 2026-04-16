"""
chatbot/tools/get_farmer_data.py — Tool A
==========================================
Fetches the farmer's complete profile, latest farm field, and most recent
prediction (health score, yield, NDVI, etc.) from Neon PostgreSQL.

Maps to ACTUAL schema:
  farmers            → id, name, phone, state_name, dist_name
  farm_fields        → id, farmer_id, city_name, state_name, area_hectares, polygon_id
  field_predictions  → latest prediction row per field

Called when farmer asks:
  "Mera health score kya hai?"
  "Meri farm ki details batao"
  "Mera NDVI kitna hai?"
  "Mera predicted yield kitna hai?"
"""

import logging
from langchain_core.tools import tool
from chatbot.db import get_db_connection

logger = logging.getLogger(__name__)


@tool
async def get_farmer_data(farmer_id: str) -> dict:
    """
    Retrieves complete farmer profile, farm details, latest predicted yield,
    health/climate score, NDVI vegetation index, and active data alerts.
    Use when farmer asks about their farm status, score, NDVI, or yield.

    Args:
        farmer_id: UUID string of the farmer (from /farmers/register endpoint)
    """
    try:
        async with get_db_connection() as conn:
            # ── Farmer profile ────────────────────────────────────────────────
            farmer = await conn.fetchrow(
                "SELECT name, state_name, dist_name, phone FROM farmers WHERE id = $1",
                farmer_id,
            )
            if not farmer:
                return {
                    "error": True,
                    "message": f"Farmer with ID '{farmer_id}' not found. Please register first.",
                }

            # ── Latest farm field ─────────────────────────────────────────────
            farm = await conn.fetchrow(
                """
                SELECT id, city_name, state_name, area_hectares,
                       center_lat, center_lon, polygon_id, field_name
                FROM   farm_fields
                WHERE  farmer_id = $1
                ORDER  BY created_at DESC
                LIMIT  1
                """,
                farmer_id,
            )
            if not farm:
                return {
                    "farmer_name": farmer["name"],
                    "state": farmer["state_name"],
                    "district": farmer["dist_name"],
                    "error": False,
                    "message": "No farm field registered. Please register a farm via POST /farm/register.",
                }

            # ── Latest prediction for this field ──────────────────────────────
            season = await conn.fetchrow(
                """
                SELECT crop_type, npk_input, irrigation_ratio, wdi_used,
                       ndvi_value, final_health_score, predicted_yield,
                       risk_level, loan_decision, year,
                       kharif_temp_used, kharif_rain_used, soil_score_used
                FROM   field_predictions
                WHERE  field_id = $1
                ORDER  BY year DESC, calculated_at DESC
                LIMIT  1
                """,
                str(farm["id"]),
            )

    except Exception as exc:
        logger.error("get_farmer_data error: %s", exc)
        return {"error": True, "message": f"Database error: {str(exc)}"}

    if not season:
        return {
            "farmer_name": farmer["name"],
            "state": farm["state_name"] or farmer["state_name"],
            "district": farm["city_name"] or farmer["dist_name"],
            "area_ha": round(farm["area_hectares"] or 1.0, 2),
            "field_name": farm["field_name"],
            "error": False,
            "message": "Farm registered but no prediction run yet. Call POST /predict first.",
        }

    # Build inline alerts from data signals
    alerts = []
    ndvi = season["ndvi_value"]
    if ndvi is not None and ndvi < 0.3:
        alerts.append({
            "type": "CROP_STRESS",
            "severity": "HIGH",
            "message": f"NDVI {ndvi:.3f} is critically low — severe vegetation stress detected.",
        })
    if season["final_health_score"] < 45:
        alerts.append({
            "type": "LOAN_RISK",
            "severity": "HIGH",
            "message": "Health Score below 45 — loan is currently INELIGIBLE.",
        })
    if season["wdi_used"] is not None and season["wdi_used"] > 0.7:
        alerts.append({
            "type": "DROUGHT_RISK",
            "severity": "MEDIUM",
            "message": f"High Water Deficit Index ({season['wdi_used']:.2f}) — consider drought-resilient practices.",
        })

    ndvi_status = (
        "Healthy" if ndvi is not None and ndvi > 0.6 else
        "Moderate" if ndvi is not None and ndvi > 0.3 else
        "Stressed" if ndvi is not None else
        "No data"
    )

    return {
        "error": False,
        "farmer_name": farmer["name"],
        "state": farm["state_name"] or farmer["state_name"],
        "district": farm["city_name"] or farmer["dist_name"],
        "area_ha": round(farm["area_hectares"] or 1.0, 2),
        "field_name": farm["field_name"],
        "crop": season["crop_type"],
        "year": season["year"],
        "ndvi": round(ndvi, 3) if ndvi is not None else None,
        "ndvi_status": ndvi_status,
        "health_score": round(season["final_health_score"], 1),
        "risk_level": season["risk_level"],
        "loan_decision": season["loan_decision"],
        "predicted_yield_kg_ha": round(season["predicted_yield"], 0),
        "npk_intensity_kg_ha": season["npk_input"],
        "irrigation_ratio": round(season["irrigation_ratio"], 3) if season["irrigation_ratio"] else None,
        "wdi": round(season["wdi_used"], 3) if season["wdi_used"] else None,
        "soil_health_score": round(season["soil_score_used"], 2) if season["soil_score_used"] else None,
        "kharif_rain_mm": session_safe(season["kharif_rain_used"]),
        "active_alerts": alerts,
    }


def session_safe(val):
    return round(float(val), 2) if val is not None else None
