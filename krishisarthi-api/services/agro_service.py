"""
services/agro_service.py — Agromonitoring API integration
==========================================================
Key integrations:
1) POST /polygons
2) GET  /weather
3) GET  /soil
4) GET  /image/search (start/end)
5) GET  stats.ndvi URL (from image/search response)

This service returns both:
- compact satellite values for prediction flow (`get_satellite_data`)
- rich snapshot payload for frontend map overlays (`fetch_agro_snapshot`)
"""

from __future__ import annotations

import datetime
import logging
import os
import random
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from logger_config import get_logger

logger = get_logger(__name__)

AGRO_API_KEY = os.getenv("AGRO_API_KEY", "").strip()
AGRO_BASE_URL = os.getenv("AGRO_BASE_URL", "https://api.agromonitoring.com/agro/1.0").rstrip("/")
HTTP_TIMEOUT = 15.0  # seconds


def _default_time_range(start_ts: Optional[int], end_ts: Optional[int]) -> tuple[int, int]:
    now_ts = int(datetime.datetime.utcnow().timestamp())
    start = start_ts if isinstance(start_ts, int) and start_ts > 0 else now_ts - (30 * 24 * 3600)
    end = end_ts if isinstance(end_ts, int) and end_ts > 0 else now_ts

    if end < start:
        start, end = end, start

    return start, end


def _ensure_closed_ring(coords: list[list[float]]) -> list[list[float]]:
    ring = list(coords)
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _extract_ndvi_tile_url(image_payload: dict[str, Any]) -> Optional[str]:
    candidates: list[Optional[str]] = [
        image_payload.get("tile", {}).get("ndvi") if isinstance(image_payload.get("tile"), dict) else None,
        image_payload.get("image", {}).get("ndvi") if isinstance(image_payload.get("image"), dict) else None,
        image_payload.get("ndvi"),
    ]

    tile_value = image_payload.get("tile")
    if isinstance(tile_value, str) and "ndvi" in tile_value.lower():
        candidates.append(tile_value)

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate

    return None


def _with_appid_if_missing(url: str, appid: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "appid" not in query:
        query["appid"] = [appid]
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


async def _fetch_image_search(
    client: httpx.AsyncClient,
    polygon_id: str,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    primary_params = {
        "polyid": polygon_id,
        "start": start_ts,
        "end": end_ts,
        "appid": AGRO_API_KEY,
    }

    fallback_params = {
        "polyid": polygon_id,
        "from": start_ts,
        "to": end_ts,
        "appid": AGRO_API_KEY,
    }

    try:
        response = await client.get(f"{AGRO_BASE_URL}/image/search", params=primary_params)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError:
        response = await client.get(f"{AGRO_BASE_URL}/image/search", params=fallback_params)
        response.raise_for_status()
        payload = response.json()

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


async def create_agro_polygon(
    field_name: str,
    coordinates: list[list[float]],
) -> dict[str, Any]:
    """
    Registers a GeoJSON polygon with Agromonitoring.

    Returns:
        {
          "polygon_id": str,
          "name": str,
          "area": float,
          "source": "agromonitoring" | "mock"
        }
    """
    ring = _ensure_closed_ring(coordinates)

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
                "coordinates": [ring],
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{AGRO_BASE_URL}/polygons",
                params={"appid": AGRO_API_KEY},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return {
            "polygon_id": data.get("id", ""),
            "name": data.get("name", field_name),
            "area": data.get("area", 0.0),
            "source": "agromonitoring",
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Agromonitoring polygon creation failed: %s", exc)
        return _mock_polygon(field_name)


async def fetch_agro_snapshot(
    polygon_id: str,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
) -> dict[str, Any]:
    """
    Fetches full Agro snapshot for frontend use:
    - weather
    - soil
    - image/search list
    - latest NDVI tile URL
    - NDVI stats payload (via stats.ndvi URL)
    """
    start, end = _default_time_range(start_ts, end_ts)

    if not AGRO_API_KEY or not polygon_id or polygon_id.startswith("mock_"):
        logger.info("Using mock agro snapshot for polygon %s", polygon_id)
        return _mock_agro_snapshot(polygon_id, start, end)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            images = await _fetch_image_search(client, polygon_id, start, end)

            latest_image = max(images, key=lambda item: item.get("dt", 0), default={})
            latest_dt = latest_image.get("dt")
            latest_image_date = None
            if isinstance(latest_dt, (int, float)):
                latest_image_date = datetime.date.fromtimestamp(int(latest_dt)).isoformat()

            ndvi_tile_url = _extract_ndvi_tile_url(latest_image)
            ndvi_stats_url = None
            ndvi_stats_payload: dict[str, Any] = {}

            stats_section = latest_image.get("stats") if isinstance(latest_image, dict) else None
            if isinstance(stats_section, dict):
                ndvi_candidate = stats_section.get("ndvi")
                if isinstance(ndvi_candidate, str) and ndvi_candidate.strip():
                    ndvi_stats_url = _with_appid_if_missing(ndvi_candidate, AGRO_API_KEY)

            if ndvi_stats_url:
                stats_resp = await client.get(ndvi_stats_url)
                stats_resp.raise_for_status()
                stats_json = stats_resp.json()
                if isinstance(stats_json, dict):
                    ndvi_stats_payload = stats_json

            soil_resp = await client.get(
                f"{AGRO_BASE_URL}/soil",
                params={"polyid": polygon_id, "appid": AGRO_API_KEY},
            )
            soil_resp.raise_for_status()
            soil_json = soil_resp.json() if isinstance(soil_resp.json(), dict) else {}

            weather_resp = await client.get(
                f"{AGRO_BASE_URL}/weather",
                params={"polyid": polygon_id, "appid": AGRO_API_KEY},
            )
            weather_resp.raise_for_status()
            weather_json = weather_resp.json() if isinstance(weather_resp.json(), dict) else {}

        air_temp = weather_json.get("main", {}).get("temp") if isinstance(weather_json.get("main"), dict) else None
        if isinstance(air_temp, (int, float)) and air_temp > 200:
            air_temp = round(float(air_temp) - 273.15, 2)

        weather = {
            "air_temp": air_temp,
            "humidity": weather_json.get("main", {}).get("humidity") if isinstance(weather_json.get("main"), dict) else None,
            "cloud_cover": weather_json.get("clouds", {}).get("all") if isinstance(weather_json.get("clouds"), dict) else None,
        }

        soil = {
            "soil_moisture": soil_json.get("moisture"),
            "soil_temp_surface": soil_json.get("t0"),
        }

        return {
            "source": "agromonitoring",
            "polygon_id": polygon_id,
            "start": start,
            "end": end,
            "images_count": len(images),
            "latest_image_date": latest_image_date,
            "ndvi_tile_url": ndvi_tile_url,
            "ndvi_stats_url": ndvi_stats_url,
            "ndvi_stats": ndvi_stats_payload,
            "weather": weather,
            "soil": soil,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch agro snapshot for %s: %s", polygon_id, exc)
        return _mock_agro_snapshot(polygon_id, start, end)


async def get_satellite_data(polygon_id: str) -> dict[str, Any]:
    """
    Backward-compatible compact satellite payload used by /predict flow.
    """
    snapshot = await fetch_agro_snapshot(polygon_id)

    ndvi_stats = snapshot.get("ndvi_stats") if isinstance(snapshot.get("ndvi_stats"), dict) else {}
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    soil = snapshot.get("soil") if isinstance(snapshot.get("soil"), dict) else {}

    return {
        "ndvi_mean": ndvi_stats.get("mean"),
        "ndvi_max": ndvi_stats.get("max"),
        "ndvi_std": ndvi_stats.get("std"),
        "satellite_image_date": snapshot.get("latest_image_date"),
        "soil_moisture": soil.get("soil_moisture"),
        "soil_temp_surface": soil.get("soil_temp_surface"),
        "air_temp": weather.get("air_temp"),
        "humidity": weather.get("humidity"),
        "cloud_cover": weather.get("cloud_cover"),
        "ndvi_tile_url": snapshot.get("ndvi_tile_url"),
        "ndvi_stats_url": snapshot.get("ndvi_stats_url"),
        "source": snapshot.get("source", "mock"),
    }


def _mock_polygon(field_name: str) -> dict[str, Any]:
    mock_id = f"mock_{abs(hash(field_name)) % 10_000_000:07d}"
    return {
        "polygon_id": mock_id,
        "name": field_name,
        "area": round(random.uniform(0.5, 5.0), 2),
        "source": "mock",
    }


def _mock_agro_snapshot(polygon_id: str, start: int, end: int) -> dict[str, Any]:
    ndvi = round(random.uniform(0.30, 0.75), 3)
    return {
        "source": "mock",
        "polygon_id": polygon_id,
        "start": start,
        "end": end,
        "images_count": 0,
        "latest_image_date": datetime.date.today().isoformat(),
        "ndvi_tile_url": None,
        "ndvi_stats_url": None,
        "ndvi_stats": {
            "mean": ndvi,
            "max": round(ndvi + random.uniform(0.05, 0.2), 3),
            "std": round(random.uniform(0.02, 0.12), 3),
            "min": round(max(0.0, ndvi - random.uniform(0.03, 0.1)), 3),
        },
        "weather": {
            "air_temp": round(random.uniform(20.0, 38.0), 2),
            "humidity": round(random.uniform(40.0, 85.0), 1),
            "cloud_cover": round(random.uniform(0.0, 80.0), 1),
        },
        "soil": {
            "soil_moisture": round(random.uniform(0.08, 0.40), 3),
            "soil_temp_surface": round(random.uniform(22.0, 38.0), 2),
        },
    }
