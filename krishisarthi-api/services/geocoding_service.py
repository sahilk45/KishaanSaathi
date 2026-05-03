"""
services/geocoding_service.py
============================
Reverse geocoding helper for converting latitude/longitude into city + state.

Uses OpenStreetMap Nominatim API (no API key required).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


async def reverse_geocode_city_state(
    latitude: float,
    longitude: float,
) -> dict[str, Optional[str]]:
    """
    Reverse geocodes coordinates into city and state.

    Returns:
        {
            "city_name": Optional[str],
            "state_name": Optional[str],
            "source": "nominatim" | "fallback"
        }
    """
    params = {
        "format": "jsonv2",
        "lat": latitude,
        "lon": longitude,
        "addressdetails": 1,
        "zoom": 12,
    }

    headers = {
        "User-Agent": "KishanSaathi/1.0 (reverse-geocoding)",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(NOMINATIM_REVERSE_URL, params=params, headers=headers)
            resp.raise_for_status()
            payload = resp.json()

        address = payload.get("address", {}) if isinstance(payload, dict) else {}

        city_name = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
            or address.get("suburb")
        )
        state_name = address.get("state") or address.get("region")

        return {
            "city_name": city_name,
            "state_name": state_name,
            "source": "nominatim",
        }

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Reverse geocode failed for lat=%s lon=%s: %s",
            latitude,
            longitude,
            exc,
        )
        return {
            "city_name": None,
            "state_name": None,
            "source": "fallback",
        }
