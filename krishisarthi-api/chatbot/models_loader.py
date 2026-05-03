"""
chatbot/models_loader.py — Singleton ML model loader for the chatbot
=====================================================================
Loads the XGBoost model and label encoders once at startup.
Provides prepare_features() used by the What-If engine.

Adapts to the ACTUAL project structure:
  Encoder_and_model/krishi_kharif_xgb_final.pkl
  Encoder_and_model/krishi_rabi_xgb_final.pkl
  Encoder_and_model/kharif_feature_list.pkl
  Encoder_and_model/rabi_feature_list.pkl
  Encoder_and_model/crop_encoder.pkl
  Encoder_and_model/state_encoder.pkl

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
MODEL_DIR = os.getenv("MODEL_DIR_ABS", "Encoder_and_model")
if not os.path.isabs(MODEL_DIR):
    MODEL_DIR = os.path.join(os.getcwd(), MODEL_DIR)

_XGB_KHARIF_PATH  = os.path.join(MODEL_DIR, "krishi_kharif_xgb_final.pkl")
_XGB_RABI_PATH    = os.path.join(MODEL_DIR, "krishi_rabi_xgb_final.pkl")
_FEAT_KHARIF_PATH = os.path.join(MODEL_DIR, "kharif_feature_list.pkl")
_FEAT_RABI_PATH   = os.path.join(MODEL_DIR, "rabi_feature_list.pkl")
_CROP_ENC_PATH    = os.path.join(MODEL_DIR, "crop_encoder.pkl")
_STATE_ENC_PATH   = os.path.join(MODEL_DIR, "state_encoder.pkl")

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
_xgb_kharif      = None
_xgb_rabi        = None
_kharif_features = None
_rabi_features   = None
_le_crop         = None
_le_state        = None

# ── Routing Helpers ───────────────────────────────────────────────────────────
KHARIF_CROP_KEYWORDS = ['RICE', 'PEARL MILLET', 'GROUNDNUT', 'SUGARCANE',
                         'MAIZE', 'COTTON', 'SOYABEAN', 'SESAMUM',
                         'KHARIF SORGHUM', 'FINGER MILLET']
RABI_CROP_KEYWORDS   = ['CHICKPEA', 'WHEAT', 'MUSTARD', 'LENTIL',
                         'BARLEY', 'LINSEED', 'SAFFLOWER', 'RABI SORGHUM',
                         'RAPESEED']

KHARIF_ALT_CROPS = ['RICE YIELD (Kg per ha)', 'GROUNDNUT YIELD (Kg per ha)',
                     'PEARL MILLET YIELD (Kg per ha)']
RABI_ALT_CROPS   = ['WHEAT.YIELD.Kg.per.ha.', 'CHICKPEA YIELD (Kg per ha)']

def _is_kharif(crop_type: str) -> bool:
    cu = crop_type.upper()
    return any(k in cu for k in KHARIF_CROP_KEYWORDS)

def _current_season() -> str:
    """Returns 'kharif' (Jun–Oct) or 'rabi' (Nov–May) based on current month."""
    import datetime
    return "kharif" if datetime.datetime.now().month in [6,7,8,9,10] else "rabi"


def get_models():
    """
    Returns (_xgb_kharif, _xgb_rabi, _kharif_features, _rabi_features, _le_crop, _le_state, benchmark_yields).
    Loads artifacts on first call; subsequent calls return cached objects.
    """
    global _xgb_kharif, _xgb_rabi, _kharif_features, _rabi_features, _le_crop, _le_state

    if _xgb_kharif is None:
        logger.log_computation(
            "model_loading_started",
            {"model_dir": MODEL_DIR},
            computation_type="model_initialization"
        )
        try:
            _xgb_kharif      = joblib.load(_XGB_KHARIF_PATH)
            _xgb_rabi        = joblib.load(_XGB_RABI_PATH)
            _kharif_features = joblib.load(_FEAT_KHARIF_PATH)
            _rabi_features   = joblib.load(_FEAT_RABI_PATH)
            _le_crop         = joblib.load(_CROP_ENC_PATH)
            _le_state        = joblib.load(_STATE_ENC_PATH)
            
            logger.log_real_data(
                "models_loaded_from_disk",
                {
                    "xgb_kharif": _XGB_KHARIF_PATH,
                    "xgb_rabi": _XGB_RABI_PATH,
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

    return _xgb_kharif, _xgb_rabi, _kharif_features, _rabi_features, _le_crop, _le_state, BENCHMARK_YIELDS

