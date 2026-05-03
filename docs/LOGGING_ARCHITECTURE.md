# Structured Logging Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                  KrishanSaathi API                              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  main.py       │
        │  Endpoints     │
        └────┬───────────┘
             │
             ├──► POST /predict
             ├──► POST /chat
             ├──► POST /farmers/register
             └──► GET /weather
             
                 │
                 ▼
        ┌─────────────────────┐
        │  StructuredLogger   │ ◄─── logger_config.py
        │  (Central Hub)      │
        └────┬────────────────┘
             │
             ├─────────────────────────────────────────────┐
             │                                             │
             ▼                                             ▼
      ┌──────────────┐                            ┌──────────────────┐
      │  JSON Logs   │                            │  Console Output  │
      │  (Structured)│                            │  (Formatted)     │
      └──────────────┘                            └──────────────────┘
             │
             ├──► File: logs/krishisarthi.log
             ├──► AWS CloudWatch (future)
             ├──► Datadog (future)
             └──► Elasticsearch (future)
```

---

## Data Flow with Logging

```
1. REQUEST ARRIVES
   ┌─────────────────────────┐
   │ POST /predict           │
   │ farmer_id, crop, year   │
   └────────────┬────────────┘
                │
                ▼
        LOG: event_received
        source: [API_REQUEST]

2. LOAD FARMER DATA
   ┌──────────────────────────┐
   │ Database Query (SELECT)  │
   └────────────┬─────────────┘
                │
                ├─► [REAL] if found
                │   log_db_operation("farmer_retrieved", data, operation="SELECT")
                │
                └─► [ERROR] if not found
                    log_error("farmer_not_found")

3. FETCH WEATHER DATA
   ┌──────────────────────────┐
   │ Call AgroMonitoring API  │
   └────────────┬─────────────┘
                │
                ├─► [REAL] if API_KEY set
                │   log_api_call("weather_fetched", status=200)
                │
                └─► [HARDCODED] if no API_KEY
                    log_hardcoded("weather_mock", reason="No AGRO_API_KEY")

4. PREDICT YIELD
   ┌──────────────────────────┐
   │ XGBoost Model Inference  │
   └────────────┬─────────────┘
                │
                ▼
        LOG: [PREDICTION] yield_predicted
        log_prediction("yield_predicted", model_name="XGBoost")

5. CALCULATE HEALTH SCORE
   ┌──────────────────────────┐
   │ Weighted Calculation     │
   └────────────┬─────────────┘
                │
                ▼
        LOG: [COMPUTATION] health_score_calculated
        log_computation("health_score_calculated", computation_type="weighted_average")

6. GENERATE ADVICE
   ┌──────────────────────────┐
   │ Call Groq LLM           │
   └────────────┬─────────────┘
                │
                ▼
        LOG: [API] groq_advice
        log_api_call("advice_generated", status=200, api_name="Groq")

7. STORE RESULT
   ┌──────────────────────────┐
   │ Database INSERT          │
   └────────────┬─────────────┘
                │
                ▼
        LOG: [DATABASE] prediction_cached
        log_db_operation("prediction_cached", operation="INSERT", table="field_predictions")

8. RESPONSE SENT
   ┌──────────────────────────┐
   │ JSON Response to Client  │
   └────────────┬─────────────┘
                │
                ▼
        LOG: [RESPONSE] prediction_complete
        status: 200
```

---

## Log Type Decision Tree

```
                         ┌─────────────────┐
                         │  Event Occurred │
                         └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
                    ▼             ▼             ▼
              Is it an      Is it from      Is it a
              ERROR?        external        MODEL?
                │           source?         │
         ┌──────┴──────┐      │         ┌────┴─────┐
         │             │      ▼         │          │
      YES│         NO│  ┌──────┐    YES│      NO│
         │             │  │DB?   │       │        │
         ▼             │  │API?   │       ▼        ▼
    log_error()        │  └──────┘   log_prediction() Is it
         │             │     │                      calculated?
         │         ┌───┴─────┴────┐                 │
         │         │              │             ┌───┴────┐
         │      YES│          NO│ │          YES│     NO│
         │         │              │ │          │        │
         │         ▼              ▼ ▼          ▼        ▼
         │    Did it       Is it a      log_computation()
         │    succeed?     tool?         │
         │     │           │             │
         │  ┌──┴──┐      ┌──┴──┐         │
         │  │     │     YES│  │         │
         │YES│  NO│     │    NO│         │
         │  │     │     ▼    │          │
         │  ▼     ▼  log_tool_execution() │
         │ [REAL][ERROR]     │          │
         │         ▼         │          │
         │      log_api_call()           │
         │      log_db_operation()       │
         │                               │
         └───────────────────────────────┘
```

---

## Log Entry Structure

```json
{
    "timestamp": "2026-04-23T15:30:45.123456Z",
    "logger": "krishisarthi_api.main",
    "event": "yield_predicted",
    "source": "[PREDICTION] XGBoost",
    "severity": "INFO",
    "data": {
        "prediction": {
            "yield_kg_ha": 1850,
            "confidence": 0.92
        },
        "model": "XGBoost",
        "confidence": 0.92
    },
    "data_type": "PREDICTION",
    "duration_ms": 250,
    "context": {...}
}
```

---

## Logger API (Functions Available)

```
StructuredLogger
├── log_real_data(event, data, source)
│   └─ Use when: Data from API, DB, or sensor
│
├── log_hardcoded(event, data, reason)
│   └─ Use when: Default/test values
│
├── log_mock(event, data, reason)
│   └─ Use when: Synthetic data for testing
│
├── log_prediction(event, data, model, confidence)
│   └─ Use when: ML model output
│
├── log_db_operation(event, data, operation, table, rows_affected)
│   └─ Use when: SELECT, INSERT, UPDATE, DELETE
│
├── log_api_call(event, data, endpoint, status, api_name)
│   └─ Use when: External API call
│
├── log_tool_execution(event, data, tool_name, duration)
│   └─ Use when: Tool execution (get_weather, etc.)
│
├── log_computation(event, data, computation_type)
│   └─ Use when: Calculated/derived value
│
└── log_error(event, error, context)
    └─ Use when: Exception or failure
```

---

## Data Sources Tracking

```
┌──────────────────────────────────────────────────────────┐
│         Log Source Markers (in every log)                │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ [REAL] DATABASE       ← Data from PostgreSQL            │
│ [REAL] AgroMonitoring ← Data from satellite/weather API │
│ [REAL] FILE_SYSTEM    ← Data from files                 │
│ [REAL] OpenWeatherMap ← Data from 3rd party API         │
│                                                          │
│ [HARDCODED]           ← Default test values             │
│ [MOCK]                ← Synthetic test data             │
│                                                          │
│ [PREDICTION] XGBoost  ← ML model output                 │
│ [PREDICTION] LLM      ← Language model output           │
│                                                          │
│ [DATABASE] SELECT     ← Query operation type            │
│ [DATABASE] INSERT                                       │
│ [DATABASE] UPDATE                                       │
│ [DATABASE] DELETE                                       │
│                                                          │
│ [API] Groq            ← External service name           │
│ [API] AgroMonitoring                                    │
│ [API] OpenWeatherMap                                    │
│                                                          │
│ [TOOL] get_weather    ← Tool name                       │
│ [TOOL] get_crop_advice                                  │
│ [TOOL] get_market_price                                 │
│                                                          │
│ [COMPUTATION] weighted_average ← Calculation type       │
│ [COMPUTATION] health_score                              │
│ [COMPUTATION] imputation                                │
│                                                          │
│ [ERROR]               ← Exception/failure               │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## Typical Request Lifecycle with Logs

```
Time  Event                           Log Entry
────  ──────────────────────────────  ─────────────────────────────
  0ms  User requests prediction       POST /predict
       │
  2ms  ├─ Load farmer data           [REAL] DATABASE "farmer_retrieved"
       │
  5ms  ├─ Check cache                [DATABASE] cache_check
       │
 10ms  ├─ Fetch weather              [REAL] AgroMonitoring (or [HARDCODED])
       │
 50ms  ├─ Load ML model              [REAL] FILE_SYSTEM "model_loaded"
       │
 75ms  ├─ Make prediction            [PREDICTION] XGBoost "yield_predicted"
       │
100ms  ├─ Calculate health score     [COMPUTATION] "health_score_calculated"
       │
120ms  ├─ Generate advice            [API] Groq "crop_advice_generated"
       │
130ms  ├─ Cache result               [DATABASE] "prediction_cached"
       │
135ms  └─ Return response            Response: 200 OK
```

---

## Distinguishing Real vs. Test Data

```
Real Data Flow:                   Test/Hardcoded Flow:
───────────────                   ──────────────────

Logs show:                        Logs show:
[REAL] source                     [HARDCODED] or [MOCK]
↓                                 ↓
status_code: 200                  reason: "API_KEY not set"
↓                                 ↓
data: actual_external_data        data: synthetic_default_data
↓                                 ↓
Farmer sees real predictions      Farmer sees demo predictions

Check:                            Check:
- AGRO_API_KEY set?              - Missing AGRO_API_KEY?
- DATABASE_URL valid?            - Missing DATABASE_URL?
- GROQ_API_KEY set?              - Missing GROQ_API_KEY?
- API responses 200?             - API responses 4xx/5xx?
```

---

## Integration Points

```
┌────────────────────────────────────────────────────────────┐
│                    KrishanSaathi Logger                    │
└────────┬──────────────────────────────────────────────────┘
         │
    ┌────┴────────────────────┬────────────────────────────┐
    │                         │                            │
    ▼                         ▼                            ▼
Console                   File                    Log Aggregators
(Real-time)            (logs/*.log)               (Future: ELK, Datadog)
    │                       │                            │
    ├─► Terminal            ├─► Searchable              ├─► Centralized
    │   output              │   File                    │   analysis
    │                       │                            │
    └─► JSON                └─► JSON                    └─► JSON
        formatted               formatted                   formatted
```

---

## Implementation Timeline

```
Phase 1: Infrastructure (✅ DONE)
├─ logger_config.py
├─ db_logging.py
├─ api_logging.py
└─ Documentation

Phase 2: Core Modules (🔄 IN PROGRESS)
├─ chatbot/agent.py
├─ chatbot/context_builder.py
├─ chatbot/tools/*.py
└─ main.py endpoints

Phase 3: Services (⏳ NEXT)
├─ services/agro_service.py
├─ services/health_score.py
├─ services/imputation.py
└─ services/geocoding_service.py

Phase 4: Monitoring (⏳ FUTURE)
├─ Log aggregation
├─ Dashboards
└─ Alerts
```

---

**Note**: This architecture ensures that every piece of data flowing through the system is tracked with clear indicators of whether it's real, hardcoded, or computed.
