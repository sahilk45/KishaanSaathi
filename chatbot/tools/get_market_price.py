"""
chatbot/tools/get_market_price.py — Tool C (FIXED)
================================================== 
Fetches live mandi (market) crop prices from Agmarknet API (data.gov.in).
Implements a two-step conversational mandi selection flow:
  Step 1: If mandi_name not provided → return list of mandis in farmer's district.
  Step 2: If mandi_name provided → fetch live price from Agmarknet API.

IMPORTANT FIX: All responses are now JSON strings (not plain text or embedded instructions).
This prevents the LLM from getting stuck in an infinite loop trying to interpret
embedded "INSTRUCTION FOR AI" commands.

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

_MANDI_DATA: dict | None = None

def _get_mandi_data() -> dict:
    global _MANDI_DATA
    if _MANDI_DATA is not None:
        return _MANDI_DATA
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
    async with get_db_connection() as conn:
        farm = await conn.fetchrow(
            "SELECT ff.city_name, ff.state_name, f.state_name AS farmer_state, f.dist_name AS farmer_dist FROM farm_fields ff JOIN farmers f ON f.id = ff.farmer_id WHERE ff.farmer_id = $1 ORDER BY ff.created_at DESC LIMIT 1",
            farmer_id,
        )
        season = await conn.fetchrow(
            "SELECT fp.crop_type FROM field_predictions fp JOIN farm_fields ff ON ff.id = fp.field_id WHERE ff.farmer_id = $1 ORDER BY fp.year DESC, fp.calculated_at DESC LIMIT 1",
            farmer_id,
        )

    state    = (farm["state_name"] if farm else None) or (farm["farmer_state"] if farm else None)
    district = (farm["farmer_dist"]  if farm else None) or (farm["city_name"]   if farm else None)
    crop     = season["crop_type"] if season else None

    clean_crop = (
        (crop or "Unknown")
        .replace("YIELD (Kg per ha)", "")
        .replace("YIELD", "")
        .replace(".Kg.per.ha.", "")
        .replace(".", " ")
        .strip()
        .title()
    )

    return {"state": state or "Unknown", "district": district or "Unknown", "crop": crop or "Unknown", "crop_display": clean_crop}


def _find_mandis(state: str, district: str) -> list[str]:
    mandi_data = _get_mandi_data()
    mandis = mandi_data.get(state, {}).get(district, [])
    if mandis:
        return mandis

    for s_key, districts in mandi_data.items():
        if s_key.lower() == state.lower():
            for d_key, mandi_list in districts.items():
                if d_key.lower() == district.lower():
                    return mandi_list
    return []


@tool
async def get_market_price(
    farmer_id: str,
    mandi_name: str = "",
    state: str = "",
    district: str = "",
    crop: str = "",
) -> str:
    """
    Fetches live mandi (market) crop prices from the Agmarknet API.

    Two-step flow:
      Step 1: If mandi_name is empty → returns available APMCs in the farmer's district.
              Show this list to the farmer and ask them to choose a mandi.
      Step 2: If mandi_name is provided → fetches and returns live price for that mandi.

    Call this tool when the farmer asks about mandi prices, bhav, rates, or selling advice.
    Use farmer_id from the FARMER PROFILE. Do NOT call this tool more than once per turn.
    """
    import uuid
    try:
        uuid.UUID(str(farmer_id))
    except ValueError:
        logger.error("FATAL: Invalid farmer_id '%s' passed by AI.", farmer_id)
        error_resp = {"error": True, "message": "FATAL ERROR: The farmer_id provided is invalid. DO NOT CALL ANY TOOLS AGAIN. Answer the user based on the FARMER PROFILE context."}
        return json.dumps(error_resp)

    try:
        farm_ctx = await _get_farm_context(farmer_id)
    except Exception as exc:
        logger.error("get_market_price DB error: %s", exc)
        error_resp = {"error": True, "message": f"Database error fetching farmer context: {str(exc)}. Please tell the user there is a problem and do not retry."}
        return json.dumps(error_resp)

    effective_state    = state.strip()    or farm_ctx["state"]
    effective_district = district.strip() or farm_ctx["district"]
    effective_crop     = crop.strip()     or farm_ctx["crop_display"]

    if effective_state in ("Unknown", "", None) or effective_district in ("Unknown", "", None):
        error_resp = {
            "status": "awaiting_location",
            "error": True,
            "awaiting_user_input": True,
            "message": "Farmer's district or state is not known. Ask the farmer: 'Aap kis district aur state mein hain? Ya kis mandi ka bhav chahiye?'"
        }
        return json.dumps(error_resp)

    if not mandi_name.strip():
        mandis = _find_mandis(effective_state, effective_district)
        if not mandis:
            no_mandis_resp = {
                "status": "no_mandis_found",
                "error": True,
                "district": effective_district,
                "state": effective_state,
                "message": f"No mandi data found for {effective_district}, {effective_state}. Please ask the farmer to provide the mandi name manually."
            }
            return json.dumps(no_mandis_resp)
        mandi_list_resp = {
            "status": "awaiting_mandi_selection",
            "awaiting_user_input": True,
            "available_mandis": mandis,
            "district": effective_district,
            "state": effective_state,
            "message": f"Available mandis in {effective_district}, {effective_state}: {', '.join(mandis)}. Please ask which mandi the farmer prefers."
        }
        return json.dumps(mandi_list_resp)

    if not AGMARKNET_API_KEY:
        logger.info("get_market_price: using mock data (no AGMARKNET_API_KEY)")
        mock_resp = {
            "status": "success",
            "crop": effective_crop,
            "mandi": mandi_name,
            "state": effective_state,
            "prices": {
                "min_price": 2050,
                "max_price": 2380,
                "modal_price": 2250,
                "unit": "₹/quintal"
            },
            "message": f"Mock prices for {effective_crop} at {mandi_name} ({effective_state}): Min ₹2050, Max ₹2380, Modal ₹2250 per quintal."
        }
        return json.dumps(mock_resp)

    params = {
        "api-key": AGMARKNET_API_KEY,
        "format": "json",
        "limit": "10",
        "filters[state.keyword]": effective_state,
        "filters[market]": mandi_name,
        "filters[commodity]": effective_crop,
    }

    try:
        resp = httpx.get(AGMARKNET_URL, params=params, timeout=12)
        data = resp.json()
    except Exception as exc:
        logger.error("Agmarknet API error: %s", exc)
        api_error_resp = {
            "error": True,
            "status": "api_error",
            "message": f"Agmarknet API se connection nahi hua: {str(exc)}. User ko later try karne ko bolo."
        }
        return json.dumps(api_error_resp)

    if not data.get("records") or data.get("total", 0) == 0:
        params.pop("filters[state.keyword]", None)
        try:
            resp2 = httpx.get(AGMARKNET_URL, params=params, timeout=12)
            data = resp2.json()
        except Exception:
            pass

    if not data.get("records") or len(data["records"]) == 0:
        no_data_resp = {
            "status": "no_data",
            "crop": effective_crop,
            "mandi": mandi_name,
            "state": effective_state,
            "error": True,
            "message": f"Aaj {effective_crop} ka price {mandi_name} mandi mein available nahi hai. Mandi ne abhi report nahi ki. User ko later try karne ya nearby mandi check karne ko bolo."
        }
        return json.dumps(no_data_resp)

    rec = data["records"][0]
    modal  = float(rec.get("modal_price", 0) or 0)
    min_p  = float(rec.get("min_price", 0)   or 0)
    max_p  = float(rec.get("max_price", 0)   or 0)

    success_resp = {
        "status": "success",
        "crop": effective_crop,
        "mandi": mandi_name,
        "state": effective_state,
        "arrival_date": rec.get("arrival_date", "today"),
        "prices": {
            "min_price": round(min_p, 2),
            "max_price": round(max_p, 2),
            "modal_price": round(modal, 2),
            "unit": "₹/quintal"
        },
        "message": f"Agmarknet Prices for {effective_crop} at {mandi_name} ({effective_state}) on {rec.get('arrival_date', 'today')}: Min ₹{min_p}/quintal, Max ₹{max_p}/quintal, Modal ₹{modal}/quintal."
    }
    return json.dumps(success_resp)
