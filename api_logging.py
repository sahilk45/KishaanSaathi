"""
api_logging.py — API call logging helpers
==========================================
Provides utility functions for logging external API calls and responses.
Makes it easy to track:
  - API request/response
  - Status codes
  - Errors and timeouts
  - Which source (AgroMonitoring, Groq, etc.)

Usage:
    from api_logging import log_api_request, log_api_response, log_api_error
    
    # Log outgoing request
    log_api_request("AgroMonitoring", "GET", "/weather", params={"appid": key})
    
    # Log response
    response = await client.get(...)
    log_api_response("AgroMonitoring", response.status_code, response.json())
    
    # Log error
    log_api_error("AgroMonitoring", error_obj, context={"endpoint": "/weather"})
"""

from logger_config import get_logger
from typing import Any, Optional
import json

logger = get_logger(__name__)


def log_api_request(
    api_name: str,
    method: str,
    endpoint: str,
    params: Optional[dict] = None,
    body: Optional[dict] = None,
) -> None:
    """Log an outgoing API request."""
    data = {
        "request_method": method,
        "endpoint": endpoint,
    }
    if params:
        # Don't log sensitive keys
        safe_params = {k: v if k.lower() not in ["key", "appid", "api_key", "token"] else "***" 
                      for k, v in params.items()}
        data["params"] = safe_params
    if body:
        data["body"] = body
    
    logger.log_api_call(
        f"api_request_{endpoint.replace('/', '_')}",
        data,
        endpoint=endpoint,
        method=method,
        api_name=api_name,
    )


def log_api_response(
    api_name: str,
    status_code: int,
    response_data: Any,
    endpoint: str = "unknown",
) -> None:
    """Log an API response."""
    is_success = 200 <= status_code < 300
    
    logger.log_api_call(
        f"api_response_{endpoint.replace('/', '_')}",
        {"response": response_data},
        endpoint=endpoint,
        status_code=status_code,
        method="RESPONSE",
        api_name=api_name,
    )


def log_api_error(
    api_name: str,
    error: Exception,
    context: Optional[dict] = None,
    endpoint: str = "unknown",
) -> None:
    """Log an API error."""
    logger.log_error(
        f"api_error_{api_name.lower()}",
        error,
        context={
            "api": api_name,
            "endpoint": endpoint,
            **(context or {})
        },
    )


def log_mock_api_response(
    api_name: str,
    mock_data: Any,
    reason: str = "API key not configured",
    endpoint: str = "unknown",
) -> None:
    """Log a mock/hardcoded API response (when real API unavailable)."""
    logger.log_hardcoded(
        f"api_mock_response_{api_name.lower()}",
        mock_data,
        reason=reason,
        endpoint=endpoint,
    )
