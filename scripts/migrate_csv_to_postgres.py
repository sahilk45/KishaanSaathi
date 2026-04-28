"""
scripts/migrate_csv_to_postgres.py
====================================
ONE-TIME script: reads KrishiTwin_Final_Engineered.csv and populates
the district_climate_history table in PostgreSQL.

Safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING.

Run from the backend/ directory:
    python scripts/migrate_csv_to_postgres.py

Or with a custom path:
    CSV_PATH=/path/to/file.csv DB_URL=postgresql://... python scripts/migrate_csv_to_postgres.py
"""

import os
import sys
import asyncio
import logging

import pandas as pd
import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("migrate")

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# Config — override via environment variables
# ─────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/kishandb"
)

CSV_PATH = os.getenv(
    "CSV_PATH",
    os.path.join(os.path.dirname(__file__), "..", "Dataset", "KrishiTwin_Final_Engineered.csv")
)

# ─────────────────────────────────────────────────────────────────────────────
# Column mapping: CSV column name → DB column name
# ─────────────────────────────────────────────────────────────────────────────
CSV_TO_DB = {
    "dist_code":                  "dist_code",
    "year":                       "year",
    "State Name":                 "state_name",
    "dist_name":                  "dist_name",
    "Kharif_Avg_MaxTemp":         "kharif_avg_maxtemp",
    "Kharif_Total_Rain":          "kharif_total_rain",
    "Rabi_Avg_MaxTemp":           "rabi_avg_maxtemp",
    "WDI":                        "wdi",
    "Irrigation_Intensity_Ratio": "irrigation_intensity_ratio",
    "NPK_Intensity_KgHa":         "npk_intensity_kgha",
    "District_Soil_Health_Score": "district_soil_health_score",
}

# Optional columns (present in CSV but not always populated)
OPTIONAL_COLS = {
    "Kharif_Avg_MinTemp": "kharif_avg_mintemp",
    "Rabi_Total_Rain":    "rabi_total_rain",
}

INSERT_SQL = """
    INSERT INTO district_climate_history (
        dist_name,
        state_name,
        dist_code,
        year,
        kharif_avg_maxtemp,
        kharif_avg_mintemp,
        kharif_total_rain,
        rabi_avg_maxtemp,
        rabi_total_rain,
        wdi,
        irrigation_intensity_ratio,
        npk_intensity_kgha,
        district_soil_health_score,
        yield_rice,
        yield_pearl_millet,
        yield_chickpea,
        yield_groundnut,
        yield_sugarcane,
        yield_wheat,
        yield_kharif_sorghum,
        yield_rabi_sorghum,
        yield_sorghum,
        yield_maize,
        yield_finger_millet,
        yield_barley,
        yield_pigeonpea,
        yield_minor_pulses,
        yield_sesamum,
        yield_rapeseed_and_mustard,
        yield_safflower,
        yield_castor,
        yield_linseed,
        yield_sunflower,
        yield_soyabean,
        yield_oilseeds,
        yield_cotton
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36)
    ON CONFLICT (dist_name, year) DO NOTHING
"""


def _safe_float(val) -> float | None:
    """Convert a CSV value to float, returning None for NaN / empty."""
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


async def migrate():
    # ── Load CSV ──────────────────────────────────────────────────────────────
    csv_path = os.path.abspath(CSV_PATH)
    if not os.path.exists(csv_path):
        logger.error("CSV file not found: %s", csv_path)
        logger.error("Set CSV_PATH env var to the correct path.")
        sys.exit(1)

    logger.info("Loading CSV: %s", csv_path)
    df = pd.read_csv(csv_path)
    logger.info("CSV loaded: %d rows × %d columns", *df.shape)

    # Normalise dist_name: lowercase + strip (must match what imputation queries)
    df["dist_name"] = df["dist_name"].astype(str).str.lower().str.strip()
    df["State Name"] = df["State Name"].astype(str).str.strip()

    # Check for optional columns
    has_kharif_mintemp = "Kharif_Avg_MinTemp" in df.columns
    has_rabi_rain      = "Rabi_Total_Rain"    in df.columns

    if not has_kharif_mintemp:
        logger.warning("Column 'Kharif_Avg_MinTemp' not in CSV — will insert NULL")
    if not has_rabi_rain:
        logger.warning("Column 'Rabi_Total_Rain' not in CSV — will insert NULL")

    # ── Connect to DB ─────────────────────────────────────────────────────────
    logger.info("Connecting to: %s", DATABASE_URL)
    conn = await asyncpg.connect(DATABASE_URL)

    # ── Ensure extension + table exist ───────────────────────────────────────
    await conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS district_climate_history (
            id                          SERIAL PRIMARY KEY,
            dist_name                   VARCHAR(100) NOT NULL,
            state_name                  VARCHAR(100) NOT NULL,
            dist_code                   INTEGER,
            year                        INTEGER NOT NULL,
            kharif_avg_maxtemp          FLOAT,
            kharif_avg_mintemp          FLOAT,
            kharif_total_rain           FLOAT,
            rabi_avg_maxtemp            FLOAT,
            rabi_total_rain             FLOAT,
            wdi                         FLOAT,
            irrigation_intensity_ratio  FLOAT,
            npk_intensity_kgha          FLOAT,
            district_soil_health_score  FLOAT,
            yield_rice FLOAT,
            yield_pearl_millet FLOAT,
            yield_chickpea FLOAT,
            yield_groundnut FLOAT,
            yield_sugarcane FLOAT,
            yield_wheat FLOAT,
            yield_kharif_sorghum FLOAT,
            yield_rabi_sorghum FLOAT,
            yield_sorghum FLOAT,
            yield_maize FLOAT,
            yield_finger_millet FLOAT,
            yield_barley FLOAT,
            yield_pigeonpea FLOAT,
            yield_minor_pulses FLOAT,
            yield_sesamum FLOAT,
            yield_rapeseed_and_mustard FLOAT,
            yield_safflower FLOAT,
            yield_castor FLOAT,
            yield_linseed FLOAT,
            yield_sunflower FLOAT,
            yield_soyabean FLOAT,
            yield_oilseeds FLOAT,
            yield_cotton FLOAT,
            created_at                  TIMESTAMP DEFAULT NOW(),
            UNIQUE(dist_name, year)
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dch_dist_year ON district_climate_history(dist_name, year)"
    )

    # ── Bulk insert using executemany ─────────────────────────────────────────
    logger.info("Starting INSERT ... ON CONFLICT DO NOTHING for %d rows...", len(df))

    records = []
    skipped = 0

    for _, row in df.iterrows():
        dist_name  = str(row["dist_name"])
        state_name = str(row["State Name"])
        dist_code  = _safe_int(row.get("dist_code"))
        year       = _safe_int(row.get("year"))

        if not dist_name or year is None:
            skipped += 1
            continue

        records.append((
            dist_name,
            state_name,
            dist_code,
            year,
            _safe_float(row.get("Kharif_Avg_MaxTemp")),
            _safe_float(row.get("Kharif_Avg_MinTemp")) if has_kharif_mintemp else None,
            _safe_float(row.get("Kharif_Total_Rain")),
            _safe_float(row.get("Rabi_Avg_MaxTemp")),
            _safe_float(row.get("Rabi_Total_Rain")) if has_rabi_rain else None,
            _safe_float(row.get("WDI")),
            _safe_float(row.get("Irrigation_Intensity_Ratio")),
            _safe_float(row.get("NPK_Intensity_KgHa")),
            _safe_float(row.get("District_Soil_Health_Score")),
            _safe_float(row.get("RICE YIELD (Kg per ha)")),
            _safe_float(row.get("PEARL MILLET YIELD (Kg per ha)")),
            _safe_float(row.get("CHICKPEA YIELD (Kg per ha)")),
            _safe_float(row.get("GROUNDNUT YIELD (Kg per ha)")),
            _safe_float(row.get("SUGARCANE YIELD (Kg per ha)")),
            _safe_float(row.get("WHEAT.YIELD.Kg.per.ha.")),
            _safe_float(row.get("KHARIF.SORGHUM.YIELD.Kg.per.ha.")),
            _safe_float(row.get("RABI.SORGHUM.YIELD.Kg.per.ha.")),
            _safe_float(row.get("SORGHUM.YIELD.Kg.per.ha.")),
            _safe_float(row.get("MAIZE.YIELD.Kg.per.ha.")),
            _safe_float(row.get("FINGER.MILLET.YIELD.Kg.per.ha.")),
            _safe_float(row.get("BARLEY.YIELD.Kg.per.ha.")),
            _safe_float(row.get("PIGEONPEA.YIELD.Kg.per.ha.")),
            _safe_float(row.get("MINOR.PULSES.YIELD.Kg.per.ha.")),
            _safe_float(row.get("SESAMUM.YIELD.Kg.per.ha.")),
            _safe_float(row.get("RAPESEED.AND.MUSTARD.YIELD.Kg.per.ha.")),
            _safe_float(row.get("SAFFLOWER.YIELD.Kg.per.ha.")),
            _safe_float(row.get("CASTOR.YIELD.Kg.per.ha.")),
            _safe_float(row.get("LINSEED.YIELD.Kg.per.ha.")),
            _safe_float(row.get("SUNFLOWER.YIELD.Kg.per.ha.")),
            _safe_float(row.get("SOYABEAN.YIELD.Kg.per.ha.")),
            _safe_float(row.get("OILSEEDS.YIELD.Kg.per.ha.")),
            _safe_float(row.get("COTTON.YIELD.Kg.per.ha.")),
        ))

    # Use executemany for bulk insert performance, batched
    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        await conn.executemany(INSERT_SQL, batch)
        logger.info(f"Inserted {i + len(batch)} / {len(records)} rows...")

    # ── Report ────────────────────────────────────────────────────────────────
    count = await conn.fetchval("SELECT COUNT(*) FROM district_climate_history")
    await conn.close()

    logger.info("=" * 55)
    logger.info("✅  Migration complete!")
    logger.info("   Rows attempted : %d", len(records))
    logger.info("   Rows skipped   : %d (bad data)", skipped)
    logger.info("   Total in table : %d", count)
    logger.info("=" * 55)


if __name__ == "__main__":
    asyncio.run(migrate())
