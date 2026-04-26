"""
main.py — KishanSaathi FastAPI Application
==========================================
Endpoints:
  GET  /districts                  → Dropdown data (district + state list)
  POST /farmers/register           → Register a new farmer
  POST /farm/register              → Register a field + draw polygon
  POST /predict                    → THE MAIN ENGINE (cache-first prediction)
  GET  /field/{field_id}/history   → All cached predictions for a field
  GET  /health                     → API liveness check

Run with:
  uvicorn main:app --reload --port 8000
"""

import os
import sys

# ── Fix Windows asyncio loop policy for asyncpg SSL ────────────────────────────
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
import datetime
import numpy as np
import pandas as pd
import joblib
from dotenv import load_dotenv

load_dotenv()  # Load .env file into os.environ

# ── Fix GROQ_API_KEY alias: .env uses the typo 'GROK_API_KEY' ───────────────
# The Groq SDK itself looks for GROQ_API_KEY; keep both for compatibility.
if os.getenv("GROK_API_KEY") and not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = os.environ["GROK_API_KEY"]

# ── Structured logging with UTF-8 so emoji don't crash on Windows CP1252 terminals ────
from logger_config import setup_structured_logging, get_logger

setup_structured_logging(
    log_level="INFO",
    log_file=os.getenv("LOG_FILE", None)  # Optional: set LOG_FILE env var to log to file
)

from contextlib import asynccontextmanager
from typing import Optional, Any
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from database import create_pool, create_all_tables
from services.imputation   import impute_weather_from_db
from services.health_score import calculate_health_score
from services.agro_service import create_agro_polygon, get_satellite_data, fetch_agro_snapshot
from services.geocoding_service import reverse_geocode_city_state
from chatbot.agent import run_agent, run_agent_streaming
from chatbot.db import close_pool as close_chatbot_pool  # Bug #5: close chatbot pool on shutdown


logger = get_logger("krishisarthi_api")

# ─────────────────────────────────────────────────────────────────────────────
# Config from environment
# ─────────────────────────────────────────────────────────────────────────────
DATABASE_URL  = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/kishandb"
)
MODEL_DIR          = os.getenv("MODEL_DIR", "Encoder_and_model")

# ── XGBoost training data cutoff year ────────────────────────────────────────
# The model was trained on KrishiTwin_Final_Engineered.csv which ends at 2015.
# Passing year > 2015 causes tree-boundary extrapolation → unrealistic yields.
# FIX: clamp 'year' feature to this value before prediction.
# The ORIGINAL year (e.g. 2026) is still stored in field_predictions and
# returned in the API response — only the model input is clamped.
MAX_TRAINING_YEAR  = 2015

# ─────────────────────────────────────────────────────────────────────────────
# ML Artifacts — loaded ONCE at startup (globals for speed)
# ─────────────────────────────────────────────────────────────────────────────
# Paths relative to this file or absolute via MODEL_DIR env var.
_model    = None
_le_crop  = None
_le_state = None

def _load_artifacts():
    global _model, _le_crop, _le_state
    try:
        _model    = joblib.load(os.path.join(MODEL_DIR, "krishi_twin_xgb_model.pkl"))
        _le_crop  = joblib.load(os.path.join(MODEL_DIR, "crop_encoder.pkl"))
        _le_state = joblib.load(os.path.join(MODEL_DIR, "state_encoder.pkl"))
        
        logger.log_real_data(
            "ml_artifacts_loaded",
            {
                "model_type": "XGBoost",
                "crop_classes": len(_le_crop.classes_),
                "state_classes": len(_le_state.classes_),
                "model_dir": MODEL_DIR,
            },
            source="FILE_SYSTEM"
        )
    except FileNotFoundError as e:
        logger.log_error("ml_artifacts_load_failed", e, context={"model_dir": MODEL_DIR})
        raise RuntimeError(f"Model file missing: {e}") from e


# ── Crop → yield-column mapping (exact column names from the CSV / model) ────
# The model was trained on the melted version of this CSV, so crop_type in
# the API must be one of these exact column names (or a clean alias).
CROP_YIELD_COLUMNS = {
    "RICE YIELD (Kg per ha)":                "RICE YIELD (Kg per ha)",
    "WHEAT.YIELD.Kg.per.ha.":               "WHEAT.YIELD.Kg.per.ha.",
    "MAIZE.YIELD.Kg.per.ha.":               "MAIZE.YIELD.Kg.per.ha.",
    "SUGARCANE YIELD (Kg per ha)":           "SUGARCANE YIELD (Kg per ha)",
    "COTTON.YIELD.Kg.per.ha.":              "COTTON.YIELD.Kg.per.ha.",
    "PEARL MILLET YIELD (Kg per ha)":        "PEARL MILLET YIELD (Kg per ha)",
    "CHICKPEA YIELD (Kg per ha)":            "CHICKPEA YIELD (Kg per ha)",
    "GROUNDNUT YIELD (Kg per ha)":           "GROUNDNUT YIELD (Kg per ha)",
    "KHARIF.SORGHUM.YIELD.Kg.per.ha.":      "KHARIF.SORGHUM.YIELD.Kg.per.ha.",
    "RABI.SORGHUM.YIELD.Kg.per.ha.":        "RABI.SORGHUM.YIELD.Kg.per.ha.",
    "SORGHUM.YIELD.Kg.per.ha.":             "SORGHUM.YIELD.Kg.per.ha.",
    "PEARL.MILLET.YIELD.Kg.per.ha.":        "PEARL.MILLET.YIELD.Kg.per.ha.",
    "FINGER.MILLET.YIELD.Kg.per.ha.":       "FINGER.MILLET.YIELD.Kg.per.ha.",
    "BARLEY.YIELD.Kg.per.ha.":              "BARLEY.YIELD.Kg.per.ha.",
    "PIGEONPEA.YIELD.Kg.per.ha.":           "PIGEONPEA.YIELD.Kg.per.ha.",
    "MINOR.PULSES.YIELD.Kg.per.ha.":        "MINOR.PULSES.YIELD.Kg.per.ha.",
    "SESAMUM.YIELD.Kg.per.ha.":             "SESAMUM.YIELD.Kg.per.ha.",
    "RAPESEED.AND.MUSTARD.YIELD.Kg.per.ha.":"RAPESEED.AND.MUSTARD.YIELD.Kg.per.ha.",
    "SAFFLOWER.YIELD.Kg.per.ha.":           "SAFFLOWER.YIELD.Kg.per.ha.",
    "CASTOR.YIELD.Kg.per.ha.":              "CASTOR.YIELD.Kg.per.ha.",
    "LINSEED.YIELD.Kg.per.ha.":             "LINSEED.YIELD.Kg.per.ha.",
    "SUNFLOWER.YIELD.Kg.per.ha.":           "SUNFLOWER.YIELD.Kg.per.ha.",
    "SOYABEAN.YIELD.Kg.per.ha.":            "SOYABEAN.YIELD.Kg.per.ha.",
    "OILSEEDS.YIELD.Kg.per.ha.":            "OILSEEDS.YIELD.Kg.per.ha.",
}

# Benchmark yields (historical district means — from CSV analysis)
# Used as denominator in yield_score = predicted/benchmark × 100
CROP_BENCHMARKS = {
    "RICE YIELD (Kg per ha)":                1872.1,
    "WHEAT.YIELD.Kg.per.ha.":               2087.2,
    "MAIZE.YIELD.Kg.per.ha.":               1880.7,
    "SUGARCANE YIELD (Kg per ha)":           5619.3,
    "COTTON.YIELD.Kg.per.ha.":               296.7,
    "PEARL MILLET YIELD (Kg per ha)":        1001.1,
    "CHICKPEA YIELD (Kg per ha)":             817.6,
    "GROUNDNUT YIELD (Kg per ha)":           1152.9,
    "KHARIF.SORGHUM.YIELD.Kg.per.ha.":       956.6,
    "RABI.SORGHUM.YIELD.Kg.per.ha.":        1050.4,
    "SORGHUM.YIELD.Kg.per.ha.":              921.8,
    "PEARL.MILLET.YIELD.Kg.per.ha.":        1001.0,
    "FINGER.MILLET.YIELD.Kg.per.ha.":       1104.1,
    "BARLEY.YIELD.Kg.per.ha.":              1823.8,
    "PIGEONPEA.YIELD.Kg.per.ha.":            763.9,
    "MINOR.PULSES.YIELD.Kg.per.ha.":         572.2,
    "SESAMUM.YIELD.Kg.per.ha.":              353.8,
    "RAPESEED.AND.MUSTARD.YIELD.Kg.per.ha.": 791.4,
    "SAFFLOWER.YIELD.Kg.per.ha.":            551.7,
    "CASTOR.YIELD.Kg.per.ha.":               761.1,
    "LINSEED.YIELD.Kg.per.ha.":              473.0,
    "SUNFLOWER.YIELD.Kg.per.ha.":            955.6,
    "SOYABEAN.YIELD.Kg.per.ha.":             997.0,
    "OILSEEDS.YIELD.Kg.per.ha.":             899.1,
}

# ─────────────────────────────────────────────────────────────────────────────
# Lifespan: startup + shutdown
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.log_computation(
        "api_startup_initiated",
        {"status": "initializing"},
        computation_type="application_startup"
    )

    # Load ML artifacts
    _load_artifacts()

    # Create DB connection pool
    app.state.pool = await create_pool(DATABASE_URL)

    # Ensure all tables exist (idempotent)
    await create_all_tables(app.state.pool)

    logger.log_computation(
        "api_startup_complete",
        {"status": "ready"},
        computation_type="application_startup"
    )
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await app.state.pool.close()
    await close_chatbot_pool()   # Bug #5: release chatbot's separate asyncpg pool
    logger.log_computation(
        "api_shutdown_complete",
        {"status": "closed"},
        computation_type="application_shutdown"
    )



# ─────────────────────────────────────────────────────────────────────────────
# App instance
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="KishanSaathi API",
    description="Agritech platform: yield prediction + farm health scoring for Indian farmers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Global exception handlers
# ─────────────────────────────────────────────────────────────────────────────


@app.exception_handler(asyncpg.exceptions.DataError)
async def asyncpg_data_error_handler(request: Request, exc: asyncpg.exceptions.DataError):
    """Catches asyncpg DataError (e.g. invalid UUID format) and returns 422."""
    logger.log_error("db_data_error", exc, context={"path": str(request.url.path)})
    return JSONResponse(
        status_code=422,
        content={"detail": f"Invalid input data: {exc}. Check that all IDs are valid UUIDs."},
    )

@app.exception_handler(asyncpg.exceptions.ForeignKeyViolationError)
async def asyncpg_fk_error_handler(request: Request, exc: asyncpg.exceptions.ForeignKeyViolationError):
    """Catches FK violations and returns 404."""
    logger.log_error("db_fk_violation", exc, context={"path": str(request.url.path)})
    return JSONResponse(
        status_code=404,
        content={"detail": f"Referenced record not found: {exc}"},
    )



# ─────────────────────────────────────────────────────────────────────────────
# Dependency: DB pool from request state
# ─────────────────────────────────────────────────────────────────────────────

async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class FarmerRegisterRequest(BaseModel):
    name:       str  = Field(..., json_schema_extra={"example": "Ramesh Kumar"})
    phone:      str  = Field(..., json_schema_extra={"example": "9876543210"})
    state_name: str  = Field(..., json_schema_extra={"example": "Punjab"})
    dist_name:  str  = Field(..., json_schema_extra={"example": "ludhiana"})


class FarmerRegisterResponse(BaseModel):
    farmer_id:  str
    name:       str
    phone:      str
    state_name: str
    dist_name:  str


class FarmRegisterRequest(BaseModel):
    farmer_id:    UUID = Field(..., description="UUID returned by /farmers/register",
                              json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"})
    field_name:   str  = Field(..., json_schema_extra={"example": "North Field"})
    coordinates:  list[list[float]] = Field(
        ...,
        description="GeoJSON polygon ring as [[lon, lat], ...]. Must be ≥ 4 points.",
        json_schema_extra={"example": [[76.78, 30.73], [76.79, 30.73], [76.79, 30.74], [76.78, 30.74]]}
    )
    area_hectares: Optional[float] = Field(None, json_schema_extra={"example": 1.4})


class FarmRegisterResponse(BaseModel):
    field_id:    str
    polygon_id:  str
    area:        Optional[float]
    source:      str
    city_name:   Optional[str]
    state_name:  Optional[str]
    center_lat:  float
    center_lon:  float


class PredictRequest(BaseModel):
    field_id:     UUID  = Field(..., description="UUID from /farm/register",
                               json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"})
    crop_type:    str  = Field(..., json_schema_extra={"example": "WHEAT.YIELD.Kg.per.ha."})
    npk_input:    float = Field(..., ge=0, le=500, description="NPK intensity kg/ha")
    year:         int  = Field(..., ge=1990, le=2030, json_schema_extra={"example": 2025})
    irrigation_ratio: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="0.0–1.0. Leave null to auto-impute from district history."
    )


class HealthScoreDetail(BaseModel):
    final_health_score: float
    yield_score:        float
    soil_score:         float
    water_score:        float
    climate_score:      float
    ndvi_score:         float
    ndvi_source:        str
    risk_level:         str
    loan_decision:      str


class PredictResponse(BaseModel):
    field_id:           str
    crop_type:          str
    year:               int
    predicted_yield:    float
    benchmark_yield:    Optional[float]
    health:             HealthScoreDetail

    # Imputed weather (for transparency)
    kharif_temp_used:   float
    kharif_rain_used:   float
    rabi_temp_used:     float
    wdi_used:           float
    soil_score_used:    float
    irr_source:         str
    irrigation_used:    float

    # Satellite / live data
    ndvi_mean:          Optional[float]
    ndvi_max:           Optional[float]
    soil_moisture:      Optional[float]
    soil_temp_surface:  Optional[float]
    air_temp:           Optional[float]
    humidity:           Optional[float]
    cloud_cover:        Optional[float]
    satellite_image_date: Optional[str]
    satellite_source:   str

    cached:             bool
    calculated_at:      str


class DistrictItem(BaseModel):
    dist_name:  str
    state_name: str


class AgroSnapshotResponse(BaseModel):
    field_id:          str
    polygon_id:        str
    city_name:         Optional[str]
    state_name:        Optional[str]
    start:             int
    end:               int
    source:            str
    latest_image_date: Optional[str]
    images_count:      int
    ndvi_tile_url:     Optional[str]
    ndvi_stats_url:    Optional[str]
    ndvi_stats:        dict[str, Any]
    weather:           dict[str, Any]
    soil:              dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1: GET /health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe — returns OK if the API and DB are reachable."""
    return {"status": "ok", "service": "KishanSaathi API"}


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2: GET /districts
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/districts", response_model=list[DistrictItem], tags=["Reference"])
async def get_districts(pool: asyncpg.Pool = Depends(get_pool)):
    """
    Returns all unique (district, state) pairs from historical data.
    Used to populate the farmer input form dropdowns.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT dist_name, state_name
            FROM   district_climate_history
            ORDER  BY state_name, dist_name
            """
        )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No district data found. Run the migration script first."
        )
    return [{"dist_name": r["dist_name"], "state_name": r["state_name"]} for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3: GET /crops
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/crops", tags=["Reference"])
async def get_crops():
    """
    Returns all supported crop types (exact column names used by the model).
    Use these as crop_type values in /predict.
    """
    crops = []
    for col in CROP_YIELD_COLUMNS:
        clean = col.upper()
        clean = clean.replace("YIELD", "").replace("(KG PER HA)", "")
        clean = clean.replace(".", " ").replace("KG PER HA", "").strip().title()
        crops.append({
            "crop_type": col,
            "display_name": clean,
            "benchmark_yield_kg_ha": CROP_BENCHMARKS.get(col),
        })
    return {"crops": crops}


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 4: POST /farmers/register
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/farmers/register", response_model=FarmerRegisterResponse, tags=["Farmers"])
async def register_farmer(
    body: FarmerRegisterRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Registers a new farmer.  Phone number must be unique.
    Returns the generated farmer_id (UUID) needed for farm registration.
    """
    dist_clean  = body.dist_name.lower().strip()
    state_clean = body.state_name.strip()

    async with pool.acquire() as conn:
        # Check if phone already registered
        existing = await conn.fetchrow(
            "SELECT id FROM farmers WHERE phone = $1", body.phone
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Phone {body.phone} is already registered. "
                       "Use GET /farmers/{phone} to retrieve your farmer_id."
            )

        row = await conn.fetchrow(
            """
            INSERT INTO farmers (name, phone, state_name, dist_name)
            VALUES ($1, $2, $3, $4)
            RETURNING id, name, phone, state_name, dist_name
            """,
            body.name, body.phone, state_clean, dist_clean,
        )

    logger.log_db_operation(
        "farmer_registered",
        {"name": body.name, "phone": body.phone},
        operation="INSERT",
        table="farmers",
        rows_affected=1
    )
    return {
        "farmer_id":  str(row["id"]),
        "name":       row["name"],
        "phone":      row["phone"],
        "state_name": row["state_name"],
        "dist_name":  row["dist_name"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 5: POST /farm/register
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/farm/register", response_model=FarmRegisterResponse, tags=["Farms"])
async def register_farm(
    body: FarmRegisterRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Registers a new farm field.

    1. Validates coordinates (≥ 4 points for a polygon)
    2. Computes centroid for weather queries
    3. Creates the polygon in Agromonitoring (or mocks if no API key)
    4. Stores the field in farm_fields table
    5. Returns field_id + polygon_id
    """
    coords = body.coordinates
    if len(coords) < 4:
        raise HTTPException(
            status_code=422,
            detail="A polygon needs at least 4 coordinate pairs (3 vertices + closing point)."
        )

    # Validate farmer exists
    async with pool.acquire() as conn:
        farmer = await conn.fetchrow(
            "SELECT id, state_name, dist_name FROM farmers WHERE id = $1",
            body.farmer_id,
        )
    if not farmer:
        raise HTTPException(
            status_code=404,
            detail=f"farmer_id '{body.farmer_id}' not found. Register farmer first."
        )

    # Compute polygon centroid (simple mean of vertices)
    lons = [pt[0] for pt in coords]
    lats = [pt[1] for pt in coords]
    center_lon = round(sum(lons) / len(lons), 6)
    center_lat = round(sum(lats) / len(lats), 6)

    # Register polygon with Agromonitoring (async, non-blocking)
    agro_result = await create_agro_polygon(body.field_name, coords)
    polygon_id  = agro_result["polygon_id"]
    agro_area   = agro_result.get("area")

    area_ha = body.area_hectares or agro_area or 1.0

    # Reverse geocode centroid → city/state (fallback to farmer profile)
    geo = await reverse_geocode_city_state(center_lat, center_lon)
    city_name = (geo.get("city_name") or farmer["dist_name"] or "").strip()
    state_name = (geo.get("state_name") or farmer["state_name"] or "").strip()

    # GeoJSON polygon object (store raw for future use)
    geojson = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords if coords[0] == coords[-1] else coords + [coords[0]]],
        },
    }

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO farm_fields
                (farmer_id, field_name, polygon_id, city_name, state_name,
                 polygon_geojson, center_lat, center_lon, area_hectares)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            body.farmer_id,
            body.field_name,
            polygon_id,
            city_name,
            state_name,
            geojson,
            center_lat,
            center_lon,
            area_ha,
        )

    field_id = str(row["id"])
    logger.log_db_operation(
        "field_registered",
        {"field_id": field_id, "polygon_id": polygon_id},
        operation="INSERT",
        table="farm_fields",
        rows_affected=1
    )

    return {
        "field_id":    field_id,
        "polygon_id":  polygon_id,
        "area":        area_ha,
        "source":      agro_result.get("source", "unknown"),
        "city_name":   city_name or None,
        "state_name":  state_name or None,
        "center_lat":  center_lat,
        "center_lon":  center_lon,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 6: POST /predict  ★ THE MAIN ENGINE ★
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/field/{field_id}/agro-snapshot", response_model=AgroSnapshotResponse, tags=["Farms"])
async def get_field_agro_snapshot(
    field_id: str,
    start: Optional[int] = Query(default=None, ge=0),
    end: Optional[int] = Query(default=None, ge=0),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Returns weather + soil + NDVI image metadata for a saved farm field.
    This endpoint is designed for frontend map overlays and field workspace UI.
    """
    async with pool.acquire() as conn:
        field = await conn.fetchrow(
            """
            SELECT id, polygon_id, city_name, state_name
            FROM   farm_fields
            WHERE  id = $1
            """,
            field_id,
        )

    if not field:
        raise HTTPException(status_code=404, detail=f"field_id '{field_id}' not found.")

    snapshot = await fetch_agro_snapshot(
        polygon_id=field["polygon_id"],
        start_ts=start,
        end_ts=end,
    )

    return {
        "field_id": field_id,
        "polygon_id": field["polygon_id"],
        "city_name": field["city_name"],
        "state_name": field["state_name"],
        "start": snapshot.get("start", 0),
        "end": snapshot.get("end", 0),
        "source": snapshot.get("source", "mock"),
        "latest_image_date": snapshot.get("latest_image_date"),
        "images_count": snapshot.get("images_count", 0),
        "ndvi_tile_url": snapshot.get("ndvi_tile_url"),
        "ndvi_stats_url": snapshot.get("ndvi_stats_url"),
        "ndvi_stats": snapshot.get("ndvi_stats", {}),
        "weather": snapshot.get("weather", {}),
        "soil": snapshot.get("soil", {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 6: POST /predict  ★ THE MAIN ENGINE ★
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/predict", response_model=PredictResponse, tags=["Prediction"])
async def predict(
    body: PredictRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Core prediction engine.

    Cache-first logic:
      1. Check field_predictions for (field_id + crop_type + year)
      2. If found → return immediately (< 10 ms)
      3. If not found:
         a. Impute missing weather from DB (weighted lag avg)
         b. Fetch live satellite data from Agromonitoring
         c. Encode state + crop
         d. Build feature DataFrame (10 features)
         e. XGBoost predict (log-space → expm1 → clip)
         f. Calculate 5-component health score
         g. Insert result into field_predictions
         h. Return full result
    """
    field_id  = str(body.field_id)
    crop_type = body.crop_type
    year      = body.year

    # ── Validate crop_type ────────────────────────────────────────────────────
    if crop_type not in CROP_YIELD_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown crop_type '{crop_type}'. "
                   f"Call GET /crops to see valid options."
        )

    # ── Load field + farmer context ───────────────────────────────────────────
    async with pool.acquire() as conn:
        field = await conn.fetchrow(
            """
            SELECT ff.id, ff.farmer_id, ff.polygon_id,
                   ff.center_lat, ff.center_lon,
                   f.state_name, f.dist_name
            FROM   farm_fields ff
            JOIN   farmers     f  ON f.id = ff.farmer_id
            WHERE  ff.id = $1
            """,
            field_id,
        )
    if not field:
        raise HTTPException(status_code=404, detail=f"field_id '{field_id}' not found.")

    state_name  = field["state_name"]
    dist_name   = field["dist_name"]
    polygon_id  = field["polygon_id"]
    farmer_id   = str(field["farmer_id"])

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 1 — Cache check
    # ══════════════════════════════════════════════════════════════════════════
    async with pool.acquire() as conn:
        cached = await conn.fetchrow(
            """
            SELECT * FROM field_predictions
            WHERE  field_id  = $1
              AND  crop_type = $2
              AND  year      = $3
            """,
            field_id, crop_type, year,
        )

    if cached:
        logger.log_db_operation(
            "cache_hit",
            {"field_id": field_id, "crop_type": crop_type, "year": year},
            operation="SELECT",
            table="field_predictions",
            rows_affected=1
        )
        return _row_to_predict_response(cached, cached=True)

    logger.log_db_operation(
        "cache_miss",
        {"field_id": field_id, "crop_type": crop_type, "year": year},
        operation="SELECT",
        table="field_predictions",
        rows_affected=0
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 2 — Impute weather from DB
    # ══════════════════════════════════════════════════════════════════════════
    imputed = await impute_weather_from_db(
        dist_name=dist_name,
        target_year=year,
        pool=pool,
        provided_irrigation=body.irrigation_ratio,
    )

    kharif_temp = imputed["kharif_avg_maxtemp"]
    kharif_rain = imputed["kharif_total_rain"]
    rabi_temp   = imputed["rabi_avg_maxtemp"]
    wdi         = imputed["wdi"]
    irr         = imputed["irrigation_intensity_ratio"]
    soil_score  = imputed["district_soil_health_score"]
    irr_source  = imputed["irr_source"]

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 3 — Fetch satellite data from Agromonitoring (async)
    # ══════════════════════════════════════════════════════════════════════════
    sat = await get_satellite_data(polygon_id)

    ndvi_mean      = sat.get("ndvi_mean")
    ndvi_max       = sat.get("ndvi_max")
    soil_moisture  = sat.get("soil_moisture")
    soil_temp_surf = sat.get("soil_temp_surface")
    air_temp       = sat.get("air_temp")
    humidity       = sat.get("humidity")
    cloud_cover    = sat.get("cloud_cover")
    sat_date       = sat.get("satellite_image_date")
    sat_source     = sat.get("source", "mock")

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 4 — Encode state + crop using saved LabelEncoders
    # ══════════════════════════════════════════════════════════════════════════
    try:
        state_encoded = int(_le_state.transform([state_name])[0])
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"State '{state_name}' was not seen during model training. "
                   f"Known states: {list(_le_state.classes_)}"
        )

    try:
        crop_encoded = int(_le_crop.transform([crop_type])[0])
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"crop_type '{crop_type}' was not seen during model training."
        )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 5 — Build the exact 10-feature DataFrame (must match training order)
    #
    # YEAR CLAMPING FIX:
    #   The model was trained up to MAX_TRAINING_YEAR (2015).
    #   XGBoost trees don't extrapolate — any year > 2015 hits the same leaf
    #   as 2015, but can produce extreme log-space values → unrealistic yields.
    #   Solution: clamp 'year' to MAX_TRAINING_YEAR for the model input ONLY.
    #   The original user-supplied year (e.g. 2026) is stored in the DB and
    #   returned in the API response unchanged.
    # ══════════════════════════════════════════════════════════════════════════
    model_year = min(year, MAX_TRAINING_YEAR)   # ← clamped for XGBoost only

    if year > MAX_TRAINING_YEAR:
        logger.log_hardcoded(
            "year_clamped_for_model",
            {"requested_year": year, "model_year": model_year},
            reason=(
                f"Input year {year} exceeds training cutoff {MAX_TRAINING_YEAR}. "
                f"Clamping to {model_year} to prevent extrapolation. "
                f"DB record will still show year={year}."
            )
        )

    input_df = pd.DataFrame([{
        "year":                        model_year,   # ← clamped
        "State_Encoded":               state_encoded,
        "Crop_Encoded":                crop_encoded,
        "NPK_Intensity_KgHa":          body.npk_input,
        "Irrigation_Intensity_Ratio":  irr,
        "WDI":                         wdi,
        "Kharif_Avg_MaxTemp":          kharif_temp,
        "Kharif_Total_Rain":           kharif_rain,
        "Rabi_Avg_MaxTemp":            rabi_temp,
        "District_Soil_Health_Score":  soil_score,
    }])

    logger.log_computation(
        "input_features_prepared",
        {
            **input_df.to_dict(orient="records")[0],
            "requested_year": year,      # original user input
            "model_year":     model_year, # what XGBoost actually sees
        },
        computation_type="feature_engineering"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 6 — XGBoost predict
    # Model was trained on log1p(yield), so inverse is np.expm1()
    # ══════════════════════════════════════════════════════════════════════════
    log_pred        = float(_model.predict(input_df)[0])
    
    # ML safeguard: prevent Infinity / NaN
    import math
    if math.isnan(log_pred) or math.isinf(log_pred):
        predicted_yield = CROP_BENCHMARKS.get(crop_type, 1000.0)
        logger.log_hardcoded(
            "yield_fallback_used",
            {"yield": predicted_yield},
            reason=f"XGBoost gave non-finite log_pred: {log_pred}"
        )
    else:
        # Cap log_pred roughly at 11 (~60k kg/ha) so expm1 doesn't overflow to INF
        log_pred_safe   = min(max(log_pred, 0.0), 11.0)
        predicted_yield = float(np.expm1(log_pred_safe))

    benchmark_yield = CROP_BENCHMARKS.get(crop_type, 1000.0)

    logger.log_prediction(
        "yield_model_prediction",
        {"predicted_yield_kg_ha": predicted_yield, "benchmark_yield_kg_ha": benchmark_yield},
        model_name="XGBoost"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 7 — Calculate 5-component health score
    # ══════════════════════════════════════════════════════════════════════════
    health = calculate_health_score(
        predicted_yield = predicted_yield,
        benchmark_yield = benchmark_yield,
        soil_score      = soil_score,
        npk             = body.npk_input,
        wdi             = wdi,
        irr             = irr,
        rain            = kharif_rain,
        kharif_temp     = kharif_temp,
        rabi_temp       = rabi_temp,
        ndvi            = ndvi_mean,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 8 — Insert into field_predictions cache table
    # ══════════════════════════════════════════════════════════════════════════
    sat_date_obj = None
    if sat_date:
        try:
            sat_date_obj = datetime.date.fromisoformat(sat_date)
        except ValueError:
            pass

    async with pool.acquire() as conn:
        new_row = await conn.fetchrow(
            """
            INSERT INTO field_predictions (
                field_id, farmer_id, year, crop_type,
                npk_input, irrigation_ratio, ndvi_value,
                kharif_temp_used, kharif_rain_used, rabi_temp_used,
                wdi_used, soil_score_used, irr_source,
                predicted_yield, benchmark_yield,
                yield_score, soil_score, water_score,
                climate_score, ndvi_score, final_health_score,
                risk_level, loan_decision,
                ndvi_mean, ndvi_max, soil_moisture,
                soil_temp_surface, air_temp, humidity, cloud_cover,
                satellite_image_date
            ) VALUES (
                $1,$2,$3,$4,
                $5,$6,$7,
                $8,$9,$10,
                $11,$12,$13,
                $14,$15,
                $16,$17,$18,
                $19,$20,$21,
                $22,$23,
                $24,$25,$26,
                $27,$28,$29,$30,
                $31
            )
            ON CONFLICT (field_id, crop_type, year) DO UPDATE
                SET calculated_at = NOW()
            RETURNING *
            """,
            # field context
            field_id, farmer_id, year, crop_type,
            # inputs
            body.npk_input, irr, ndvi_mean,
            # imputed weather
            kharif_temp, kharif_rain, rabi_temp,
            wdi, soil_score, irr_source,
            # model output
            predicted_yield, benchmark_yield,
            # health scores
            health["yield_score"],
            health["soil_score"],
            health["water_score"],
            health["climate_score"],
            health["ndvi_score"],
            health["final_health_score"],
            health["risk_level"],
            health["loan_decision"],
            # satellite data
            ndvi_mean, ndvi_max, soil_moisture,
            soil_temp_surf, air_temp, humidity, cloud_cover,
            sat_date_obj,
        )

    logger.log_db_operation(
        "prediction_cached",
        {
            "field_id": field_id,
            "crop_type": crop_type,
            "year": year,
            "health_score": health["final_health_score"],
            "loan_decision": health["loan_decision"]
        },
        operation="INSERT",
        table="field_predictions",
        rows_affected=1
    )

    return _row_to_predict_response(new_row, cached=False)


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 7: GET /field/{field_id}/history
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/field/{field_id}/history", tags=["Prediction"])
async def get_field_history(
    field_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Returns all prediction rows for a field, newest first.
    Used by the frontend for trend charts and history view.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM field_predictions
            WHERE  field_id = $1
            ORDER  BY year DESC, calculated_at DESC
            """,
            field_id,
        )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No prediction history found for field_id '{field_id}'."
        )

    return {
        "field_id": field_id,
        "count":    len(rows),
        "history":  [_row_to_predict_response(r, cached=True) for r in rows],
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 8: GET /farmer/{farmer_id}/fields
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/farmer/{farmer_id}/fields", tags=["Farms"])
async def get_farmer_fields(
    farmer_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Returns all registered fields for a farmer."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, field_name, polygon_id, center_lat,
                     center_lon, city_name, state_name,
                     area_hectares, created_at
            FROM   farm_fields
            WHERE  farmer_id = $1
            ORDER  BY created_at DESC
            """,
            farmer_id,
        )
    return {
        "farmer_id": farmer_id,
        "fields": [
            {
                "field_id":     str(r["id"]),
                "field_name":   r["field_name"],
                "polygon_id":   r["polygon_id"],
                "center_lat":   r["center_lat"],
                "center_lon":   r["center_lon"],
                "city_name":    r["city_name"],
                "state_name":   r["state_name"],
                "area_hectares": r["area_hectares"],
                "created_at":   r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: asyncpg Record → PredictResponse dict
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_predict_response(row, cached: bool) -> dict:
    """Converts a field_predictions DB row to the PredictResponse schema."""
    sat_date = row["satellite_image_date"]
    return {
        "field_id":         str(row["field_id"]),
        "crop_type":        row["crop_type"],
        "year":             row["year"],
        "predicted_yield":  round(float(row["predicted_yield"]), 2),
        "benchmark_yield":  round(float(row["benchmark_yield"]), 2) if row["benchmark_yield"] else None,
        "health": {
            "final_health_score": float(row["final_health_score"]),
            "yield_score":        float(row["yield_score"]   or 0),
            "soil_score":         float(row["soil_score"]    or 0),
            "water_score":        float(row["water_score"]   or 0),
            "climate_score":      float(row["climate_score"] or 0),
            "ndvi_score":         float(row["ndvi_score"]    or 0),
            "ndvi_source":        "satellite" if row["ndvi_mean"] else "yield proxy",
            "risk_level":         row["risk_level"],
            "loan_decision":      row["loan_decision"],
        },
        "kharif_temp_used":  float(row["kharif_temp_used"] or 0),
        "kharif_rain_used":  float(row["kharif_rain_used"] or 0),
        "rabi_temp_used":    float(row["rabi_temp_used"]   or 0),
        "wdi_used":          float(row["wdi_used"]         or 0),
        "soil_score_used":   float(row["soil_score_used"]  or 0),
        "irr_source":        row["irr_source"] or "auto_imputed",
        "irrigation_used":   float(row["irrigation_ratio"] or 0),
        "ndvi_mean":         float(row["ndvi_mean"])        if row["ndvi_mean"]        is not None else None,
        "ndvi_max":          float(row["ndvi_max"])         if row["ndvi_max"]         is not None else None,
        "soil_moisture":     float(row["soil_moisture"])    if row["soil_moisture"]    is not None else None,
        "soil_temp_surface": float(row["soil_temp_surface"]) if row["soil_temp_surface"] is not None else None,
        "air_temp":          float(row["air_temp"])         if row["air_temp"]         is not None else None,
        "humidity":          float(row["humidity"])         if row["humidity"]         is not None else None,
        "cloud_cover":       float(row["cloud_cover"])      if row["cloud_cover"]      is not None else None,
        "satellite_image_date": sat_date.isoformat() if sat_date else None,
        "satellite_source":  "agromonitoring",
        "cached":            cached,
        "calculated_at":     row["calculated_at"].isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 9: POST /chat  — LangGraph KisanSaathi Chatbot
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    farmer_id: str = Field(
        ...,
        description="UUID of the farmer (from /farmers/register)",
        json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
    )

    @field_validator("farmer_id", mode="before")
    @classmethod
    def extract_uuid(cls, v: str) -> str:
        """Silently strips any extra copied text (like ' - farmer_id') and extracts just the UUID."""
        import re
        match = re.search(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', str(v))
        return match.group(0) if match else v
    message: str = Field(
        ...,
        description="The farmer's chat message",
        json_schema_extra={"example": "Mera health score kya hai?"},
    )
    thread_id: Optional[str] = Field(
        default=None,
        description=(
            "Chat session ID for thread persistence and resumption. "
            "Omit to auto-derive as 'thread-{farmer_id}'. "
            "Provide the same value across turns to maintain conversation history."
        ),
        json_schema_extra={"example": "thread-abc-123"},
    )
    history: list[dict] = Field(
        default=[],
        description="(Legacy — ignored; history is loaded from DB via thread_id)",
    )


class ChatResponse(BaseModel):
    reply: str
    farmer_id: str
    thread_id: str


@app.post("/chat", response_model=ChatResponse, tags=["Chatbot"])
async def chat(req: ChatRequest):
    """
    KisanSaathi conversational AI agent — LangGraph StateGraph edition.

    Powered by LangGraph (StateGraph) + ChatGroq (llama-3.3-70b-versatile).
    The agent has 4 tools:
      • get_farmer_data   — farm status, NDVI, health score, yield
      • get_weather       — current weather + 7-day forecast
      • get_market_price  — live mandi prices (Agmarknet API)
      • get_crop_advice   — What-If engine for score improvement advice

    Supports Hinglish (Hindi + English mixed) responses.
    All data is fetched live from the database — no hallucinated values.

    Thread persistence:
      Provide thread_id to resume a previous conversation with full memory.
      Omit it to auto-derive a default thread for this farmer.
    """
    thread_id = req.thread_id or f"thread-{req.farmer_id}"
    try:
        reply = await run_agent(
            farmer_id=req.farmer_id,
            message=req.message,
            thread_id=thread_id,
        )
    except Exception as exc:
        logger.log_error(
            "chat_endpoint_error",
            exc,
            context={"farmer_id": req.farmer_id, "thread_id": thread_id}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Chatbot error: {str(exc)}",
        )
    return {"reply": reply, "farmer_id": req.farmer_id, "thread_id": thread_id}


from fastapi.responses import StreamingResponse as _StreamingResponse


@app.post("/chat/stream", tags=["Chatbot"])
async def chat_stream(req: ChatRequest):
    """
    Token-streaming variant of /chat.

    Tokens stream via Server-Sent Events as they are generated by the LLM.
    Ideal for mobile clients on slow networks — farmer sees the reply appear word by word.

    Response format: text/plain — each chunk is a raw token string.
    Prefix your SSE listener with 'data: ' if you need standard SSE wrapping.

    Thread persistence same as /chat — provide thread_id or default is used.
    """
    thread_id = req.thread_id or f"thread-{req.farmer_id}"

    async def token_generator():
        try:
            async for chunk in run_agent_streaming(
                farmer_id=req.farmer_id,
                message=req.message,
                thread_id=thread_id,
            ):
                if chunk:
                    yield chunk
        except Exception as exc:
            logger.log_error(
                "streaming_chat_error",
                exc,
                context={"farmer_id": req.farmer_id}
            )
            yield f"\n[Error: {type(exc).__name__} — {exc}]"

    return _StreamingResponse(
        token_generator(),
        media_type="text/plain",
        headers={
            "X-Thread-Id": thread_id,
            "Cache-Control": "no-cache",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
