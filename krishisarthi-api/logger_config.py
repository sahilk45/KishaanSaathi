"""
logger_config.py — Structured Logging Configuration for KrishanSaathi API
==========================================================================
Provides:
  1. JSON-formatted structured logging
  2. Distinction between real data (API/DB), mock/hardcoded, and predictions
  3. Context tracking for debugging
  4. Easy integration across all modules

Usage:
  from logger_config import get_logger
  logger = get_logger(__name__)
  
  # Log real data from API/DB
  logger.log_real_data("weather_fetched", {"temp": 32, "humidity": 60}, source="AgroMonitoring")
  
  # Log mock/hardcoded values
  logger.log_hardcoded("default_values_used", {"temp": 32, "humidity": 65})
  
  # Log model predictions
  logger.log_prediction("yield_predicted", {"yield_kg_ha": 1800, "model": "XGBoost"})
  
  # Log DB operations
  logger.log_db_operation("farmer_retrieved", {"farmer_id": "F123", "rows": 1}, operation="SELECT")
  
  # Log API calls
  logger.log_api_call("groq_inference", {"endpoint": "/chat/completions", "status": 200})
"""

import json
import logging
import sys
from typing import Any, Optional
from datetime import datetime


class StructuredLogger:
    """Wrapper around Python logger with structured logging methods."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger_name = name

    def _format_log_entry(
        self,
        event_type: str,
        data: dict,
        source: str = "INTERNAL",
        severity: str = "INFO",
        **extra_fields
    ) -> dict:
        """
        Formats a structured log entry with timestamp, event type, data, and source.
        
        Args:
            event_type: What happened (e.g., "db_query", "api_call", "prediction")
            data: The actual data/result
            source: Where the data came from ("DB", "AgroMonitoring", "Groq", "HARDCODED", "MOCK", etc.)
            severity: Log level ("INFO", "WARNING", "ERROR")
            **extra_fields: Additional context
        
        Returns:
            Structured log dict
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "logger": self.logger_name,
            "event": event_type,
            "source": source,
            "severity": severity,
            "data": data,
        }
        entry.update(extra_fields)
        return entry

    def _log(self, level: int, log_dict: dict):
        """Logs the structured dict as JSON."""
        log_line = json.dumps(log_dict, default=str)
        self.logger.log(level, log_line)

    def info(self, msg: str, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    # ───────────────────────────────────────────────────────────────────────────
    # High-level logging methods for common operations
    # ───────────────────────────────────────────────────────────────────────────

    def log_real_data(
        self,
        event_type: str,
        data: Any,
        source: str = "EXTERNAL_API",
        **extra_fields
    ):
        """
        Logs data from real sources (database, external API, satellite, etc.).
        Indicates this is ACTUAL data, not mock/hardcoded.
        """
        entry = self._format_log_entry(
            event_type=event_type,
            data={"actual_data": data},
            source=f"[REAL] {source}",
            severity="INFO",
            data_type="REAL",
            **extra_fields
        )
        self._log(logging.INFO, entry)

    def log_hardcoded(
        self,
        event_type: str,
        data: Any,
        reason: str = "No API key / default values",
        **extra_fields
    ):
        """
        Logs hardcoded or default values.
        Indicates this is NOT real data but fallback values for testing/demo.
        """
        entry = self._format_log_entry(
            event_type=event_type,
            data={"hardcoded_value": data},
            source="[HARDCODED]",
            severity="WARNING",
            data_type="HARDCODED",
            reason=reason,
            **extra_fields
        )
        self._log(logging.WARNING, entry)

    def log_mock(
        self,
        event_type: str,
        data: Any,
        reason: str = "Mock data for testing",
        **extra_fields
    ):
        """
        Logs mock data used for testing when real data unavailable.
        Similar to hardcoded but emphasizes it's synthetic.
        """
        entry = self._format_log_entry(
            event_type=event_type,
            data={"mock_data": data},
            source="[MOCK]",
            severity="WARNING",
            data_type="MOCK",
            reason=reason,
            **extra_fields
        )
        self._log(logging.WARNING, entry)

    def log_prediction(
        self,
        event_type: str,
        data: Any,
        model_name: str = "Unknown",
        confidence: Optional[float] = None,
        **extra_fields
    ):
        """
        Logs model predictions (XGBoost, ML model outputs, etc.).
        Indicates this is a PREDICTION, not actual observed data.
        """
        prediction_data = {
            "prediction": data,
            "model": model_name,
        }
        if confidence is not None:
            prediction_data["confidence"] = confidence

        entry = self._format_log_entry(
            event_type=event_type,
            data=prediction_data,
            source=f"[PREDICTION] {model_name}",
            severity="INFO",
            data_type="PREDICTION",
            **extra_fields
        )
        self._log(logging.INFO, entry)

    def log_db_operation(
        self,
        event_type: str,
        data: Any,
        operation: str = "QUERY",
        table: Optional[str] = None,
        rows_affected: Optional[int] = None,
        **extra_fields
    ):
        """
        Logs database operations (SELECT, INSERT, UPDATE, DELETE).
        Tracks what queries are executed and what data was retrieved/modified.
        """
        db_data = {
            "operation": operation,
            "result": data,
        }
        if table:
            db_data["table"] = table
        if rows_affected is not None:
            db_data["rows_affected"] = rows_affected

        entry = self._format_log_entry(
            event_type=event_type,
            data=db_data,
            source=f"[DATABASE] {operation}",
            severity="INFO",
            data_type="DATABASE",
            **extra_fields
        )
        self._log(logging.INFO, entry)

    def log_api_call(
        self,
        event_type: str,
        data: Any,
        endpoint: str = "",
        status_code: Optional[int] = None,
        method: str = "GET",
        api_name: str = "Unknown",
        **extra_fields
    ):
        """
        Logs API calls to external services (Groq, AgroMonitoring, etc.).
        Tracks requests, responses, and status codes.
        """
        api_data = {
            "api": api_name,
            "method": method,
            "endpoint": endpoint,
            "response": data,
        }
        if status_code:
            api_data["status_code"] = status_code

        entry = self._format_log_entry(
            event_type=event_type,
            data=api_data,
            source=f"[API] {api_name}",
            severity="INFO" if status_code in (200, 201, 202) else "WARNING",
            data_type="API_CALL",
            **extra_fields
        )
        self._log(logging.INFO, entry)

    def log_tool_execution(
        self,
        event_type: str,
        data: Any,
        tool_name: str = "Unknown",
        duration_ms: Optional[float] = None,
        **extra_fields
    ):
        """
        Logs tool executions (get_weather, get_market_price, get_crop_advice, etc.).
        """
        tool_data = {
            "tool": tool_name,
            "result": data,
        }
        if duration_ms:
            tool_data["duration_ms"] = duration_ms

        entry = self._format_log_entry(
            event_type=event_type,
            data=tool_data,
            source=f"[TOOL] {tool_name}",
            severity="INFO",
            data_type="TOOL",
            **extra_fields
        )
        self._log(logging.INFO, entry)

    def log_error(
        self,
        event_type: str,
        error: Exception,
        context: Optional[dict] = None,
        **extra_fields
    ):
        """
        Logs errors with context.
        """
        error_data = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
        }

        entry = self._format_log_entry(
            event_type=event_type,
            data=error_data,
            source="[ERROR]",
            severity="ERROR",
            data_type="ERROR",
            **extra_fields
        )
        self._log(logging.ERROR, entry)

    def log_computation(
        self,
        event_type: str,
        data: Any,
        computation_type: str = "calculation",
        **extra_fields
    ):
        """
        Logs explicit value assignments and computations.
        """
        entry = self._format_log_entry(
            event_type=event_type,
            data={"computed_value": data},
            source=f"[COMPUTATION] {computation_type}",
            severity="INFO",
            data_type="COMPUTATION",
            **extra_fields
        )
        self._log(logging.INFO, entry)


def setup_structured_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Configures structured logging for the entire application.
    
    Args:
        log_level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR")
        log_file: Optional file path to log to (in addition to console)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Console handler — force UTF-8 so Windows CP1252 doesn't crash on
    # unicode characters (arrows, emoji) used in log format strings
    import io
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    console_handler = logging.StreamHandler(utf8_stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Simple format that plays nice with JSON output
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> StructuredLogger:
    """
    Returns a StructuredLogger instance for the given module name.
    
    Usage:
        logger = get_logger(__name__)
        logger.log_real_data("event", {"key": "value"}, source="API")
    """
    return StructuredLogger(name)
