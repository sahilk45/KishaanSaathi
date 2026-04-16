"""
chatbot/tools/get_market_price.py — Tool C
==========================================
Fetches live mandi (market) crop prices from Agmarknet API (data.gov.in).
Implements a two-step conversational mandi selection flow:
  Step 1: If mandi_name not provided → return list of mandis in farmer's district.
  Step 2: If mandi_name provided → fetch live price from Agmarknet API.

Called when farmer asks:
  "Mere gehun ka bhav kya hai?"
  "Aaj mandi price kya chal raha hai?"
  "Kab bechna chahiye?"
"""

import os
import json
import logging

import httpx
from langchain_core.tools import tool
from chatbot.db import get_db_connection

logger = logging.getLogger(__name__)

AGMARKNET_API_KEY = os.getenv("AGMARKNET_API_KEY", "")
AGMARKNET_URL     = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

# ── Lazy-load mandi master JSON (avoids import-time crash if path wrong) ──────
_MANDI_DATA: dict | None = None

def _get_mandi_data() -> dict:
    global _MANDI_DATA
    if _MANDI_DATA is not None:
        return _MANDI_DATA
    # Resolve path — try env var, then default clean name, then the original (1) name
    candidates = [
        os.getenv("MANDI_JSON_PATH", ""),
        "./data/mandi_master.json",
        "./data/mandi_master (1).json",
    ]
    for path in candidates:
        path = path.strip().strip('"')
        if not path:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                _MANDI_DATA = json.load(f)
            logger.info("✅ mandi_master.json loaded from %s — %d states", path, len(_MANDI_DATA))
            return _MANDI_DATA
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as e:
            logger.error("mandi_master.json JSON error at %s: %s", path, e)
            continue
    logger.warning("mandi_master.json not found in any candidate path. Mandi lookup will be unavailable.")
    _MANDI_DATA = {}
    return _MANDI_DATA


async def _get_farm_context(farmer_id: str) -> dict:
    """Fetch state, district, and most recent crop for this farmer."""
    async with get_db_connection() as conn:
        farm = await conn.fetchrow(
            """
            SELECT ff.city_name, ff.state_name, f.state_name AS farmer_state,
                   f.dist_name AS farmer_dist
            FROM   farm_fields ff
            JOIN   farmers f ON f.id = ff.farmer_id
            WHERE  ff.farmer_id = $1
            ORDER  BY ff.created_at DESC
            LIMIT  1
            """,
            farmer_id,
        )
        season = await conn.fetchrow(
            """
            SELECT fp.crop_type
            FROM   field_predictions fp
            JOIN   farm_fields ff ON ff.id = fp.field_id
            WHERE  ff.farmer_id = $1
            ORDER  BY fp.year DESC, fp.calculated_at DESC
            LIMIT  1
            """,
            farmer_id,
        )

    state    = (farm["state_name"] if farm else None) or (farm["farmer_state"] if farm else "Unknown")
    district = (farm["city_name"]  if farm else None) or (farm["farmer_dist"]  if farm else "Unknown")
    crop     = season["crop_type"] if season else "Unknown"

    # Convert model crop_type column names to clean display names
    clean_crop = (
        crop.replace("YIELD (Kg per ha)", "")
            .replace("YIELD", "")
            .replace(".Kg.per.ha.", "")
            .replace(".", " ")
            .strip()
            .title()
    )

    return {"state": state, "district": district, "crop": crop, "crop_display": clean_crop}


def _find_mandis(state: str, district: str) -> list[str]:
    """Case-insensitive lookup of mandis for a state+district combination."""
    mandi_data = _get_mandi_data()
    # Try exact match first
    mandis = mandi_data.get(state, {}).get(district, [])
    if mandis:
        return mandis

    # Try case-insensitive fallback
    for s_key, districts in mandi_data.items():
        if s_key.lower() == state.lower():
            for d_key, mandi_list in districts.items():
                if d_key.lower() == district.lower():
                    return mandi_list
    return []


@tool
async def get_market_price(farmer_id: str, mandi_name: str = "") -> dict:
    """
    Fetches current crop price (min, max, modal) from Agmarknet API for a specific mandi.
    If mandi_name is not provided, returns the list of available mandis in farmer's district
    so the LLM can ask the farmer to choose one.
    Use when farmer asks about crop prices, market rates, or where to sell.

    Args:
        farmer_id:  UUID of the farmer
        mandi_name: exact mandi name (optional — if empty, returns mandi list for district)
    """
    try:
        farm_ctx = await _get_farm_context(farmer_id)
    except Exception as exc:
        logger.error("get_market_price DB error: %s", exc)
        return {"error": True, "message": f"Database error: {str(exc)}"}

    state    = farm_ctx["state"]
    district = farm_ctx["district"]
    crop     = farm_ctx["crop"]
    crop_display = farm_ctx["crop_display"]

    # ── Step 1: Return mandi list if no mandi selected yet ────────────────────
    if not mandi_name.strip():
        mandis = _find_mandis(state, district)
        if not mandis:
            return {
                "status": "no_mandis_found",
                "state": state,
                "district": district,
                "crop": crop_display,
                "message": (
                    f"No mandi data found for {district}, {state}. "
                    "Please provide the mandi name manually."
                ),
            }
        return {
            "status": "mandi_selection_needed",
            "state": state,
            "district": district,
            "crop": crop_display,
            "available_mandis": mandis,
            "message": (
                f"The following mandis are available in {district}, {state}: "
                f"{', '.join(mandis)}. Please ask the farmer which mandi they want prices for."
            ),
        }

    # ── Step 2: Fetch price from Agmarknet ────────────────────────────────────
    if not AGMARKNET_API_KEY:
        # Mock response when API key not configured
        logger.info("get_market_price: using mock data (no AGMARKNET_API_KEY)")
        return {
            "status": "success",
            "source": "mock",
            "crop": crop_display,
            "mandi": mandi_name,
            "state": state,
            "date": "2026-04-16",
            "min_price_per_quintal": 2050.0,
            "max_price_per_quintal": 2380.0,
            "modal_price_per_quintal": 2250.0,
            "note": (
                "Mock prices shown — configure AGMARKNET_API_KEY for live prices. "
                "Modal price is the most commonly traded price."
            ),
        }

    params = {
        "api-key": AGMARKNET_API_KEY,
        "format": "json",
        "limit": "10",
        "filters[state.keyword]": state,
        "filters[market]": mandi_name,
        "filters[commodity]": crop_display,
    }

    try:
        resp = httpx.get(AGMARKNET_URL, params=params, timeout=12)
        data = resp.json()
    except Exception as exc:
        logger.error("Agmarknet API error: %s", exc)
        return {"error": True, "message": f"Agmarknet API error: {str(exc)}"}

    if not data.get("records") or data.get("total", 0) == 0:
        # Try without state filter (broader search)
        params.pop("filters[state.keyword]", None)
        try:
            resp2 = httpx.get(AGMARKNET_URL, params=params, timeout=12)
            data = resp2.json()
        except Exception:
            pass

    if not data.get("records") or len(data["records"]) == 0:
        return {
            "status": "no_data",
            "crop": crop_display,
            "mandi": mandi_name,
            "state": state,
            "message": (
                f"No price data found for {crop_display} at {mandi_name} today. "
                "The mandi may not have reported prices yet. Try again later or check a nearby mandi."
            ),
        }

    rec = data["records"][0]
    modal  = float(rec.get("modal_price", 0) or 0)
    min_p  = float(rec.get("min_price", 0)   or 0)
    max_p  = float(rec.get("max_price", 0)   or 0)

    return {
        "status": "success",
        "source": "agmarknet",
        "crop": crop_display,
        "mandi": mandi_name,
        "state": state,
        "date": rec.get("arrival_date", "today"),
        "min_price_per_quintal": min_p,
        "max_price_per_quintal": max_p,
        "modal_price_per_quintal": modal,
        "note": (
            "Modal price is the most commonly traded price — use this for selling decisions. "
            "Prices are in INR per quintal (100 kg)."
        ),
    }
