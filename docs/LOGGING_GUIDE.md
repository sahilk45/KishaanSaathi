"""
STRUCTURED LOGGING GUIDE — KrishanSaathi API
==============================================

This document explains the comprehensive structured logging system implemented
across the KrishanSaathi API. Use it to understand what data is real vs. hardcoded,
and to debug issues.

## Overview

The logging system provides **structured JSON logs** that clearly distinguish between:
1. **REAL DATA** — From databases, APIs, and sensors
2. **HARDCODED/MOCK DATA** — Default/test values
3. **PREDICTIONS** — ML model outputs
4. **DATABASE OPERATIONS** — Queries and data retrieval
5. **API CALLS** — External service integrations
6. **TOOL EXECUTIONS** — Chatbot tool invocations
7. **COMPUTATIONS** — Calculated values
8. **ERRORS** — Failures and exceptions

## Getting Started

### 1. Enable Logging in Environment

```bash
# Optional: Save logs to file (in addition to console)
export LOG_FILE=logs/krishisarthi.log

# Run the API
uvicorn main:app --reload --port 8000
```

### 2. Understanding Log Output

Each log entry is a JSON object with:

```json
{
    "timestamp": "2026-04-23T15:30:45.123456Z",
    "logger": "krishisarthi_api.models_loader",
    "event": "models_loaded_from_disk",
    "source": "[REAL] FILE_SYSTEM",
    "severity": "INFO",
    "data": {...},
    "data_type": "PREDICTION"
}
```

### 3. Log Types & Examples

#### A. Real Data (from DB, API, Sensors)

**Log Entry Example:**
```python
logger.log_real_data(
    event_type="weather_fetched",
    data={"temp": 32.5, "humidity": 65},
    source="AgroMonitoring"
)
```

**JSON Output:**
```json
{
    "event": "weather_fetched",
    "source": "[REAL] AgroMonitoring",
    "data": {"actual_data": {"temp": 32.5, "humidity": 65}},
    "data_type": "REAL"
}
```

**What to look for:** ✅ REAL data means the values came from an external API, database, or sensor.

---

#### B. Hardcoded/Mock Data (Default Values, Test Mode)

**Log Entry Example:**
```python
logger.log_hardcoded(
    event_type="weather_fetched_mock",
    data={"temp": 32.0, "humidity": 68},
    reason="AGRO_API_KEY not configured"
)
```

**JSON Output:**
```json
{
    "event": "weather_fetched_mock",
    "source": "[HARDCODED]",
    "severity": "WARNING",
    "data": {"hardcoded_value": {...}},
    "data_type": "HARDCODED",
    "reason": "AGRO_API_KEY not configured"
}
```

**What to look for:** ⚠️ HARDCODED data means you're in test/demo mode. Check the `reason` field to see why real data wasn't available.

---

#### C. Model Predictions

**Log Entry Example:**
```python
logger.log_prediction(
    event_type="yield_predicted",
    data={"predicted_yield": 1850, "confidence": 0.92},
    model_name="XGBoost",
    confidence=0.92
)
```

**JSON Output:**
```json
{
    "event": "yield_predicted",
    "source": "[PREDICTION] XGBoost",
    "data": {
        "prediction": {"predicted_yield": 1850, "confidence": 0.92},
        "model": "XGBoost",
        "confidence": 0.92
    },
    "data_type": "PREDICTION"
}
```

**What to look for:** The `[PREDICTION]` marker indicates the value is output from the ML model, not real observed data.

---

#### D. Database Operations

**Log Entry Example:**
```python
logger.log_db_operation(
    event_type="farmer_retrieved",
    data={"farmer_name": "Rajesh Kumar", "state": "Punjab"},
    operation="SELECT",
    table="farmers",
    rows_affected=1
)
```

**JSON Output:**
```json
{
    "event": "farmer_retrieved",
    "source": "[DATABASE] SELECT",
    "data": {
        "operation": "SELECT",
        "result": {...},
        "table": "farmers",
        "rows_affected": 1
    },
    "data_type": "DATABASE"
}
```

**What to look for:** The `operation` field (SELECT, INSERT, UPDATE, DELETE) tells you what happened to the database.

---

#### E. API Calls (to external services)

**Log Entry Example:**
```python
logger.log_api_call(
    event_type="groq_inference",
    data={"response": "Here's crop advice..."},
    endpoint="/chat/completions",
    status_code=200,
    method="POST",
    api_name="Groq"
)
```

**JSON Output:**
```json
{
    "event": "groq_inference",
    "source": "[API] Groq",
    "data": {
        "api": "Groq",
        "method": "POST",
        "endpoint": "/chat/completions",
        "status_code": 200,
        "response": "Here's crop advice..."
    },
    "data_type": "API_CALL"
}
```

**What to look for:** Check `status_code` (200 = success, 4xx/5xx = error). Look at `endpoint` to see which API was called.

---

#### F. Tool Executions (Chatbot tools)

**Log Entry Example:**
```python
logger.log_tool_execution(
    event_type="get_weather_executed",
    data={"temp": 32, "rainfall": 5},
    tool_name="get_weather",
    duration_ms=450
)
```

**JSON Output:**
```json
{
    "event": "get_weather_executed",
    "source": "[TOOL] get_weather",
    "data": {
        "tool": "get_weather",
        "result": {"temp": 32, "rainfall": 5},
        "duration_ms": 450
    },
    "data_type": "TOOL"
}
```

**What to look for:** `duration_ms` shows if the tool is slow. `result` shows what the tool returned.

---

#### G. Computations (Calculated values)

**Log Entry Example:**
```python
logger.log_computation(
    event_type="health_score_calculated",
    data={"score": 72.5, "components": {"yield": 80, "soil": 70}},
    computation_type="weighted_average"
)
```

**JSON Output:**
```json
{
    "event": "health_score_calculated",
    "source": "[COMPUTATION] weighted_average",
    "data": {"computed_value": {...}},
    "data_type": "COMPUTATION"
}
```

**What to look for:** This shows explicitly computed/derived values, not direct measurements.

---

#### H. Errors

**Log Entry Example:**
```python
logger.log_error(
    event_type="database_connection_failed",
    error=connection_error,
    context={"database": "neon_postgres", "retry_count": 3}
)
```

**JSON Output:**
```json
{
    "event": "database_connection_failed",
    "source": "[ERROR]",
    "severity": "ERROR",
    "data": {
        "error_type": "ConnectionRefusedError",
        "error_message": "Connection refused on port 5432",
        "context": {"database": "neon_postgres", "retry_count": 3}
    },
    "data_type": "ERROR"
}
```

**What to look for:** `error_type` tells you what went wrong, `error_message` provides details, `context` shows where it happened.

---

## Common Log Patterns

### Pattern 1: Finding Real vs. Hardcoded Data

```bash
# Search for REAL data
grep '"source": "\[REAL\]' logs/krishisarthi.log

# Search for HARDCODED/MOCK data
grep '"source": "\[HARDCODED\]' logs/krishisarthi.log

# Find WARNINGS (often indicates test mode or data quality issues)
grep '"severity": "WARNING"' logs/krishisarthi.log
```

### Pattern 2: Tracing a Prediction Flow

```bash
# 1. User asks for prediction
grep "chat_message_received" logs/krishisarthi.log

# 2. Data is retrieved (real or hardcoded?)
grep "farmer_retrieved\|weather_fetched" logs/krishisarthi.log

# 3. Model runs
grep "yield_predicted" logs/krishisarthi.log

# 4. Result cached
grep "field_predictions.*INSERT" logs/krishisarthi.log
```

### Pattern 3: Debugging API Failures

```bash
# Find failed API calls
grep '"status_code": [45]' logs/krishisarthi.log

# Or
grep '\[API\].*ERROR' logs/krishisarthi.log

# Check API errors
grep 'api_error' logs/krishisarthi.log
```

### Pattern 4: Monitoring Data Flow

```bash
# Track what data is coming from each source
grep '\[REAL\]' logs/krishisarthi.log | grep -o '"source": "[^"]*"' | sort | uniq -c

# Example output:
#   5 "[REAL] AgroMonitoring"
#   3 "[REAL] DATABASE"
#   8 "[HARDCODED]"
```

---

## Using the Logging Utilities

### In Your Own Code

```python
from logger_config import get_logger

logger = get_logger(__name__)

# Log real data from API
response = await fetch_weather_api(farmer_id)
logger.log_real_data(
    "weather_api_response",
    response,
    source="OpenWeatherMap"
)

# Log hardcoded fallback
if not response:
    logger.log_hardcoded(
        "weather_fallback",
        {"temp": 28, "humidity": 60},
        reason="API timeout after 3 retries"
    )

# Log model prediction
prediction = model.predict(features)
logger.log_prediction(
    "yield_model_prediction",
    {"yield_kg_ha": prediction},
    model_name="XGBoost",
    confidence=0.87
)

# Log database operation
farmer = await db.fetch("SELECT * FROM farmers WHERE id = $1", farmer_id)
logger.log_db_operation(
    "farmer_lookup",
    farmer,
    operation="SELECT",
    table="farmers",
    rows_affected=1
)

# Log error
try:
    await risky_operation()
except Exception as e:
    logger.log_error("operation_failed", e, context={"retry_count": 3})
```

### Database Logging Helpers

```python
from db_logging import log_query, log_insert, log_update

# For SELECT
result = await conn.fetch("SELECT * FROM farmers WHERE state = $1", "Punjab")
log_query("list_punjab_farmers", result, table="farmers", rows_count=len(result))

# For INSERT
await conn.execute("INSERT INTO farmers ...")
log_insert("new_farmer_created", result, table="farmers")

# For UPDATE
rows_affected = await conn.execute("UPDATE farmers SET ...")
log_update("farmer_updated", result, table="farmers", rows_affected=rows_affected)
```

### API Logging Helpers

```python
from api_logging import log_api_request, log_api_response, log_api_error

# Request
log_api_request("AgroMonitoring", "GET", "/weather", params={"id": poly_id})

# Response
response = await client.get(url)
log_api_response("AgroMonitoring", response.status_code, response.json())

# Error
log_api_error("AgroMonitoring", error_obj, endpoint="/weather")

# Mock response
log_mock_api_response("AgroMonitoring", mock_weather, reason="API key missing")
```

---

## Environment Variables

```bash
# Set log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# Optional: Save logs to file
LOG_FILE=logs/krishisarthi.log

# Data sources (when configured, real data is used; otherwise defaults to mock)
AGRO_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
DATABASE_URL=postgresql://...
```

---

## Reading JSON Logs

### With `jq` (recommended)

```bash
# Pretty-print logs
cat logs/krishisarthi.log | jq '.'

# Filter by data type
cat logs/krishisarthi.log | jq 'select(.data_type == "REAL")'

# Filter by source
cat logs/krishisarthi.log | jq 'select(.source | contains("AgroMonitoring"))'

# Extract just the events
cat logs/krishisarthi.log | jq -r '.event'

# Get all hardcoded values
cat logs/krishisarthi.log | jq 'select(.data_type == "HARDCODED") | .data.hardcoded_value'
```

### With `grep` and `python`

```bash
# Convert newline-separated JSON to pretty format
python -m json.tool logs/krishisarthi.log

# Extract specific field
grep '"event": "yield_predicted"' logs/krishisarthi.log | python -m json.tool
```

---

## Troubleshooting

### Q: I see lots of HARDCODED entries. What does it mean?

**A:** The API keys for external services (AgroMonitoring, Groq) are not configured. The system is using default test values. Check:

```bash
echo $AGRO_API_KEY
echo $GROQ_API_KEY
```

If empty, the system will auto-generate mock data.

---

### Q: How do I know if the model is actually predicting or just returning hardcoded values?

**A:** Look for logs with `data_type: "PREDICTION"`. If you see model predictions, the ML model is active. If you only see HARDCODED logs, check if model files exist:

```bash
ls -la Encoder_and_model/
```

---

### Q: I want to see ONLY the real data flow. How?

**A:** Use grep to filter:

```bash
grep '"source": "\[REAL\]' logs/krishisarthi.log | jq '.'
```

Or in Python:

```python
import json

with open("logs/krishisarthi.log") as f:
    for line in f:
        log_entry = json.loads(line)
        if "[REAL]" in log_entry.get("source", ""):
            print(json.dumps(log_entry, indent=2))
```

---

### Q: The chatbot is slow. How do I find which tool is slow?

**A:** Look for TOOL logs with high `duration_ms`:

```bash
grep '"data_type": "TOOL"' logs/krishisarthi.log | jq 'select(.data.duration_ms > 1000)'
```

---

## Next Steps

1. **Enable file logging**: Set `LOG_FILE` env var to save logs
2. **Parse logs**: Use `jq` to filter and analyze logs
3. **Monitor production**: Consider centralized logging (ELK, Datadog, etc.)
4. **Set up alerts**: Alert when you see ERROR or too many HARDCODED logs

---

## Summary Table

| Log Type | Source | Indicates | Example |
|----------|--------|-----------|---------|
| REAL | [REAL] API | Actual external data | Weather from AgroMonitoring |
| HARDCODED | [HARDCODED] | Test/default values | Weather with no API key |
| PREDICTION | [PREDICTION] Model | ML model output | XGBoost yield prediction |
| DATABASE | [DATABASE] Operation | DB query result | SELECT from farmers table |
| API_CALL | [API] Service | External API call | POST to Groq |
| TOOL | [TOOL] Name | Chatbot tool ran | get_weather execution |
| COMPUTATION | [COMPUTATION] Type | Calculated value | Health score calculation |
| ERROR | [ERROR] | Exception/failure | Connection timeout |

"""

# Print to file as markdown
if __name__ == "__main__":
    with open("LOGGING_GUIDE.md", "w") as f:
        # Remove the triple quotes and print content
        f.write(__doc__)
    print("✅ LOGGING_GUIDE.md created!")
