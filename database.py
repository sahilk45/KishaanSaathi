"""
database.py — asyncpg connection pool + schema bootstrap
=========================================================
Creates the pool once at startup and exposes it via app.state.
Run create_all_tables() once on first deploy to create all 4 tables.
"""

import asyncpg
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DDL — all 4 tables
# ─────────────────────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """

-- Enable uuid generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Table 1: district_climate_history ────────────────────────────────────────
-- Pre-aggregated from KrishiTwin_Final_Engineered.csv (7841 rows).
-- Used for weighted_lag_avg imputation at prediction time.
CREATE TABLE IF NOT EXISTS district_climate_history (
    id                          SERIAL PRIMARY KEY,
    dist_name                   VARCHAR(100) NOT NULL,
    state_name                  VARCHAR(100) NOT NULL,
    dist_code                   INTEGER,
    year                        INTEGER NOT NULL,

    -- Weather / agronomic features (used for weighted lag imputation)
    kharif_avg_maxtemp          FLOAT,
    kharif_avg_mintemp          FLOAT,
    kharif_total_rain           FLOAT,
    rabi_avg_maxtemp            FLOAT,
    rabi_total_rain             FLOAT,
    wdi                         FLOAT,
    irrigation_intensity_ratio  FLOAT,
    npk_intensity_kgha          FLOAT,

    -- Static district-level health score (same across all years per district)
    district_soil_health_score  FLOAT,

    created_at                  TIMESTAMP DEFAULT NOW(),
    UNIQUE(dist_name, year)
);

CREATE INDEX IF NOT EXISTS idx_dch_dist_year
    ON district_climate_history(dist_name, year);

CREATE INDEX IF NOT EXISTS idx_dch_dist_name
    ON district_climate_history(dist_name);


-- ── Table 2: farmers ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS farmers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    phone       VARCHAR(20)  UNIQUE NOT NULL,
    state_name  VARCHAR(100) NOT NULL,
    dist_name   VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);


-- ── Table 3: farm_fields ─────────────────────────────────────────────────────
-- One farmer → many fields.
CREATE TABLE IF NOT EXISTS farm_fields (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id       UUID REFERENCES farmers(id) ON DELETE CASCADE,
    field_name      VARCHAR(200),
    polygon_id      VARCHAR(100),           -- Agromonitoring polygon_id
    city_name       VARCHAR(120),           -- Reverse-geocoded city/town/village
    state_name      VARCHAR(120),           -- Reverse-geocoded state
    polygon_geojson JSONB,                  -- Raw GeoJSON from Leaflet draw
    center_lat      FLOAT,
    center_lon      FLOAT,
    area_hectares   FLOAT,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Backward-compatible column upgrades for existing deployments
ALTER TABLE farm_fields ADD COLUMN IF NOT EXISTS city_name  VARCHAR(120);
ALTER TABLE farm_fields ADD COLUMN IF NOT EXISTS state_name VARCHAR(120);

CREATE INDEX IF NOT EXISTS idx_ff_farmer ON farm_fields(farmer_id);


-- ── Table 4: field_predictions ───────────────────────────────────────────────
-- THE CACHE TABLE. One row per (field × crop × year).
-- Check this first; if exists → return cached. If not → compute + store.
CREATE TABLE IF NOT EXISTS field_predictions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id        UUID REFERENCES farm_fields(id) ON DELETE CASCADE,
    farmer_id       UUID REFERENCES farmers(id)     ON DELETE CASCADE,

    -- Prediction inputs
    year            INTEGER      NOT NULL,
    crop_type       VARCHAR(150) NOT NULL,
    npk_input       FLOAT,
    irrigation_ratio FLOAT,
    ndvi_value      FLOAT,               -- NDVI used for health score

    -- Auto-imputed weather values (stored to avoid re-calculation)
    kharif_temp_used   FLOAT,
    kharif_rain_used   FLOAT,
    rabi_temp_used     FLOAT,
    wdi_used           FLOAT,
    soil_score_used    FLOAT,
    irr_source         VARCHAR(50),      -- 'farmer_input' | 'auto_imputed'

    -- Model output
    predicted_yield    FLOAT NOT NULL,
    benchmark_yield    FLOAT,

    -- Health score components (5 components)
    yield_score        FLOAT,
    soil_score         FLOAT,
    water_score        FLOAT,
    climate_score      FLOAT,
    ndvi_score         FLOAT,
    final_health_score FLOAT NOT NULL,
    risk_level         VARCHAR(20),       -- 'LOW' | 'MEDIUM' | 'HIGH'
    loan_decision      VARCHAR(20),       -- 'ELIGIBLE' | 'REVIEW' | 'INELIGIBLE'

    -- Satellite / live data from Agromonitoring
    ndvi_mean           FLOAT,
    ndvi_max            FLOAT,
    soil_moisture       FLOAT,
    soil_temp_surface   FLOAT,
    air_temp            FLOAT,
    humidity            FLOAT,
    cloud_cover         FLOAT,
    satellite_image_date DATE,

    calculated_at   TIMESTAMP DEFAULT NOW(),

    -- One cached result per field + crop + year combination
    UNIQUE(field_id, crop_type, year)
);

CREATE INDEX IF NOT EXISTS idx_fp_field_crop_year
    ON field_predictions(field_id, crop_type, year);

CREATE INDEX IF NOT EXISTS idx_fp_farmer
    ON field_predictions(farmer_id);
"""


# ─────────────────────────────────────────────────────────────────────────────
# Pool management
# ─────────────────────────────────────────────────────────────────────────────

async def create_pool(dsn: str) -> asyncpg.Pool:
    """
    Creates the asyncpg connection pool.
    Called once at application startup via the lifespan context manager.
    """
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=60,
        # asyncpg needs explicit JSON codec registration
        init=_init_connection,
    )
    logger.info("✅ asyncpg pool created")
    return pool


async def _init_connection(conn: asyncpg.Connection):
    """
    Called for every new connection in the pool.
    Registers codecs so asyncpg can encode/decode Python dicts ↔ JSONB.
    """
    await conn.set_type_codec(
        "jsonb",
        encoder=lambda v: __import__("json").dumps(v),
        decoder=lambda v: __import__("json").loads(v),
        schema="pg_catalog",
        format="text",
    )
    await conn.set_type_codec(
        "json",
        encoder=lambda v: __import__("json").dumps(v),
        decoder=lambda v: __import__("json").loads(v),
        schema="pg_catalog",
        format="text",
    )


async def create_all_tables(pool: asyncpg.Pool):
    """
    Runs the DDL once on first deploy.  Safe to re-run (all IF NOT EXISTS).
    """
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
    logger.info("✅ All tables ensured")


@asynccontextmanager
async def get_conn(pool: asyncpg.Pool):
    """Helper context manager for acquiring a single connection."""
    async with pool.acquire() as conn:
        yield conn
