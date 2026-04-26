"""
chatbot/tools/get_weather.py — Tool B
======================================
Fetches real-time weather and 7-day forecast using Open-Meteo API.
Open-Meteo is FREE — no API key required.
API docs: https://open-meteo.com/en/docs

Called when farmer asks:
  "Aaj barish hogi kya?"
  "Kya mujhe irrigation karni chahiye?"
  "Kal ka temperature kitna hoga?"
  "Drought risk hai kya meri field mein?"
  "Agle 7 din ka mausam kaisa rahega?"

Does NOT handle market prices — use get_market_price for that.
"""

import logging
from typing import Optional

import httpx
from langchain_core.tools import tool
from chatbot.db import get_db_connection

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


async def _fetch_open_meteo(lat: float, lon: float) -> Optional[dict]:
    """
    Calls Open-Meteo API and returns parsed weather + 7-day forecast.
    Returns None on error.
    """
    params = {
        "latitude":  lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "hourly": "temperature_2m,precipitation,relativehumidity_2m,windspeed_10m",
        "current_weather": "true",
        "timezone": "Asia/Kolkata",
        "forecast_days": 7,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Open-Meteo API error: %s", exc)
        return None

    current = data.get("current_weather", {})
    daily   = data.get("daily", {})
    hourly  = data.get("hourly", {})

    # Current conditions from hourly[0] (most recent hour)
    humidity = (hourly.get("relativehumidity_2m") or [65])[0]
    wind_kmh = current.get("windspeed", 0)       # Open-Meteo already gives km/h

    # WMO weather code → description
    wmo_code = int(current.get("weathercode", 0))
    weather_desc = _wmo_to_text(wmo_code)

    # 7-day forecast
    dates      = daily.get("time", [])
    max_temps  = daily.get("temperature_2m_max", [])
    min_temps  = daily.get("temperature_2m_min", [])
    precip     = daily.get("precipitation_sum", [])
    wmo_codes  = daily.get("weathercode", [])

    forecast_7d = []
    for i in range(min(7, len(dates))):
        forecast_7d.append({
            "day":         i + 1,
            "date":        dates[i] if i < len(dates) else "",
            "rain_mm":     round(float(precip[i] or 0), 1) if i < len(precip) else 0,
            "temp_max_c":  round(float(max_temps[i] or 0), 1) if i < len(max_temps) else 0,
            "temp_min_c":  round(float(min_temps[i] or 0), 1) if i < len(min_temps) else 0,
            "description": _wmo_to_text(int(wmo_codes[i])) if i < len(wmo_codes) else "",
        })

    total_rain_7d = sum(d["rain_mm"] for d in forecast_7d)
    irr_advice = (
        "Irrigation hold karein — agli 7 dinon mein achi barish expected hai."
        if total_rain_7d > 30 else
        "Irrigation karein — agli 7 dinon mein kam barish expected hai (30mm se kam)."
    )

    return {
        "source":                 "open-meteo",
        "current_temp_c":         round(float(current.get("temperature", 0)), 1),
        "humidity_pct":           humidity,
        "current_rain_mm":        round(float((hourly.get("precipitation") or [0])[0]), 1),
        "wind_kmh":               round(wind_kmh, 1),
        "weather_description":    weather_desc,
        "forecast_7_days":        forecast_7d,
        "total_rain_next_7d_mm":  round(total_rain_7d, 1),
        "irrigation_advice":      irr_advice,
        "note": "Live weather from Open-Meteo (free, no API key required).",
    }


def _wmo_to_text(code: int) -> str:
    """Converts WMO weather interpretation code to human-readable text."""
    mapping = {
        0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
        45: "foggy", 48: "icy fog",
        51: "light drizzle", 53: "moderate drizzle", 55: "heavy drizzle",
        61: "slight rain", 63: "moderate rain", 65: "heavy rain",
        71: "slight snow", 73: "moderate snow", 75: "heavy snow",
        80: "slight showers", 81: "moderate showers", 82: "heavy showers",
        95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
    }
    return mapping.get(code, f"code {code}")


@tool
async def get_weather(farmer_id: str) -> dict:
    """
    Fetches current weather and 7-day forecast for the farmer's farm location.

    Use ONLY when farmer asks about:
    - Rain forecast or barish
    - Temperature or garmi/sardi
    - Irrigation timing (sinchai)
    - Drought risk or flood risk
    - Any weather-related question

    Do NOT use for market prices — use get_market_price for that.
    Do NOT use for farm health score — that is in the FARMER PROFILE.

    Args:
        farmer_id: UUID of the farmer
    """
    import uuid as _uuid
    try:
        _uuid.UUID(str(farmer_id))
    except ValueError:
        return {
            "error": True,
            "message": "FATAL ERROR: Invalid farmer_id. DO NOT CALL ANY TOOLS AGAIN.",
        }

    # ── 1. Load farm GPS from DB ───────────────────────────────────────────────
    try:
        async with get_db_connection() as conn:
            farm = await conn.fetchrow(
                """
                SELECT id, center_lat, center_lon, city_name, state_name
                FROM   farm_fields
                WHERE  farmer_id = $1
                ORDER  BY created_at DESC
                LIMIT  1
                """,
                _uuid.UUID(str(farmer_id)),
            )
    except Exception as exc:
        logger.error("get_weather DB error: %s", exc)
        return f"Database error fetching farm location: {exc}. Tell user there is a problem."

    if not farm:
        return "ERROR: Aapka farm register nahi hai. Weather data ke liye farm location hona zaroori hai."

    lat = float(farm["center_lat"] or 28.6)
    lon = float(farm["center_lon"] or 77.2)
    location_name = f"{farm.get('city_name', '') or ''}, {farm.get('state_name', '') or ''}".strip(", ")

    # ── 2. Call Open-Meteo ────────────────────────────────────────────────────
    weather = await _fetch_open_meteo(lat, lon)

    if weather is None:
        # Graceful fallback with location-appropriate defaults
        logger.warning("Open-Meteo failed — returning fallback for lat=%.4f lon=%.4f", lat, lon)
        return (
            f"ERROR: Open-Meteo weather service is currently unavailable for {location_name}. "
            "INSTRUCTION FOR AI: Tell the user that weather data cannot be fetched right now and to check manually."
        )


    logger.info("get_weather: fetched Open-Meteo data for %s (%.4f, %.4f)", location_name, lat, lon)
    
    forecast_str = "\n".join([
        f"- {day['date']}: {day['description']}, Max {day['temp_max_c']}°C, Min {day['temp_min_c']}°C, Rain {day['rain_mm']}mm" 
        for day in weather['forecast_7_days'][:3]  # Only 3 days to save tokens
    ])

    return (
        f"Weather for {location_name}:\n"
        f"Current: {weather['current_temp_c']}°C, {weather['weather_description']}, Humidity: {weather['humidity_pct']}%, Wind: {weather['wind_kmh']}km/h\n"
        f"Rain today: {weather['current_rain_mm']}mm\n\n"
        f"3-Day Forecast:\n{forecast_str}\n\n"
        f"Irrigation Advice: {weather['irrigation_advice']}\n\n"
        "INSTRUCTION FOR AI: Translate this weather and advice to the farmer in Hindi."
    )
