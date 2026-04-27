"""
services/apmc_service.py
========================
APMC mandi master loading + data.gov.in fetch + synthetic history simulation.

Flow:
1) Load state -> district -> market hierarchy from mandi_master.json
2) Fetch latest mandi record from data.gov API
3) Simulate previous N-1 days around latest real values
4) Return 25-day (configurable) min/max/modal time-series for frontend tables/charts
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

DATA_GOV_MANDI_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
_DEFAULT_MANDI_MASTER_PATH = Path(__file__).resolve().parents[1] / "data" / "mandi_master.json"
MANDI_MASTER_PATH = Path(os.getenv("MANDI_MASTER_JSON_PATH", str(_DEFAULT_MANDI_MASTER_PATH))).expanduser().resolve()
BACKEND_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def get_apmc_api_key() -> str:
    """Loads and returns APMC API key from backend .env or process env."""
    load_dotenv(dotenv_path=BACKEND_ENV_PATH, override=True)
    return os.getenv("APMC_MANDI_API_KEY", "").strip().strip('"').strip("'")


def load_mandi_master(path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """Loads mandi master dictionary from local JSON file."""
    target_path = path or MANDI_MASTER_PATH

    if not target_path.exists():
        return {
            "Maharashtra": {
                "Pune": ["Pune APMC", "Baramati APMC"],
            }
        }

    with target_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    # Normalize to expected shape and stable ordering.
    normalized: dict[str, dict[str, list[str]]] = {}

    for state_name, district_map in payload.items():
        if not isinstance(state_name, str) or not isinstance(district_map, dict):
            continue

        state_bucket: dict[str, list[str]] = {}

        for district_name, markets in district_map.items():
            if not isinstance(district_name, str) or not isinstance(markets, list):
                continue

            clean_markets = sorted({str(market).strip() for market in markets if str(market).strip()})
            if clean_markets:
                state_bucket[district_name.strip()] = clean_markets

        if state_bucket:
            normalized[state_name.strip()] = dict(sorted(state_bucket.items(), key=lambda item: item[0]))

    return dict(sorted(normalized.items(), key=lambda item: item[0]))


def is_valid_market_selection(
    master: dict[str, dict[str, list[str]]],
    state: str,
    district: str,
    market: str,
) -> bool:
    """Checks whether selected state/district/market exists in loaded master data."""
    district_map = master.get(state)
    if not district_map:
        return False

    markets = district_map.get(district)
    if not markets:
        return False

    return market in markets


def _parse_api_date(value: str | None) -> dt.date | None:
    if not value:
        return None

    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _simulate_series(
    latest_date: dt.date,
    min_price: float,
    max_price: float,
    modal_price: float,
    days: int,
) -> list[dict[str, Any]]:
    """
    Creates ascending date-series with latest real value on last day and
    simulated historical values for previous days.
    """
    rows: list[dict[str, Any]] = []

    modal_base = max(1.0, modal_price)
    min_base = max(0.0, min_price)
    max_base = max(min_base, max_price)

    for offset in range(days - 1, -1, -1):
        day = latest_date - dt.timedelta(days=offset)

        if offset == 0:
            row_min = round(min_base, 2)
            row_max = round(max_base, 2)
            row_modal = round(modal_base, 2)
        else:
            drift = random.randint(-70, 70)
            synthetic_modal = max(1.0, modal_base + drift)
            down_spread = random.randint(30, 180)
            up_spread = random.randint(30, 180)
            synthetic_min = max(0.0, synthetic_modal - down_spread)
            synthetic_max = max(synthetic_min, synthetic_modal + up_spread)

            row_min = round(synthetic_min, 2)
            row_max = round(synthetic_max, 2)
            row_modal = round(synthetic_modal, 2)

        rows.append(
            {
                "arrival_date": day.isoformat(),
                "min_price": row_min,
                "max_price": row_max,
                "modal_price": row_modal,
            }
        )

    return rows


async def fetch_and_simulate_history(
    state: str,
    district: str,
    market: str,
    commodity: str,
    days: int = 25,
) -> dict[str, Any]:
    """
    Fetches latest mandi prices for selected filters and simulates historical rows.

    Returns:
        {
          state, district, market, commodity,
          source,
          latest_real_date,
          records: [{arrival_date, min_price, max_price, modal_price}, ...]
        }
    """
    days = max(1, min(days, 90))
    api_key = get_apmc_api_key()

    if not api_key:
        raise RuntimeError("APMC_MANDI_API_KEY is missing. Set it in krishisarthi-api/.env")

    params = {
        "api-key": api_key,
        "format": "json",
        "limit": 100,
        "filters[state.keyword]": state,
        "filters[district]": district,
        "filters[market]": market,
        "filters[commodity]": commodity,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(DATA_GOV_MANDI_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            records = []

        best = None
        best_date = None

        for item in records:
            if not isinstance(item, dict):
                continue

            parsed_date = _parse_api_date(item.get("arrival_date"))
            if parsed_date is None:
                continue

            if best_date is None or parsed_date > best_date:
                best = item
                best_date = parsed_date

        if not best or best_date is None:
            raise ValueError(
                "No mandi price records found for selected state/district/market/commodity. Try another commodity or mandi."
            )

        latest_min = _to_float(best.get("min_price"), 0.0)
        latest_max = _to_float(best.get("max_price"), latest_min)
        latest_modal = _to_float(best.get("modal_price"), latest_min)

        if latest_max < latest_min:
            latest_max = latest_min

        if not (latest_min <= latest_modal <= latest_max):
            latest_modal = max(latest_min, min(latest_modal, latest_max))

        rows = _simulate_series(best_date, latest_min, latest_max, latest_modal, days)

        return {
            "state": state,
            "district": district,
            "market": market,
            "commodity": commodity,
            "source": "live-plus-simulated",
            "latest_real_date": best_date.isoformat(),
            "records": rows,
        }

    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"APMC API request failed with status {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("APMC API network error while fetching mandi prices") from exc
