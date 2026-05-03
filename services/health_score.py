"""
services/health_score.py — 5-component farm health score
=========================================================
Exact formula as defined in Krishi_Health_Score_Notebook.ipynb.

Components and weights:
  1. Yield Performance Score  — 25%
  2. Soil Health Score        — 20%
  3. Water Stress Score       — 25%
  4. Climate Risk Score       — 15%
  5. NDVI Vegetation Score    — 15%

Thresholds:
  final >= 65  →  LOW risk    / ELIGIBLE
  final >= 45  →  MEDIUM risk / REVIEW
  final <  45  →  HIGH risk   / INELIGIBLE
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_health_score(
    predicted_yield:  float,
    benchmark_yield:  float,
    soil_score:       float,    # district_soil_health_score from DB
    npk:              float,    # NPK_Intensity_KgHa (farmer input)
    wdi:              float,    # Water Demand Index (0–1, lower = less stressed)
    irr:              float,    # Irrigation_Intensity_Ratio (0–1)
    rain:             float,    # Kharif_Total_Rain (mm)
    kharif_temp:      float,    # Kharif_Avg_MaxTemp (°C)
    rabi_temp:        float,    # Rabi_Avg_MaxTemp   (°C)
    ndvi:             Optional[float] = None,   # NDVI mean from satellite (optional)
) -> dict:
    """
    Computes the KishiSaathi Farm Health Score.

    Returns a dict with:
        final_health_score  (0–100, float)
        yield_score         (0–100)
        soil_score          (0–100, after NPK penalty)
        water_score         (0–100)
        climate_score       (0–100)
        ndvi_score          (0–100)
        ndvi_source         ('satellite (x.xx)' | 'yield proxy')
        benchmark_yield     (for reference)
        risk_level          ('LOW' | 'MEDIUM' | 'HIGH')
        loan_decision       ('ELIGIBLE' | 'REVIEW' | 'INELIGIBLE')
    """

    # ── 1. Yield Performance Score (25%) ─────────────────────────────────────
    # How close is predicted yield to the district historical benchmark?
    if benchmark_yield and benchmark_yield > 0:
        yield_score = min((predicted_yield / benchmark_yield) * 100.0, 100.0)
    else:
        yield_score = 50.0          # neutral fallback if benchmark unknown
        logger.warning("benchmark_yield is zero/None — using neutral 50 for yield_score")

    # ── 2. Soil Health Score (20%) ────────────────────────────────────────────
    # Base score from district soil health (scale: district_soil_health_score / 200 × 100)
    # Penalty if NPK is far from the optimal 120 kg/ha
    soil_base   = (soil_score / 200.0) * 100.0
    npk_penalty = min((abs(npk - 120.0) / 120.0) * 30.0, 30.0)
    soil_final  = max(soil_base - npk_penalty, 0.0)

    # ── 3. Water Stress Score (25%) ───────────────────────────────────────────
    # WDI: Water Demand Index (0 = no stress, 1 = max stress) → invert
    # irr: 1.0 = optimal. Deviation in either direction is penalised.
    # rain: 600 mm considered adequate for kharif season
    wdi_score   = (1.0 - wdi)  * 100.0
    irr_score = max((1.0 - abs(1.0 - irr)) * 100.0, 0.0)   # add max(..., 0.0)
    rain_score  = min((rain / 600.0) * 100.0, 100.0)
    water_score = (0.5 * wdi_score) + (0.3 * irr_score) + (0.2 * rain_score)

    # ── 4. Climate Risk Score (15%) ───────────────────────────────────────────
    # Temperature stress penalties (above threshold = crop stress):
    #   Kharif: every degree above 35°C → -5 points
    #   Rabi  : every degree above 25°C → -5 points
    kharif_stress = max(0.0, kharif_temp - 35.0) * 5.0
    rabi_stress   = max(0.0, rabi_temp   - 25.0) * 5.0
    climate_score = max(100.0 - (kharif_stress + rabi_stress), 0.0)

    # ── 5. NDVI Vegetation Score (15%) ────────────────────────────────────────
    # NDVI range 0–1; scale to 0–100.  (NDVI 0.80 → 100 score)
    # If no satellite data available, proxy from yield score.
    if ndvi is not None:
        ndvi_score  = min(ndvi * 125.0, 100.0)
        ndvi_source = f"satellite ({ndvi:.2f})"
    else:
        ndvi_score  = min(yield_score * 0.8, 100.0)
        ndvi_source = "yield proxy"

    # ── Final Weighted Sum ────────────────────────────────────────────────────
    final = round(
        (yield_score   * 0.25) +
        (soil_final    * 0.20) +
        (water_score   * 0.25) +
        (climate_score * 0.15) +
        (ndvi_score    * 0.15),
        2,
    )

    # ── Risk Level & Loan Decision ────────────────────────────────────────────
    if final >= 65.0:
        risk_level    = "LOW"
        loan_decision = "ELIGIBLE"
    elif final >= 45.0:
        risk_level    = "MEDIUM"
        loan_decision = "REVIEW"
    else:
        risk_level    = "HIGH"
        loan_decision = "INELIGIBLE"

    logger.info(
        "Health score: final=%.2f  risk=%s  decision=%s",
        final, risk_level, loan_decision,
    )

    return {
        "final_health_score": final,
        "yield_score":        round(yield_score,   2),
        "soil_score":         round(soil_final,    2),
        "water_score":        round(water_score,   2),
        "climate_score":      round(climate_score, 2),
        "ndvi_score":         round(ndvi_score,    2),
        "ndvi_source":        ndvi_source,
        "benchmark_yield":    round(benchmark_yield, 2) if benchmark_yield else None,
        "risk_level":         risk_level,
        "loan_decision":      loan_decision,
    }
