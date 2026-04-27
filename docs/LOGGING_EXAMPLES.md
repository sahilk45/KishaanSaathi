"""
BEFORE & AFTER EXAMPLES — Adding Structured Logging
====================================================

This file shows practical examples of adding structured logging to existing code.
Copy these patterns into your files.

---

## EXAMPLE 1: Database Query

### BEFORE (No Logging)
```python
async def get_farmer(farmer_id: str):
    async with get_db_connection() as conn:
        farmer = await conn.fetchrow(
            "SELECT * FROM farmers WHERE id = $1",
            farmer_id
        )
        return farmer
```

### AFTER (With Logging)
```python
from logger_config import get_logger

logger = get_logger(__name__)

async def get_farmer(farmer_id: str):
    async with get_db_connection() as conn:
        farmer = await conn.fetchrow(
            "SELECT * FROM farmers WHERE id = $1",
            farmer_id
        )
        
        # Log the database operation
        logger.log_db_operation(
            event_type="farmer_retrieved",
            data=farmer,
            operation="SELECT",
            table="farmers",
            rows_affected=1 if farmer else 0
        )
        
        return farmer
```

### WHAT YOU SEE IN LOGS
```json
{
    "event": "farmer_retrieved",
    "source": "[DATABASE] SELECT",
    "data_type": "DATABASE",
    "data": {
        "operation": "SELECT",
        "result": {"id": "...", "name": "Rajesh", "state": "Punjab", ...},
        "table": "farmers",
        "rows_affected": 1
    }
}
```

---

## EXAMPLE 2: External API Call

### BEFORE (No Logging)
```python
async def get_weather(polygon_id: str):
    url = f"{AGRO_BASE_URL}/weather"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            params={"appid": AGRO_KEY, "polyid": polygon_id},
            timeout=15
        )
        data = response.json()
        return data
```

### AFTER (With Logging)
```python
from logger_config import get_logger
from api_logging import log_api_request, log_api_response, log_api_error

logger = get_logger(__name__)

async def get_weather(polygon_id: str):
    url = f"{AGRO_BASE_URL}/weather"
    
    try:
        # Log outgoing request
        log_api_request(
            api_name="AgroMonitoring",
            method="GET",
            endpoint="/weather",
            params={"polyid": polygon_id}  # Note: appid hidden for security
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"appid": AGRO_KEY, "polyid": polygon_id},
                timeout=15
            )
            data = response.json()
            
            # Log response
            log_api_response(
                api_name="AgroMonitoring",
                status_code=response.status_code,
                response_data=data,
                endpoint="/weather"
            )
            
            # Also log as real data
            logger.log_real_data(
                event_type="weather_fetched",
                data=data,
                source="AgroMonitoring"
            )
            
            return data
            
    except Exception as e:
        log_api_error(
            api_name="AgroMonitoring",
            error=e,
            endpoint="/weather"
        )
        raise
```

### WHAT YOU SEE IN LOGS
```json
// Outgoing request
{"event": "api_request_/weather", "source": "[API] AgroMonitoring", "data": {"request_method": "GET", "endpoint": "/weather"}}

// Response
{"event": "api_response_/weather", "source": "[API] AgroMonitoring", "data": {"api": "AgroMonitoring", "status_code": 200, "response": {...}}}

// Actual data
{"event": "weather_fetched", "source": "[REAL] AgroMonitoring", "data": {"actual_data": {...}}}
```

---

## EXAMPLE 3: Hardcoded/Default Value

### BEFORE (No Indication It's Hardcoded)
```python
async def get_weather_or_default(farmer_id: str):
    if not AGRO_KEY:  # No API key
        return {
            "temp": 32.0,
            "humidity": 65,
            "rain": 0,
            "note": "Using default values"
        }
    
    # ... fetch real data ...
```

### AFTER (Clear Logging)
```python
from logger_config import get_logger

logger = get_logger(__name__)

async def get_weather_or_default(farmer_id: str):
    if not AGRO_KEY:  # No API key
        default_data = {
            "temp": 32.0,
            "humidity": 65,
            "rain": 0,
            "note": "Using default values"
        }
        
        # Log this as HARDCODED data
        logger.log_hardcoded(
            event_type="weather_using_defaults",
            data=default_data,
            reason="AGRO_API_KEY environment variable not set"
        )
        
        return default_data
    
    # ... fetch real data ...
```

### WHAT YOU SEE IN LOGS
```json
{
    "event": "weather_using_defaults",
    "source": "[HARDCODED]",
    "severity": "WARNING",
    "data": {"hardcoded_value": {"temp": 32.0, "humidity": 65, ...}},
    "reason": "AGRO_API_KEY environment variable not set"
}
```

**Key Point**: Anyone reading the logs immediately sees ⚠️ this is test/demo data, not production.

---

## EXAMPLE 4: ML Model Prediction

### BEFORE (No Logging)
```python
def predict_yield(features):
    model, le_crop, le_state, benchmarks = get_models()
    prediction = model.predict([features])
    yield_value = np.exp(prediction[0]) - 1  # Undo log1p transformation
    return {
        "yield_kg_ha": yield_value,
        "benchmark_kg_ha": benchmarks[crop]
    }
```

### AFTER (With Logging)
```python
from logger_config import get_logger

logger = get_logger(__name__)

def predict_yield(features):
    model, le_crop, le_state, benchmarks = get_models()
    prediction = model.predict([features])
    yield_value = np.exp(prediction[0]) - 1  # Undo log1p transformation
    
    result = {
        "yield_kg_ha": yield_value,
        "benchmark_kg_ha": benchmarks[crop]
    }
    
    # Log as PREDICTION (not real data!)
    logger.log_prediction(
        event_type="yield_predicted",
        data=result,
        model_name="XGBoost",
        confidence=0.87  # If you have confidence scores
    )
    
    return result
```

### WHAT YOU SEE IN LOGS
```json
{
    "event": "yield_predicted",
    "source": "[PREDICTION] XGBoost",
    "data_type": "PREDICTION",
    "data": {
        "prediction": {"yield_kg_ha": 1850, "benchmark_kg_ha": 1872},
        "model": "XGBoost",
        "confidence": 0.87
    }
}
```

**Key Point**: Logs clearly show this is MODEL OUTPUT, not measured/observed data.

---

## EXAMPLE 5: Tool Execution

### BEFORE (No Logging)
```python
@tool
async def get_crop_advice(crop: str, region: str) -> str:
    prompt = f"Give farming advice for {crop} in {region}"
    response = client.messages.create(
        model="mixtral-8x7b-32768",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
```

### AFTER (With Logging)
```python
import time
from logger_config import get_logger

logger = get_logger(__name__)

@tool
async def get_crop_advice(crop: str, region: str) -> str:
    start_time = time.time()
    
    try:
        prompt = f"Give farming advice for {crop} in {region}"
        
        # Log tool start
        logger.log_tool_execution(
            event_type="get_crop_advice_started",
            data={"crop": crop, "region": region},
            tool_name="get_crop_advice"
        )
        
        response = client.messages.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}]
        )
        
        result = response.content[0].text
        duration_ms = (time.time() - start_time) * 1000
        
        # Log tool result
        logger.log_tool_execution(
            event_type="get_crop_advice_completed",
            data={"advice": result},
            tool_name="get_crop_advice",
            duration_ms=duration_ms
        )
        
        return result
        
    except Exception as e:
        logger.log_error(
            "get_crop_advice_failed",
            e,
            context={"crop": crop, "region": region}
        )
        raise
```

### WHAT YOU SEE IN LOGS
```json
// Start
{"event": "get_crop_advice_started", "source": "[TOOL] get_crop_advice", "data": {"tool": "get_crop_advice", "result": {"crop": "Rice", "region": "Punjab"}}}

// End
{"event": "get_crop_advice_completed", "source": "[TOOL] get_crop_advice", "data": {"tool": "get_crop_advice", "result": {"advice": "Water regularly..."}, "duration_ms": 450}}
```

---

## EXAMPLE 6: Error Handling

### BEFORE (Basic Logging)
```python
async def register_farmer(name, phone, state, district):
    try:
        async with get_db_connection() as conn:
            result = await conn.execute(
                "INSERT INTO farmers (name, phone, state_name, dist_name) VALUES ($1, $2, $3, $4)",
                name, phone, state, district
            )
            return {"success": True}
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}
```

### AFTER (Structured Error Logging)
```python
from logger_config import get_logger

logger = get_logger(__name__)

async def register_farmer(name, phone, state, district):
    try:
        async with get_db_connection() as conn:
            result = await conn.execute(
                "INSERT INTO farmers (name, phone, state_name, dist_name) VALUES ($1, $2, $3, $4)",
                name, phone, state, district
            )
            
            # Log successful insertion
            logger.log_db_operation(
                event_type="farmer_registered",
                data={"name": name, "phone": phone},
                operation="INSERT",
                table="farmers",
                rows_affected=1
            )
            
            return {"success": True}
            
    except Exception as e:
        # Log error with context
        logger.log_error(
            event_type="farmer_registration_failed",
            error=e,
            context={
                "name": name,
                "phone": phone,
                "state": state,
                "district": district
            }
        )
        return {"error": str(e)}
```

### WHAT YOU SEE IN LOGS
```json
// Success
{"event": "farmer_registered", "source": "[DATABASE] INSERT", "data_type": "DATABASE", "data": {"operation": "INSERT", "table": "farmers", "rows_affected": 1}}

// Error
{"event": "farmer_registration_failed", "source": "[ERROR]", "severity": "ERROR", "data": {"error_type": "UniqueViolationError", "error_message": "Duplicate phone number", "context": {"phone": "9876543210"}}}
```

---

## EXAMPLE 7: Computed Value / Calculation

### BEFORE (No Indication Value Is Computed)
```python
def calculate_health_score(yield_score, soil_score, water_score):
    health_score = (yield_score * 0.3) + (soil_score * 0.3) + (water_score * 0.4)
    return health_score
```

### AFTER (Clear Logging)
```python
from logger_config import get_logger

logger = get_logger(__name__)

def calculate_health_score(yield_score, soil_score, water_score):
    health_score = (yield_score * 0.3) + (soil_score * 0.3) + (water_score * 0.4)
    
    # Log the computation
    logger.log_computation(
        event_type="health_score_calculated",
        data={
            "final_score": health_score,
            "components": {
                "yield_score": yield_score,
                "soil_score": soil_score,
                "water_score": water_score
            },
            "weights": {"yield": 0.3, "soil": 0.3, "water": 0.4}
        },
        computation_type="weighted_average"
    )
    
    return health_score
```

### WHAT YOU SEE IN LOGS
```json
{
    "event": "health_score_calculated",
    "source": "[COMPUTATION] weighted_average",
    "data_type": "COMPUTATION",
    "data": {
        "computed_value": {
            "final_score": 65.5,
            "components": {"yield_score": 70, "soil_score": 60, "water_score": 65},
            "weights": {"yield": 0.3, "soil": 0.3, "water": 0.4}
        }
    }
}
```

---

## QUICK COPY-PASTE SNIPPETS

### Just import these at the top of your file:
```python
from logger_config import get_logger
from db_logging import log_query, log_insert, log_update
from api_logging import log_api_request, log_api_response, log_api_error

logger = get_logger(__name__)
```

### For database: just call:
```python
result = await conn.fetch(query)
log_query("operation_name", result, table="table_name", rows_count=len(result))
```

### For API: just call:
```python
response = await client.get(url)
log_api_response("ServiceName", response.status_code, response.json())
```

### For defaults/hardcoded:
```python
logger.log_hardcoded("event_name", default_value, reason="Why you're using it")
```

---

## Summary

| Pattern | Function | Use When |
|---------|----------|----------|
| `log_real_data()` | Data from DB/API/sensors | Actual external data |
| `log_hardcoded()` | Test/default values | No API key or test mode |
| `log_prediction()` | ML model output | Model makes a prediction |
| `log_db_operation()` | Database queries | SELECT/INSERT/UPDATE/DELETE |
| `log_api_call()` | External API calls | Call to Groq, AgroMonitoring, etc. |
| `log_tool_execution()` | Tool runs | Chatbot tools run |
| `log_computation()` | Calculated values | Explicit calculation/derivation |
| `log_error()` | Exceptions | Something goes wrong |

---

**Remember**: Your future self (and your team) will thank you for logging! 🎯
"""

if __name__ == "__main__":
    print(__doc__)
