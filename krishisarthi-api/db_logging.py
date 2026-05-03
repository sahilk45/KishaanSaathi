"""
db_logging.py — Database operation logging helpers
===================================================
Provides utility functions for logging database queries and operations.
Makes it easy to track:
  - SELECT queries and their results
  - INSERT/UPDATE/DELETE operations
  - Query performance
  - Rows affected

Usage:
    from db_logging import log_query, log_insert, log_update
    
    # Log SELECT query
    result = await conn.fetch("SELECT * FROM farmers WHERE id = $1", farmer_id)
    log_query("fetch_farmer", result, table="farmers")
    
    # Log INSERT
    result = await conn.execute("INSERT INTO farmers ...")
    log_insert("create_farmer", result, table="farmers")
"""

from logger_config import get_logger
from typing import Any, Optional

logger = get_logger(__name__)


def log_query(
    event_name: str,
    result: Any,
    table: str = "unknown",
    rows_count: Optional[int] = None,
    query_condition: str = "",
) -> None:
    """Log a SELECT query result."""
    if rows_count is None:
        rows_count = len(result) if isinstance(result, (list, tuple)) else (1 if result else 0)
    
    logger.log_db_operation(
        event_name,
        {"result": result, "query_condition": query_condition},
        operation="SELECT",
        table=table,
        rows_affected=rows_count,
    )


def log_insert(
    event_name: str,
    result: Any,
    table: str = "unknown",
    rows_count: int = 1,
) -> None:
    """Log an INSERT operation."""
    logger.log_db_operation(
        event_name,
        {"result": result},
        operation="INSERT",
        table=table,
        rows_affected=rows_count,
    )


def log_update(
    event_name: str,
    result: Any,
    table: str = "unknown",
    rows_affected: int = 0,
    condition: str = "",
) -> None:
    """Log an UPDATE operation."""
    logger.log_db_operation(
        event_name,
        {"result": result, "condition": condition},
        operation="UPDATE",
        table=table,
        rows_affected=rows_affected,
    )


def log_delete(
    event_name: str,
    result: Any,
    table: str = "unknown",
    rows_affected: int = 0,
) -> None:
    """Log a DELETE operation."""
    logger.log_db_operation(
        event_name,
        {"result": result},
        operation="DELETE",
        table=table,
        rows_affected=rows_affected,
    )


def log_db_error(
    event_name: str,
    error: Exception,
    operation: str = "QUERY",
    table: str = "unknown",
    context: Optional[dict] = None,
) -> None:
    """Log a database error."""
    logger.log_error(
        event_name,
        error,
        context={
            "operation": operation,
            "table": table,
            **(context or {})
        },
    )
