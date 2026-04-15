"""
services/imputation.py — Weighted lag-average imputation from PostgreSQL
=========================================================================
For a given district + target_year, computes:
  value = (yr-1 × 0.5) + (yr-2 × 0.3) + (yr-3 × 0.2)

Features imputed:
  kharif_avg_maxtemp, kharif_total_rain, rabi_avg_maxtemp,
  wdi, irrigation_intensity_ratio

Static (district mean, not time-weighted):
  district_soil_health_score
"""

import asyncpg
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Columns to impute with weighted lag average
LAG_FEATURES = [
    "kharif_avg_maxtemp",
    "kharif_total_rain",
    "rabi_avg_maxtemp",
    "wdi",
    "irrigation_intensity_ratio",
]

# Lag offsets and their weights (must sum to 1.0)
LAG_WEIGHTS = [
    (1, 0.5),   # year - 1,  weight 0.5
    (2, 0.3),   # year - 2,  weight 0.3
    (3, 0.2),   # year - 3,  weight 0.2
]


async def impute_weather_from_db(
    dist_name: str,
    target_year: int,
    pool: asyncpg.Pool,
    provided_irrigation: Optional[float] = None,
) -> dict:
    """
    Returns a dict with all imputed values for the district.

    Keys returned:
        kharif_avg_maxtemp, kharif_total_rain, rabi_avg_maxtemp,
        wdi, irrigation_intensity_ratio, district_soil_health_score,
        irr_source ('farmer_input' | 'auto_imputed')

    Args:
        dist_name:             District name (lowercase, stripped)
        target_year:           The year we are predicting FOR
        pool:                  asyncpg pool
        provided_irrigation:   If the farmer supplied irrigation ratio,
                               we use that and skip imputation for it.
    """
    dist_clean = dist_name.lower().strip()
    result: dict = {}

    async with pool.acquire() as conn:
        # ── 1. Weighted lag average for each feature ──────────────────────────
        for col in LAG_FEATURES:

            # Skip irrigation if farmer already provided it
            if col == "irrigation_intensity_ratio" and provided_irrigation is not None:
                continue

            weighted_sum  = 0.0
            total_weight  = 0.0

            for lag, weight in LAG_WEIGHTS:
                # asyncpg does NOT support f-string column names as parameters
                # so we use format() for column name (safe — it's a hardcoded list)
                row = await conn.fetchrow(
                    f"""
                    SELECT {col}
                    FROM   district_climate_history
                    WHERE  dist_name = $1
                      AND  year      = $2
                    """,
                    dist_clean,
                    target_year - lag,
                )

                if row and row[col] is not None:
                    weighted_sum  += row[col] * weight
                    total_weight  += weight

            if total_weight > 0:
                imputed_val = weighted_sum / total_weight
            else:
                # Fallback: use the district's all-time average for that column
                imputed_val = await conn.fetchval(
                    f"""
                    SELECT AVG({col})
                    FROM   district_climate_history
                    WHERE  dist_name = $1
                    """,
                    dist_clean,
                )
                if imputed_val is None:
                    # Last resort: sensible national defaults
                    defaults = {
                        "kharif_avg_maxtemp":      32.0,
                        "kharif_total_rain":        900.0,
                        "rabi_avg_maxtemp":         26.0,
                        "wdi":                      0.50,
                        "irrigation_intensity_ratio": 0.40,
                    }
                    imputed_val = defaults.get(col, 0.0)
                logger.warning(
                    "Imputation fallback to district mean for %s / %s (year %d)",
                    col, dist_clean, target_year,
                )

            result[col] = round(float(imputed_val), 6)

        # ── 2. Irrigation: use farmer-provided or imputed ─────────────────────
        if provided_irrigation is not None:
            result["irrigation_intensity_ratio"] = float(provided_irrigation)
            result["irr_source"] = "farmer_input"
        else:
            result["irr_source"] = "auto_imputed"

        # ── 3. Soil score: district mean (static across years) ────────────────
        soil_mean = await conn.fetchval(
            """
            SELECT AVG(district_soil_health_score)
            FROM   district_climate_history
            WHERE  dist_name = $1
            """,
            dist_clean,
        )
        result["district_soil_health_score"] = round(
            float(soil_mean) if soil_mean is not None else 50.0, 4
        )

    logger.info(
        "Imputation complete for %s / year %d → %s",
        dist_clean, target_year, result,
    )
    return result
