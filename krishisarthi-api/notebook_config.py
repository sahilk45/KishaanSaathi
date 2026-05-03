r"""
notebook_config.py — Shared config loader for all KrishiSarthi Jupyter Notebooks
==================================================================================
Usage (first cell of any notebook):
    import sys, os
    sys.path.insert(0, r"D:\CA_content\Python\KissanSathi\krishisarthi-api")
    from notebook_config import *
    print("Config loaded:", MODEL_DIR_ABS)

All values are read from the project root .env file automatically.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import joblib

# ── Load .env from project root ───────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

# ── Database ──────────────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL")

# ── Session / Test Farmer ─────────────────────────────────────────────────────
SESSION_FARMER_ID = os.getenv("SESSION_FARMER_ID", "c59f6f44-1a98-4eaa-8cf0-3581316a32bb")

# ── Model Paths ───────────────────────────────────────────────────────────────
MODEL_DIR         = os.getenv("MODEL_DIR_ABS", str(_PROJECT_ROOT / "Encoder_and_model"))
XGB_MODEL_PATH    = os.getenv("XGB_MODEL_PATH",    str(Path(MODEL_DIR) / "krishi_twin_xgb_model_complete.pkl"))
CROP_ENC_PATH     = os.getenv("CROP_ENCODER_PATH", str(Path(MODEL_DIR) / "crop_encoder.pkl"))
STATE_ENC_PATH    = os.getenv("STATE_ENCODER_PATH",str(Path(MODEL_DIR) / "state_encoder.pkl"))

# ── Data Paths ────────────────────────────────────────────────────────────────
MANDI_JSON_PATH   = os.getenv("MANDI_JSON_PATH", str(_PROJECT_ROOT / "data" / "mandi_master.json"))
CSV_PATH          = os.getenv("CSV_PATH_ABS",    str(_PROJECT_ROOT / "Dataset" / "KrishiTwin_Final_Engineered.csv"))

# ── External API URLs ─────────────────────────────────────────────────────────
AGMARKNET_URL     = os.getenv("AGMARKNET_URL",  "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070")
OPEN_METEO_URL    = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")

# ── API Keys ──────────────────────────────────────────────────────────────────
GROQ_API_KEY      = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY")
AGMARKNET_API_KEY = os.getenv("AGMARKNET_API_KEY") or os.getenv("APMC_MANDI_API_KEY")
AGRO_API_KEY      = os.getenv("AGRO_API_KEY")

# ── Load ML Models ────────────────────────────────────────────────────────────
_xgb      = joblib.load(XGB_MODEL_PATH)
_le_crop  = joblib.load(CROP_ENC_PATH)
_le_state = joblib.load(STATE_ENC_PATH)

print(f"Config loaded from: {_PROJECT_ROOT}")
print(f"  MODEL_DIR  : {MODEL_DIR}")
print(f"  MANDI_JSON : {MANDI_JSON_PATH}")
print(f"  XGB Model  : loaded ({_xgb.n_estimators} estimators)")
print(f"  Crops      : {len(_le_crop.classes_)} | States: {len(_le_state.classes_)}")
print(f"  Farmer ID  : {SESSION_FARMER_ID}")
