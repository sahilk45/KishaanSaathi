"""
chatbot/db.py — Async DB connection pool for the chatbot module
===============================================================
Reuses the same Neon PostgreSQL connection via asyncpg.
Uses a singleton pool (shared across all requests) with JSON codec support.
"""

import os
import json
import logging
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codecs for every new pooled connection."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def get_pool() -> asyncpg.Pool:
    """Returns the singleton asyncpg pool, creating it if needed."""
    global _pool
    if _pool is None:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=5,
            command_timeout=15,
            init=_init_connection,
        )
        logger.info("✅ chatbot asyncpg pool created")
    return _pool


@asynccontextmanager
async def get_db_connection():
    """
    Async context manager that yields a single DB connection from the pool.

    Usage:
        async with get_db_connection() as conn:
            row = await conn.fetchrow("SELECT ...")
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def close_pool() -> None:
    """Closes the pool. Call this on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("chatbot asyncpg pool closed")
