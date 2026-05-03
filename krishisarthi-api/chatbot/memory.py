"""
chatbot/memory.py — PostgreSQL-backed conversation memory for KisanSaathi
=========================================================================

Responsibilities:
  1. ensure_thread_exists()    — upsert a row in chat_threads for a given thread_id.
  2. load_messages()           — fetch chat_messages for a thread → list[BaseMessage].
  3. save_turn()               — persist one user + one AI turn to chat_messages.
  4. apply_memory_pressure()   — if message count > MEMORY_THRESHOLD (20):
                                    • summarize the oldest (count - KEEP_RECENT) messages
                                      with the LLM, appending any existing summary.
                                    • delete those old messages from DB.
                                    • update chat_threads.summary.
                                 Returns (messages_to_use, existing_summary).

Schema used (from database.py):
  chat_threads  (thread_id PK, farmer_id, summary, created_at, updated_at)
  chat_messages (msg_id, thread_id FK, role, content, tool_name, created_at)

Role values: 'human' | 'ai' | 'tool' | 'summary'
"""

import logging
from typing import Optional

import asyncpg
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage,
)
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

# ── Memory tuning ──────────────────────────────────────────────────────────────
MEMORY_THRESHOLD = 20   # trigger summarisation after this many stored messages
KEEP_RECENT      = 5    # keep this many recent messages after summarisation


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_message(row: asyncpg.Record) -> Optional[BaseMessage]:
    """Convert a chat_messages DB row to a LangChain BaseMessage."""
    role    = row["role"]
    content = row["content"]
    if role == "human":
        return HumanMessage(content=content)
    if role == "ai":
        return AIMessage(content=content)
    if role == "tool":
        # tool_name is stored but ToolMessage needs a tool_call_id; use a placeholder
        return ToolMessage(content=content, tool_call_id="db_restored")
    if role == "summary":
        return SystemMessage(content=f"[Previous conversation summary]\n{content}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def ensure_thread_exists(
    thread_id: str,
    farmer_id: str,
    pool: asyncpg.Pool,
) -> None:
    """
    Upserts a row in chat_threads so the thread is tracked.
    Safe to call on every request — does nothing if thread already exists.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_threads (thread_id, farmer_id)
            VALUES ($1, $2::uuid)
            ON CONFLICT (thread_id) DO NOTHING
            """,
            thread_id, farmer_id,
        )


async def load_messages(
    thread_id: str,
    pool: asyncpg.Pool,
) -> tuple[list[BaseMessage], Optional[str]]:
    """
    Loads all chat_messages for the thread, ordered chronologically.

    Returns:
        (messages, existing_summary)
        messages          — list of BaseMessage ready to pass to LangGraph state
        existing_summary  — the current summary text stored in chat_threads (or None)
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, tool_name, created_at
            FROM   chat_messages
            WHERE  thread_id = $1
            ORDER  BY created_at ASC
            """,
            thread_id,
        )
        thread_row = await conn.fetchrow(
            "SELECT summary FROM chat_threads WHERE thread_id = $1", thread_id
        )

    summary = thread_row["summary"] if thread_row and thread_row["summary"] else None
    messages: list[BaseMessage] = []
    for row in rows:
        msg = _row_to_message(row)
        if msg is not None:
            messages.append(msg)

    return messages, summary


async def save_turn(
    thread_id: str,
    user_message: str,
    ai_reply: str,
    tool_messages: list[dict],   # [{"name": str, "content": str}, ...]
    pool: asyncpg.Pool,
) -> None:
    """
    Persists one conversation turn (human → [tools] → ai) to chat_messages.

    Args:
        thread_id:     The chat session identifier.
        user_message:  The raw text of the farmer's message.
        ai_reply:      The final AI text response shown to the farmer.
        tool_messages: List of dicts with keys 'name' and 'content' for each
                       tool call that happened during this turn.
        pool:          asyncpg connection pool.
    """
    async with pool.acquire() as conn:
        # Human message
        await conn.execute(
            "INSERT INTO chat_messages (thread_id, role, content) VALUES ($1, $2, $3)",
            thread_id, "human", user_message,
        )
        # Tool messages (if any)
        for tm in tool_messages:
            await conn.execute(
                "INSERT INTO chat_messages (thread_id, role, content, tool_name)"
                " VALUES ($1, $2, $3, $4)",
                thread_id, "tool", tm["content"], tm.get("name", "unknown"),
            )
        # AI reply
        await conn.execute(
            "INSERT INTO chat_messages (thread_id, role, content) VALUES ($1, $2, $3)",
            thread_id, "ai", ai_reply,
        )
        # Update thread timestamp
        await conn.execute(
            "UPDATE chat_threads SET updated_at = NOW() WHERE thread_id = $1", thread_id
        )


async def apply_memory_pressure(
    thread_id: str,
    pool: asyncpg.Pool,
    llm: ChatGroq,
) -> tuple[list[BaseMessage], Optional[str]]:
    """
    If the number of stored messages exceeds MEMORY_THRESHOLD (20):
      1. Fetches all messages and the existing summary.
      2. Calls the LLM to summarise the oldest (count - KEEP_RECENT) messages,
         incorporating the prior summary.
      3. Deletes those old messages from chat_messages.
      4. Updates chat_threads.summary with the new summary text.
      5. Returns (recent_messages_only, new_summary).

    If message count is within threshold, returns (all_messages, existing_summary)
    unchanged — no DB writes.

    Args:
        thread_id: Chat session identifier.
        pool:      asyncpg connection pool.
        llm:       Groq LLM instance (used only when summarisation is triggered).

    Returns:
        (messages, summary) tuple ready to be injected into the LangGraph state.
    """
    messages, existing_summary = await load_messages(thread_id, pool)

    if len(messages) <= MEMORY_THRESHOLD:
        return messages, existing_summary

    logger.info(
        "Memory pressure: thread='%s' has %d messages — summarising oldest %d",
        thread_id, len(messages), len(messages) - KEEP_RECENT,
    )

    to_summarise = messages[:len(messages) - KEEP_RECENT]
    recent       = messages[len(messages) - KEEP_RECENT:]

    # Build summarisation prompt
    convo_text = "\n".join(
        f"[{type(m).__name__}]: {m.content}" for m in to_summarise
    )
    if existing_summary:
        prompt_text = (
            f"Previous summary:\n{existing_summary}\n\n"
            f"New conversation to add to summary:\n{convo_text}\n\n"
            "Please write an updated, concise summary of the entire conversation "
            "so far (max 300 words). Focus on what the farmer asked, what data "
            "was returned, and any decisions made."
        )
    else:
        prompt_text = (
            f"Conversation:\n{convo_text}\n\n"
            "Please write a concise summary of this conversation (max 300 words). "
            "Focus on what the farmer asked, what data was returned, and any decisions."
        )

    summary_resp = await llm.ainvoke([HumanMessage(content=prompt_text)])
    new_summary  = summary_resp.content

    # Get the oldest message IDs to delete
    async with pool.acquire() as conn:
        old_msg_ids = await conn.fetch(
            """
            SELECT msg_id FROM chat_messages
            WHERE  thread_id = $1
            ORDER  BY created_at ASC
            LIMIT  $2
            """,
            thread_id,
            len(messages) - KEEP_RECENT,
        )
        ids = [str(r["msg_id"]) for r in old_msg_ids]
        if ids:
            await conn.execute(
                f"DELETE FROM chat_messages WHERE msg_id = ANY($1::uuid[])", ids
            )
        # Update the rolling summary in chat_threads
        await conn.execute(
            "UPDATE chat_threads SET summary = $1, updated_at = NOW() WHERE thread_id = $2",
            new_summary, thread_id,
        )

    logger.info("Memory pressure resolved: stored new summary (%d chars)", len(new_summary))
    return recent, new_summary
