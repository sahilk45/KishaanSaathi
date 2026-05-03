"""
services/imputation.py — Weighted lag-average imputation from PostgreSQL
=========================================================================

Strategy (FIXED):
  Instead of looking for exact years target-1, target-2, target-3
  (which all MISS when target_year=2026 and data ends at 2015),
  we find the 3 MOST RECENT years that actually EXIST in the DB
  for that district, then apply weights 0.5 / 0.3 / 0.2.

  Example:
    target_year = 2026, district has data up to 2015
    → uses years 2015 (×0.5) + 2014 (×0.3) + 2013 (×0.2)

  Example (normal case within data range):
    target_year = 2014, district has data up to 2015
    → still uses the 3 most recent years ≤ 2013 that exist
      i.e. 2013 (×0.5) + 2012 (×0.3) + 2011 (×0.2)

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

# Weights applied to [most_recent, second, third] years found in DB
LAG_WEIGHTS = [0.5, 0.3, 0.2]   # must sum to 1.0

# National fallback defaults (last resort if district has no data at all)
_DEFAULTS = {
    "kharif_avg_maxtemp":       32.0,
    "kharif_total_rain":        900.0,
    "rabi_avg_maxtemp":         26.0,
    "wdi":                      0.50,
    "irrigation_intensity_ratio": 0.40,
}


async def _get_recent_years(conn, dist_clean: str, before_year: int) -> list[int]:
    """
    Returns up to 3 most recent years that exist in district_climate_history
    for the given district, strictly BEFORE before_year.

    For target_year=2026 and data up to 2015:
      → returns [2015, 2014, 2013]
    For target_year=2014 and data up to 2015:
      → returns [2013, 2012, 2011]  (excludes 2014 and 2015 since we want lag)
    """
    rows = await conn.fetch(
        """
        SELECT year
        FROM   district_climate_history
        WHERE  dist_name = $1
          AND  year      < $2
          AND  year      IS NOT NULL
        ORDER  BY year DESC
        LIMIT  3
        """,
        dist_clean,
        before_year,
    )
    return [r["year"] for r in rows]


async def impute_weather_from_db(
    dist_name: str,
    target_year: int,
    pool: asyncpg.Pool,
    provided_irrigation: Optional[float] = None,
) -> dict:
    """
    Returns a dict with all imputed climate values for the district.

    Keys returned:
        kharif_avg_maxtemp, kharif_total_rain, rabi_avg_maxtemp,
        wdi, irrigation_intensity_ratio, district_soil_health_score,
        irr_source       ('farmer_input' | 'auto_imputed'),
        years_used       (list of years that went into the weighted average)

    Args:
        dist_name:           District name (will be lowercased + stripped)
        target_year:         The year we are predicting FOR (e.g. 2026)
        pool:                asyncpg connection pool
        provided_irrigation: If farmer supplied irrigation ratio, use that
                             directly and skip imputation for it.
    """
    dist_clean = dist_name.lower().strip()
    result: dict = {}

    async with pool.acquire() as conn:

        # ── Step 1: Find the 3 most recent years BEFORE target_year ───────────
        recent_years = await _get_recent_years(conn, dist_clean, target_year)

        if recent_years:
            logger.info(
                "Imputation: district='%s' target_year=%d → using years %s with weights %s",
                dist_clean, target_year, recent_years, LAG_WEIGHTS[:len(recent_years)],
            )
        else:
            logger.warning(
                "Imputation: district='%s' has NO data before year %d — will use district mean",
                dist_clean, target_year,
            )

        result["years_used"] = recent_years   # for transparency / logging

        # ── Step 2: Weighted average per feature ───────────────────────────────
        for col in LAG_FEATURES:

            # Skip irrigation if farmer already provided it
            if col == "irrigation_intensity_ratio" and provided_irrigation is not None:
                continue

            weighted_sum = 0.0
            total_weight = 0.0

            for i, yr in enumerate(recent_years):
                weight = LAG_WEIGHTS[i]   # 0.5, 0.3, 0.2 in order

                # col is from the hardcoded LAG_FEATURES list — safe to use in f-string
                row = await conn.fetchrow(
                    f"""
                    SELECT {col}
                    FROM   district_climate_history
                    WHERE  dist_name = $1
                      AND  year      = $2
                    """,
                    dist_clean,
                    yr,
                )

                if row and row[col] is not None:
                    weighted_sum += float(row[col]) * weight
                    total_weight += weight
                else:
                    logger.debug(
                        "Imputation: %s missing for district='%s' year=%d — skipping",
                        col, dist_clean, yr,
                    )

            if total_weight > 0:
                # Normalise in case some year rows had NULL for this column
                imputed_val = weighted_sum / total_weight
                logger.debug(
                    "Imputation: %s for '%s' = %.4f (weighted over %s)",
                    col, dist_clean, imputed_val, recent_years,
                )
            else:
                # ── Fallback A: district all-time mean ─────────────────────────
                imputed_val = await conn.fetchval(
                    f"""
                    SELECT AVG({col})
                    FROM   district_climate_history
                    WHERE  dist_name = $1
                    """,
                    dist_clean,
                )
                if imputed_val is not None:
                    logger.warning(
                        "Imputation: %s for '%s' — no recent years found, "
                        "using district all-time mean %.4f",
                        col, dist_clean, imputed_val,
                    )
                else:
                    # ── Fallback B: national hardcoded default ─────────────────
                    imputed_val = _DEFAULTS.get(col, 0.0)
                    logger.warning(
                        "Imputation: %s for '%s' — district has NO data at all, "
                        "using national default %.4f",
                        col, dist_clean, imputed_val,
                    )

            result[col] = round(float(imputed_val), 6)

        # ── Step 3: Irrigation — farmer input takes priority ──────────────────
        if provided_irrigation is not None:
            result["irrigation_intensity_ratio"] = float(provided_irrigation)
            result["irr_source"] = "farmer_input"
        else:
            result["irr_source"] = "auto_imputed"

        # ── Step 4: Soil score — district mean (static, not time-weighted) ────
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
        "Imputation complete | district='%s' target_year=%d years_used=%s → "
        "kharif_temp=%.1f kharif_rain=%.0f rabi_temp=%.1f wdi=%.3f soil=%.1f",
        dist_clean, target_year, result.get("years_used", []),
        result.get("kharif_avg_maxtemp", 0),
        result.get("kharif_total_rain", 0),
        result.get("rabi_avg_maxtemp", 0),
        result.get("wdi", 0),
        result.get("district_soil_health_score", 0),
    )
    return result

