# KrishiSarthi API 🌾

**Agri-Intelligence Platform** — Yield prediction, crop health scoring, and loan eligibility for Indian farmers using satellite data + machine learning.

---

## Project Structure

```
krishisarthi-api/
│
├── main.py                    # FastAPI application — all endpoints
├── database.py                # asyncpg pool + table creation
├── logger_config.py           # Structured logging (UTF-8 safe)
├── api_logging.py             # API-layer logging helpers
├── db_logging.py              # DB-layer logging helpers
├── pyproject.toml             # Project metadata & build config
├── requirements.txt           # Python dependencies
├── env.example                # Template for .env (copy & fill)
│
├── chatbot/                   # LangGraph AI chatbot
│   ├── agent.py               # Agent entrypoint (run_agent / streaming)
│   ├── db.py                  # Chatbot's own asyncpg pool
│   ├── graph/                 # LangGraph nodes & edges
│   │   └── nodes.py           # LLM provider selection (Groq / Gemini)
│   ├── models_loader.py       # Singleton model loader + prepare_features()
│   ├── tools/                 # Tool functions called by the agent
│   │   ├── get_farmer_data.py
│   │   ├── get_crop_advice.py
│   │   └── get_market_price.py
│   └── Mandi_ChatBot/         # Jupyter notebooks for chatbot dev
│
├── services/                  # Core business logic
│   ├── agro_service.py        # Agromonitoring API (NDVI, polygon, soil)
│   ├── health_score.py        # Final health score calculation
│   ├── imputation.py          # Weighted lag-average climate imputation
│   └── geocoding_service.py   # Reverse geocoding (city/state from GPS)
│
├── Encoder_and_model/         # PRODUCTION ML artifacts (do not edit)
│   ├── krishi_twin_xgb_model_complete.pkl  # XGBoost (500 trees, 33 features)
│   ├── crop_encoder.pkl       # LabelEncoder for 23 crop types
│   └── state_encoder.pkl      # LabelEncoder for 20 states
│
├── NoteBook/                  # Research & validation
│   ├── Model/                 # Training notebooks
│   │   ├── KrishiTwin_WalkForward_Model.ipynb   # Walk-Forward CV training
│   │   ├── Model_Training.ipynb                 # Original training notebook
│   │   ├── krishi_xgb_final.pkl                 # Mirror of production model
│   │   ├── krishi_twin_xgb_model_complete.pkl   # Production model copy
│   │   ├── crop_encoder.pkl
│   │   └── state_encoder.pkl
│   └── Validation/            # Automated validation scripts
│       ├── production_readiness_audit.py        # 5-point production audit
│       ├── dual_model_diagnostic.py             # Scale + bug verification
│       ├── full_validation_stats.py             # Full statistical benchmarks
│       ├── test_production_model.py             # Production model test
│       └── test_walkforward_model.py            # Walk-forward model test
│
├── Dataset/                   # Training data
│   └── KrishiTwin_Final_Engineered.csv          # 33-feature engineered dataset
│
├── data/                      # Runtime data
│   └── mandi_master.json      # Mandi price reference data
│
├── docs/                      # All documentation & reports
│   ├── deployment_report.md             # Production deployment verdict
│   ├── walkforward_model_analysis.md    # Walk-forward model R² analysis
│   ├── LOGGING_ARCHITECTURE.md
│   ├── LOGGING_GUIDE.md
│   ├── LOGGING_EXAMPLES.md
│   ├── README_LOGGING.md
│   ├── IMPLEMENTATION_CHECKLIST.md
│   ├── QUICK_REFERENCE_CHANGES.md
│   └── TOOL_FIX_SUMMARY.md
│
├── tests/                     # Integration & debug test scripts
│   ├── e2e_agra_test.py        # Full end-to-end Agra farmer test
│   ├── e2e_test.py
│   ├── test_agent.py
│   ├── test_fixes.py
│   ├── test_loop.py
│   ├── debug_loop.py
│   ├── check_farmer.py
│   ├── query_db.py
│   └── diagnose.py
│
└── scripts/                   # One-time setup & migration utilities
    ├── migrate_csv_to_postgres.py   # Load CSV into PostgreSQL
    ├── setup_test_farmer.py         # Create a test farmer in the DB
    └── schema_check.py              # Verify DB schema
```

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/sahilk45/krishisarthi-api.git
cd krishisarthi-api
pip install -r requirements.txt

# 2. Set environment variables
cp env.example .env
# Fill in: DATABASE_URL, GROQ_API_KEY, AGRO_API_KEY, AGMARKNET_API_KEY

# 3. Initialise DB
python scripts/migrate_csv_to_postgres.py

# 4. Run the API
uvicorn main:app --reload --port 8000
```

Interactive docs: **http://localhost:8000/docs**

---

## Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/farmers/register` | Register a new farmer |
| POST | `/farm/register` | Register field + draw satellite polygon |
| POST | `/predict` | **Main engine** — yield, health score, loan decision |
| GET | `/field/{field_id}/history` | All predictions for a field |
| GET | `/districts` | District + state dropdown data |
| POST | `/chat` | AI chatbot (Groq/Gemini powered) |
| GET | `/health` | API liveness check |

---

## ML Model Summary

| Property | Value |
|---|---|
| Algorithm | XGBoost Walk-Forward CV |
| Target | `log1p(Yield_kg_ha)` → inverse `np.expm1()` |
| Features | 33 (10 base + 18 lags + 3 deltas + 2 rolling avg) |
| R² Score | **0.86** on real crop data |
| MAE | 293 kg/ha |
| Latency | ~6.5 ms per prediction |
| Tier 1 Crops | Rice, Wheat, Maize, Rapeseed (R² > 0.40) |

See [`docs/deployment_report.md`](docs/deployment_report.md) for the full production readiness audit.

---

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `GROQ_API_KEY` | Groq LLM key (chatbot) |
| `GEMINI_API_KEY` | Google Gemini key (optional chatbot fallback) |
| `AGRO_API_KEY` | Agromonitoring API key (NDVI + satellite) |
| `AGMARKNET_API_KEY` | Agmarknet key (mandi price data) |
| `MODEL_DIR` | Override model directory (default: `Encoder_and_model`) |
