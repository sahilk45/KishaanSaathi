"""
chatbot/models_loader.py — Singleton ML model loader for the chatbot
=====================================================================
Loads the XGBoost model and label encoders once at startup.
Provides prepare_features() used by the What-If engine.

Adapts to the ACTUAL project structure:
  Encoder_and_model/krishi_twin_xgb_model.pkl  — XGBoost model (log1p target)
  Encoder_and_model/crop_encoder.pkl            — LabelEncoder for crop_type
  Encoder_and_model/state_encoder.pkl           — LabelEncoder for state_name

Benchmark yields are kept in-module (sourced from main.py CROP_BENCHMARKS).
"""

import os
import logging
import joblib

from dotenv import load_dotenv
from logger_config import get_logger

load_dotenv()

logger = get_logger(__name__)

# ── Paths (configurable via env vars) ─────────────────────────────────────────
MODEL_DIR = os.getenv("MODEL_DIR", "Encoder_and_model")
_XGB_MODEL_PATH = os.path.join(MODEL_DIR, "krishi_twin_xgb_model.pkl")
_CROP_ENC_PATH  = os.path.join(MODEL_DIR, "crop_encoder.pkl")
_STATE_ENC_PATH = os.path.join(MODEL_DIR, "state_encoder.pkl")

# ── Benchmark yields per crop (kg/ha) — same as main.py CROP_BENCHMARKS ───────
BENCHMARK_YIELDS: dict[str, float] = {
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

# ── Singleton state ────────────────────────────────────────────────────────────
_xgb_model  = None
_le_crop    = None
_le_state   = None


def get_models():
    """
    Returns (xgb_model, le_crop, le_state, benchmark_yields).
    Loads artifacts on first call; subsequent calls return cached objects.
    """
    global _xgb_model, _le_crop, _le_state

    if _xgb_model is None:
        logger.log_computation(
            "model_loading_started",
            {"model_dir": MODEL_DIR},
            computation_type="model_initialization"
        )
        try:
            _xgb_model = joblib.load(_XGB_MODEL_PATH)
            _le_crop   = joblib.load(_CROP_ENC_PATH)
            _le_state  = joblib.load(_STATE_ENC_PATH)
            
            logger.log_real_data(
                "models_loaded_from_disk",
                {
                    "xgb_model": _XGB_MODEL_PATH,
                    "crop_encoder": _CROP_ENC_PATH,
                    "state_encoder": _STATE_ENC_PATH,
                    "crop_classes_count": len(_le_crop.classes_),
                    "state_classes_count": len(_le_state.classes_),
                },
                source="FILE_SYSTEM"
            )
        except Exception as e:
            logger.log_error(
                "model_loading_failed",
                e,
                context={"model_dir": MODEL_DIR}
            )
            raise

    return _xgb_model, _le_crop, _le_state, BENCHMARK_YIELDS


def prepare_features(inputs: dict, le_crop, le_state) -> list:
    """
    Encodes categorical features and returns the ordered 10-feature list
    expected by the XGBoost model (must match training-time column order):

      year, State_Encoded, Crop_Encoded, NPK_Intensity_KgHa,
      Irrigation_Intensity_Ratio, WDI,
      Kharif_Avg_MaxTemp, Kharif_Total_Rain, Rabi_Avg_MaxTemp,
      District_Soil_Health_Score
    """
    try:
        crop_enc  = int(le_crop.transform([inputs["Crop_Type"]])[0])
    except ValueError:
        # Fallback: unknown crop → median encoded index
        crop_enc = len(le_crop.classes_) // 2

    try:
        state_enc = int(le_state.transform([inputs["State_Name"]])[0])
    except ValueError:
        state_enc = len(le_state.classes_) // 2

    return [
        inputs.get("year", 2026),
        state_enc,
        crop_enc,
        inputs["NPK_Intensity_KgHa"],
        inputs["Irrigation_Intensity_Ratio"],
        inputs["WDI"],
        inputs["Kharif_Avg_MaxTemp"],
        inputs["Kharif_Total_Rain"],
        inputs["Rabi_Avg_MaxTemp"],
        inputs["District_Soil_Health_Score"],
    ]
