"""
chatbot/tools/get_weather.py — Tool B
======================================
Fetches real-time weather and 7-day forecast for the farmer's farm polygon
using the AgroMonitoring API.

Flow:
  1. Look up the farmer's polygon_id from farm_fields table.
  2. If no polygon_id stored, register a new polygon with AgroMonitoring.
  3. Fetch current weather for that polygon.
  4. Fetch 7-day forecast.
  5. Fetch soil moisture data.
  6. Return combined structured result with irrigation advice.

Called when farmer asks:
  "Aaj barish hogi kya?"
  "Kya mujhe irrigation karni chahiye?"
  "Kal ka temperature kitna hoga?"
  "Drought risk hai kya meri field mein?"
"""

import os
import json
import logging
import asyncio
from typing import Optional

import httpx
from langchain_core.tools import tool
from chatbot.db import get_db_connection

logger = logging.getLogger(__name__)

AGRO_KEY = os.getenv("AGRO_API_KEY") or os.getenv("AGROMONITORING_API_KEY", "")
BASE_URL  = "https://agromonitoring.com/agro/1.0"
POLY_URL  = "https://agromonitoring.com/agrodata/v1/polygons"

# kelvin → celsius
def k_to_c(k: float) -> float:
    return round(k - 273.15, 1)


async def _register_polygon(client: httpx.AsyncClient, farm_record) -> Optional[str]:
    """Registers the farm's GeoJSON polygon with AgroMonitoring and returns the poly_id."""
    farmer_id_short = str(farm_record.get("farmer_id", "unknown"))[:8]
    geojson = farm_record.get("polygon_geojson")

    if not geojson:
        # Build a minimal polygon from centroid if no GeoJSON stored
        lat = farm_record["center_lat"]
        lon = farm_record["center_lon"]
        delta = 0.01  # ~1 km bounding box
        geojson = {
            "type": "Polygon",
            "coordinates": [[
                [lon - delta, lat - delta],
                [lon + delta, lat - delta],
                [lon + delta, lat + delta],
                [lon - delta, lat + delta],
                [lon - delta, lat - delta],
            ]],
        }

    payload = {
        "name": f"farm_{farmer_id_short}",
        "geo_json": {
            "type": "Feature",
            "properties": {},
            "geometry": geojson,
        },
    }
    try:
        resp = await client.post(
            POLY_URL,
            params={"appid": AGRO_KEY},
            json=payload,
            timeout=12,
        )
        data = resp.json()
        return data.get("id") or data.get("_id")
    except Exception as ex:
        logger.warning("AgroMonitoring polygon registration failed: %s", ex)
        return None


async def _fetch_weather_mock(farm_record) -> dict:
    """Returns realistic mock weather data when AgroMonitoring key is absent."""
    lat = farm_record.get("center_lat", 28.6)
    logger.info("get_weather: using mock data (no AGRO_API_KEY configured)")
    return {
        "source": "mock",
        "current_temp_c": 32.0,
        "humidity_pct": 68,
        "current_rain_mm": 0.0,
        "wind_kmh": 12.5,
        "weather_description": "partly cloudy (mock data — configure AGRO_API_KEY for live data)",
        "soil_moisture": 0.35,
        "forecast_7_days": [
            {"day": i + 1, "rain_mm": [0, 0, 5, 12, 0, 0, 3][i],
             "temp_max_c": 33 - i * 0.5, "humidity_pct": 65 + i}
            for i in range(7)
        ],
        "total_rain_next_7d_mm": 20.0,
        "irrigation_advice": "Irrigate recommended — less than 30 mm rain expected in 7 days.",
        "note": "Live weather disabled. Set AGRO_API_KEY in .env for real data.",
    }


@tool
async def get_weather(farmer_id: str) -> dict:
    """
    Fetches current weather conditions and 7-day forecast for the farmer's
    registered farm polygon using AgroMonitoring API.
    Use when farmer asks about rain forecast, temperature, irrigation advice,
    drought risk, or any weather-related question.

    Args:
        farmer_id: UUID string of the farmer
    """
    # ── 1. Load farm info from DB ──────────────────────────────────────────────
    try:
        async with get_db_connection() as conn:
            farm = await conn.fetchrow(
                """
                SELECT id, farmer_id, polygon_id, polygon_geojson,
                       center_lat, center_lon, city_name, state_name
                FROM   farm_fields
                WHERE  farmer_id = $1
                ORDER  BY created_at DESC
                LIMIT  1
                """,
                farmer_id,
            )
    except Exception as exc:
        logger.error("get_weather DB error: %s", exc)
        return {"error": True, "message": f"Database error: {exc}"}

    if not farm:
        return {
            "error": True,
            "message": "No farm field registered for this farmer. Please register a field first.",
        }

    # ── 2. Fall back to mock if no API key ────────────────────────────────────
    if not AGRO_KEY:
        return await _fetch_weather_mock(farm)

    # ── 3. Get or register polygon ────────────────────────────────────────────
    poly_id = farm.get("polygon_id")

    async with httpx.AsyncClient() as client:
        if not poly_id or poly_id.startswith("mock-"):
            poly_id = await _register_polygon(client, farm)
            if not poly_id:
                return await _fetch_weather_mock(farm)

        try:
            # ── 4. Current weather ─────────────────────────────────────────────
            w_resp = await client.get(
                f"{BASE_URL}/weather",
                params={"polyid": poly_id, "appid": AGRO_KEY},
                timeout=12,
            )
            w = w_resp.json()

            # ── 5. 7-day forecast ──────────────────────────────────────────────
            f_resp = await client.get(
                f"{BASE_URL}/weather/forecast",
                params={"polyid": poly_id, "appid": AGRO_KEY},
                timeout=12,
            )
            forecast_raw = f_resp.json()

            # ── 6. Soil data ───────────────────────────────────────────────────
            s_resp = await client.get(
                f"{BASE_URL}/soil",
                params={"polyid": poly_id, "appid": AGRO_KEY},
                timeout=12,
            )
            soil = s_resp.json()

        except Exception as exc:
            logger.warning("AgroMonitoring API error: %s — using mock.", exc)
            return await _fetch_weather_mock(farm)

    # ── 7. Parse forecast ─────────────────────────────────────────────────────
    forecast_7d = []
    for i, day in enumerate(forecast_raw[:7]):
        rain_3h  = day.get("rain", {}).get("3h", 0) or 0
        rain_day = round(rain_3h * 8, 2)   # 3-hour chunks → daily estimate
        forecast_7d.append({
            "day": i + 1,
            "rain_mm": rain_day,
            "temp_max_c": k_to_c(day["main"]["temp_max"]),
            "humidity_pct": day["main"]["humidity"],
        })

    total_rain_7d = sum(d["rain_mm"] for d in forecast_7d)
    irr_advice = (
        "Hold irrigation — sufficient rain forecast in next 7 days."
        if total_rain_7d > 30 else
        "Irrigate recommended — low rain expected in the next 7 days."
    )

    return {
        "error": False,
        "source": "agromonitoring",
        "location": f"{farm.get('city_name', '')}, {farm.get('state_name', '')}",
        "current_temp_c": k_to_c(w["main"]["temp"]),
        "feels_like_c": k_to_c(w["main"].get("feels_like", w["main"]["temp"])),
        "humidity_pct": w["main"]["humidity"],
        "current_rain_mm": w.get("rain", {}).get("1h", 0) or 0,
        "wind_kmh": round(w["wind"]["speed"] * 3.6, 1),
        "weather_description": w["weather"][0]["description"] if w.get("weather") else "N/A",
        "soil_moisture": soil.get("moisture"),
        "soil_temp_c": k_to_c(soil["t0"]) if soil.get("t0") else None,
        "forecast_7_days": forecast_7d,
        "total_rain_next_7d_mm": round(total_rain_7d, 1),
        "irrigation_advice": irr_advice,
    }
