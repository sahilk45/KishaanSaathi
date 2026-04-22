"""
chatbot/graph/memory.py — Short-term memory with Neon DB persistence
======================================================================

Memory strategy:
  - All messages are stored in Neon DB (chat_messages table).
  - When messages count >= MAX_MESSAGES (50):
      1. Take oldest MESSAGES_TO_SUMMARIZE (45) messages.
      2. Generate a concise agricultural summary with the LLM.
      3. Save summary to chat_threads.summary in DB.
      4. Replace those messages in state with one SystemMessage containing summary.
      5. Keep newest SUMMARY_KEEP_RECENT (5) messages as-is.
  - On session START: load existing summary from DB and inject as SystemMessage.
  - Thread ID lets the farmer resume previous conversations seamlessly.

DB tables used:
  chat_threads  — stores thread metadata + rolling summary text
  chat_messages — stores individual messages (role, content, tool_name)
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from chatbot.db import get_db_connection

logger = logging.getLogger(__name__)

# ── Memory config ──────────────────────────────────────────────────────────────
MAX_MESSAGES          = 50   # trigger summarisation at this count
MESSAGES_TO_SUMMARIZE = 45   # how many oldest messages to compress
SUMMARY_KEEP_RECENT   = 5    # how many recent messages to keep after compression

# ── Summary prompt ─────────────────────────────────────────────────────────────
SUMMARY_PROMPT = """
You are summarizing a conversation between an AI agricultural advisor (KisanSaathi)
and an Indian farmer.

Create a concise summary that preserves ALL of the following details if mentioned:
1. LOCATION: Farmer's state, district, village, farm size
2. CROP: Current crop type, growth stage, season
3. WEATHER: Weather conditions discussed, forecast mentioned, drought/rain alerts
4. FARM HEALTH: NDVI values, health score, climate score mentioned
5. MARKET: Crop prices, mandi names, MSP comparisons discussed
6. YIELD: Predictions, comparisons, improvements suggested
7. ADVICE GIVEN: NPK/irrigation changes recommended, exact scores mentioned
8. PENDING: Questions the farmer asked that are still open
9. DECISIONS: Decisions the farmer made (e.g. chose to change crop, apply more fertilizer)
10. LOAN STATUS: Any loan eligibility discussed

Write in 200-300 words. Be specific with numbers — preserve exact values.
NEVER generalise. If score was 67, write 67, not "moderate".
Do NOT mention that this is a summary.

Conversation to summarize:
{conversation_text}
"""


# ── DB helper functions ────────────────────────────────────────────────────────

async def get_or_create_thread(thread_id: str, farmer_id: str) -> dict:
    """Creates the thread row if it doesn't exist. Returns the thread record."""
    async with get_db_connection() as conn:
        row = await conn.fetchrow(
            "SELECT thread_id, summary FROM chat_threads WHERE thread_id = $1",
            thread_id,
        )
        if not row:
            row = await conn.fetchrow(
                """
                INSERT INTO chat_threads (thread_id, farmer_id)
                VALUES ($1, $2::uuid)
                RETURNING thread_id, summary
                """,
                thread_id, farmer_id,
            )
    return dict(row) if row else {"thread_id": thread_id, "summary": None}


async def fetch_thread_summary(thread_id: str) -> Optional[str]:
    """Returns the existing summary text for a thread, or None."""
    async with get_db_connection() as conn:
        row = await conn.fetchrow(
            "SELECT summary FROM chat_threads WHERE thread_id = $1",
            thread_id,
        )
    return row["summary"] if row else None


async def fetch_thread_messages(thread_id: str) -> list[dict]:
    """Returns all messages for a thread ordered by created_at ASC."""
    async with get_db_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, tool_name
            FROM   chat_messages
            WHERE  thread_id = $1
            ORDER  BY created_at ASC
            """,
            thread_id,
        )
    return [dict(r) for r in rows]


async def count_thread_messages(thread_id: str) -> int:
    """Returns the count of messages stored for a thread."""
    async with get_db_connection() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM chat_messages WHERE thread_id = $1",
            thread_id,
        )
    return int(row["cnt"]) if row else 0


async def save_message(
    thread_id: str,
    role: str,
    content: str,
    tool_name: Optional[str] = None,
) -> None:
    """Inserts one message into chat_messages and bumps updated_at on the thread."""
    async with get_db_connection() as conn:
        await conn.execute(
            """
            INSERT INTO chat_messages (thread_id, role, content, tool_name)
            VALUES ($1, $2, $3, $4)
            """,
            thread_id, role, content, tool_name,
        )
        await conn.execute(
            """
            UPDATE chat_threads
            SET    updated_at = NOW()
            WHERE  thread_id = $1
            """,
            thread_id,
        )


async def save_thread_summary(thread_id: str, summary: str) -> None:
    """Upserts the summary text for a thread."""
    async with get_db_connection() as conn:
        await conn.execute(
            """
            UPDATE chat_threads
            SET    summary    = $2,
                   updated_at = NOW()
            WHERE  thread_id  = $1
            """,
            thread_id, summary,
        )


# ── Summarisation logic ────────────────────────────────────────────────────────

async def should_summarize(thread_id: str) -> bool:
    """Returns True if message count has reached or exceeded MAX_MESSAGES."""
    count = await count_thread_messages(thread_id)
    return count >= MAX_MESSAGES


async def generate_and_save_summary(
    thread_id: str,
    messages: list,
    llm,
) -> str:
    """
    Takes the oldest MESSAGES_TO_SUMMARIZE messages, generates a summary with
    the LLM, saves it to DB, and returns the summary text.
    """
    messages_to_compress = messages[:MESSAGES_TO_SUMMARIZE]

    conversation_text = "\n".join([
        f"{msg.type.upper()}: {msg.content}"
        for msg in messages_to_compress
        if hasattr(msg, "content") and msg.content
    ])

    summary_response = await llm.ainvoke(
        SUMMARY_PROMPT.format(conversation_text=conversation_text)
    )
    summary = summary_response.content

    await save_thread_summary(thread_id, summary)
    logger.info("Thread %s: summary generated and saved (%d chars)", thread_id, len(summary))
    return summary


async def build_initial_messages(
    thread_id: str,
    farmer_context: dict,
    existing_summary: Optional[str] = None,
) -> list:
    """
    Called at the start of each conversation turn.

    Returns:
      [SystemMessage(farmer context), SystemMessage(summary if exists),
       ...recent messages from DB]
    """
    messages = []

    # ── System prompt with full farmer context ─────────────────────────────────
    ndvi = farmer_context.get("ndvi", 0.0)
    ndvi_label = (
        "(STRESSED — below 0.35)" if ndvi < 0.35
        else "(MODERATE)" if ndvi < 0.6
        else "(HEALTHY)"
    )

    health_score = farmer_context.get("health_score", 0.0)
    if health_score < 40:
        risk_label = "HIGH RISK — Loan likely rejected"
    elif health_score < 60:
        risk_label = "MEDIUM RISK — Small loan eligible"
    else:
        risk_label = "LOW RISK — Standard/full loan eligible"

    farmer_id   = farmer_context.get('farmer_id', '')

    system_content = f"""You are KisanSaathi (किसान साथी), an AI agricultural advisor for Indian farmers.

FARMER PROFILE:
- Name: {farmer_context.get('farmer_name', 'Farmer')}
- Farmer ID (UUID): {farmer_id}   ← USE THIS EXACT VALUE when calling any tool
- Location: {farmer_context.get('farmer_district', '')}, {farmer_context.get('farmer_state', '')}
- Current Crop: {farmer_context.get('current_crop', 'Unknown')}
- Farm Size: {farmer_context.get('area_ha', 1.0):.1f} hectares
- NDVI (Satellite): {ndvi:.3f} {ndvi_label}
- Health Score: {health_score:.1f}/100 — {risk_label}
- Predicted Yield: {farmer_context.get('predicted_yield', 0):.0f} kg/ha
- NPK Applied: {farmer_context.get('npk_intensity_kgha', 0):.0f} kg/ha
- Irrigation Ratio: {farmer_context.get('irr_ratio', 0):.2f}
- Water Deficit Index (WDI): {farmer_context.get('wdi', 0):.2f}
- Soil Health Score: {farmer_context.get('district_soil_score', 0):.1f}
- GPS: {farmer_context.get('centroid_lat', 0)}, {farmer_context.get('centroid_lng', 0)}
- Kharif Temp: {farmer_context.get('kharif_avg_maxtemp', 0):.1f}°C | Rain: {farmer_context.get('kharif_total_rain', 0):.0f} mm
- Rabi Temp: {farmer_context.get('rabi_avg_maxtemp', 0):.1f}°C

TOOL USAGE RULES — READ CAREFULLY:
- farmer_id argument for ALL tools MUST be exactly: {farmer_id}
- NEVER invent, guess, or use a placeholder farmer_id — always use the UUID above.
- Call get_farmer_data   → when farmer asks about NDVI, health score, farm status.
- Call get_weather       → when farmer asks about rain, temperature, irrigation timing.
- Call get_market_price  → when farmer asks about mandi prices, market rates.
- Call get_crop_advice   → when farmer asks how to improve yield/score/loan eligibility.
- Do NOT call tools if the question is already answered by FARMER PROFILE above.

RESPONSE RULES:
1. Respond in Hinglish (Hindi + English mix) unless farmer writes in pure English.
2. ALWAYS reference farmer's actual data above — NEVER give generic advice.
3. Keep responses concise — max 150 words unless farmer asks for more detail.
4. Always give 2-3 concrete next steps at the end of your answer.
5. Use ₹ for prices, °C for temperature, kg/ha for quantities.
6. NEVER guess score deltas or yields — use get_crop_advice tool for that.
7. If a tool returns an error, apologise briefly and answer from FARMER PROFILE data."""

    messages.append(SystemMessage(content=system_content))

    # ── Inject existing summary if present ─────────────────────────────────────
    if existing_summary:
        messages.append(SystemMessage(
            content=f"PREVIOUS CONVERSATION SUMMARY:\n{existing_summary}"
        ))

    # ── Load recent messages from DB ──────────────────────────────────────────
    db_messages = await fetch_thread_messages(thread_id)
    # Fewer recent messages if summary exists (we already have context)
    keep_count = SUMMARY_KEEP_RECENT if existing_summary else 20
    recent_msgs = db_messages[-keep_count:] if db_messages else []

    for msg in recent_msgs:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content:
            continue
        if role == "human":
            messages.append(HumanMessage(content=content))
        elif role == "ai":
            messages.append(AIMessage(content=content))

    return messages
