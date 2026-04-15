"""
services/agro_service.py — Agromonitoring API integration
==========================================================
Two async functions:

1. create_agro_polygon  → POST a GeoJSON polygon, get back a polygon_id
2. get_satellite_data   → Fetch NDVI + weather + soil for an existing polygon_id

Both functions:
  - Use httpx for async HTTP calls
  - Return real data when AGRO_API_KEY is set in the environment
  - Fall back to realistic mock data if no key is present (dev/test mode)
  - Never raise unhandled exceptions — always return a dict

Agromonitoring API docs: https://agromonitoring.com/api
"""

import os
import random
import logging
import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

AGRO_API_KEY   = os.getenv("AGRO_API_KEY", "")
AGRO_BASE_URL  = "http://agromonitoring.com/agromonitoring/v1.0"
HTTP_TIMEOUT   = 15.0   # seconds


# ─────────────────────────────────────────────────────────────────────────────
# 1. Create Polygon
# ─────────────────────────────────────────────────────────────────────────────

async def create_agro_polygon(
    field_name: str,
    coordinates: list[list[float]],   # [[lon, lat], ...]
) -> dict:
    """
    Registers a GeoJSON polygon with the Agromonitoring API.

    Args:
        field_name:    Human-readable name stored in Agromonitoring
        coordinates:   List of [longitude, latitude] pairs (Leaflet format)
                       The ring must be closed (first == last point).

    Returns:
        {
          "polygon_id": str,
          "name": str,
          "area": float,   # hectares (returned by Agromonitoring)
          "source": "agromonitoring" | "mock"
        }
    """
    # Ensure ring is closed
    coords = list(coordinates)
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    if not AGRO_API_KEY:
        logger.warning("AGRO_API_KEY not set — returning mock polygon_id")
        return _mock_polygon(field_name)

    payload = {
        "name": field_name,
        "geo_json": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{AGRO_BASE_URL}/polygons",
                params={"appid": AGRO_API_KEY},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "polygon_id": data.get("id", ""),
                "name":       data.get("name", field_name),
                "area":       data.get("area", 0.0),
                "source":     "agromonitoring",
            }
    except httpx.HTTPStatusError as e:
        logger.error("Agromonitoring polygon creation failed: %s", e)
        # Graceful fallback so the rest of the flow can continue
        return _mock_polygon(field_name)
    except Exception as e:
        logger.error("Unexpected error creating Agro polygon: %s", e)
        return _mock_polygon(field_name)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Get Satellite Data (NDVI + soil + weather)
# ─────────────────────────────────────────────────────────────────────────────

async def get_satellite_data(polygon_id: str) -> dict:
    """
    Fetches NDVI stats, soil data, and current weather for a polygon.

    Calls 3 Agromonitoring endpoints in sequence:
      /image/search   → list of satellite imagery
      /soil           → soil moisture + temperature
      /weather        → current air temperature + humidity

    Args:
        polygon_id:   The ID returned by create_agro_polygon

    Returns a flat dict with keys:
        ndvi_mean, ndvi_max, ndvi_std,
        soil_moisture, soil_temp_surface,
        air_temp, humidity, cloud_cover,
        satellite_image_date,
        source ("agromonitoring" | "mock")
    """
    if not AGRO_API_KEY or polygon_id.startswith("mock_"):
        logger.info("Using mock satellite data for polygon %s", polygon_id)
        return _mock_satellite_data()

    now_ts  = int(datetime.datetime.utcnow().timestamp())
    ago_ts  = now_ts - (30 * 24 * 3600)   # 30 days back

    ndvi_data    = {}
    soil_data    = {}
    weather_data = {}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # ── a) Latest satellite image + NDVI stats ────────────────────────
            search_resp = await client.get(
                f"{AGRO_BASE_URL}/image/search",
                params={
                    "appid":  AGRO_API_KEY,
                    "polyid": polygon_id,
                    "from":   ago_ts,
                    "to":     now_ts,
                },
            )
            search_resp.raise_for_status()
            images = search_resp.json()

            if images:
                latest = images[0]   # Agromonitoring returns newest first
                ndvi_stats_url = latest.get("stats", {}).get("ndvi", "")
                image_date_ts  = latest.get("dt", now_ts)
                image_date     = datetime.date.fromtimestamp(image_date_ts).isoformat()

                if ndvi_stats_url:
                    stats_resp = await client.get(
                        ndvi_stats_url,
                        params={"appid": AGRO_API_KEY},
                    )
                    stats_resp.raise_for_status()
                    stats = stats_resp.json()
                    ndvi_data = {
                        "ndvi_mean":           stats.get("mean",  0.0),
                        "ndvi_max":            stats.get("max",   0.0),
                        "ndvi_std":            stats.get("std",   0.0),
                        "satellite_image_date": image_date,
                    }

            # ── b) Soil data ──────────────────────────────────────────────────
            soil_resp = await client.get(
                f"{AGRO_BASE_URL}/soil",
                params={"appid": AGRO_API_KEY, "polyid": polygon_id},
            )
            soil_resp.raise_for_status()
            soil_json = soil_resp.json()
            soil_data = {
                "soil_moisture":      soil_json.get("moisture", None),
                "soil_temp_surface":  soil_json.get("t0",       None),
            }

            # ── c) Current weather ────────────────────────────────────────────
            wx_resp = await client.get(
                f"{AGRO_BASE_URL}/weather",
                params={"appid": AGRO_API_KEY, "polyid": polygon_id},
            )
            wx_resp.raise_for_status()
            wx_json = wx_resp.json()
            weather_data = {
                "air_temp":    wx_json.get("main", {}).get("temp",     None),
                "humidity":    wx_json.get("main", {}).get("humidity", None),
                "cloud_cover": wx_json.get("clouds", {}).get("all",    None),
            }

        # Temperature comes in Kelvin from OWM-based API → convert to Celsius
        if weather_data.get("air_temp") and weather_data["air_temp"] > 200:
            weather_data["air_temp"] = round(weather_data["air_temp"] - 273.15, 2)

        return {
            **ndvi_data,
            **soil_data,
            **weather_data,
            "source": "agromonitoring",
        }

    except httpx.HTTPStatusError as e:
        logger.error("Agromonitoring satellite fetch failed: %s", e)
        return _mock_satellite_data()
    except Exception as e:
        logger.error("Unexpected error fetching satellite data: %s", e)
        return _mock_satellite_data()


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers (used when no API key or in tests)
# ─────────────────────────────────────────────────────────────────────────────

def _mock_polygon(field_name: str) -> dict:
    """Returns a plausible mock polygon response for dev/test."""
    mock_id = f"mock_{abs(hash(field_name)) % 10_000_000:07d}"
    return {
        "polygon_id": mock_id,
        "name":       field_name,
        "area":       round(random.uniform(0.5, 5.0), 2),
        "source":     "mock",
    }


def _mock_satellite_data() -> dict:
    """Returns realistic mock satellite + weather data for dev/test."""
    ndvi = round(random.uniform(0.30, 0.75), 3)
    return {
        "ndvi_mean":            ndvi,
        "ndvi_max":             round(ndvi + random.uniform(0.05, 0.20), 3),
        "ndvi_std":             round(random.uniform(0.02, 0.12), 3),
        "soil_moisture":        round(random.uniform(0.08, 0.40), 3),
        "soil_temp_surface":    round(random.uniform(22.0, 38.0), 2),
        "air_temp":             round(random.uniform(20.0, 38.0), 2),
        "humidity":             round(random.uniform(40.0, 85.0), 1),
        "cloud_cover":          round(random.uniform(0.0,  80.0), 1),
        "satellite_image_date": datetime.date.today().isoformat(),
        "source":               "mock",
    }
