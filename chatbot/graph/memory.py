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

# ── Summary prompt ──────────────────────────────────────────────────────────────
SUMMARY_PROMPT = """
You are summarising a conversation between KisanSaathi (an AI agricultural advisor) and an Indian farmer.

Write a concise summary (100-250 words) of ONLY what was actually discussed.
Do NOT invent or assume any field that was not mentioned. Skip sections entirely if that topic never came up.
Preserve exact numbers where mentioned (e.g. score 67, not "moderate").
Do NOT write "This is a summary" or any meta-commentary.

Include the following ONLY IF they appeared in the conversation:
- Farmer's location (state, district, village) and farm size
- Crop being grown and current season
- Any farm health data mentioned: NDVI, health score, climate score, yield
- Weather conditions, forecasts, or alerts discussed
- Market/mandi prices discussed and any selling decisions
- Specific advice given (fertilizer, irrigation, crop changes) with numbers
- Loan eligibility or financial topics raised
- Questions the farmer asked that were not fully answered
- Decisions the farmer made

Conversation:
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
    data_status = farmer_context.get("data_status", "complete")

    # ── Data availability banner ───────────────────────────────────────────────
    if data_status == "no_farm":
        data_banner = (
            "\n\nDATA AVAILABILITY ALERT:\n"
            "  [WARNING] This farmer has NOT registered a farm field yet.\n"
            "  [WARNING] Scores, NDVI, yield, and predictions are NOT available.\n"
            "  REQUIRED STEPS FOR USER:\n"
            "    1. Register a farm via POST /farm/register (with GPS coordinates)\n"
            "    2. Run a prediction via POST /predict\n"
            "  INSTRUCTION: DO NOT call get_farmer_data, get_crop_advice, get_market_price, get_weather.\n"
            "  Instead, EXPLAIN to the farmer what they need to do first.\n"
        )
    elif data_status == "no_prediction":
        data_banner = (
            "\n\nDATA AVAILABILITY ALERT:\n"
            "  [WARNING] Farm field is registered but NO prediction has been run yet.\n"
            "  [WARNING] Health score, NDVI, and yield data are NOT available.\n"
            "  REQUIRED STEP FOR USER: Call POST /predict with their field_id and crop_type.\n"
            "  INSTRUCTION: DO NOT call get_farmer_data or get_crop_advice (they will fail and loop).\n"
            "  You MAY call get_weather. EXPLAIN to the farmer they need to run a prediction first.\n"
        )
    else:
        data_banner = ""

    def _fmt(val, fmt=".1f", fallback="N/A"):
        """Format a numeric value safely, return fallback if None."""
        if val is None:
            return fallback
        try:
            return format(float(val), fmt)
        except (TypeError, ValueError):
            return fallback

    ndvi         = farmer_context.get("ndvi")
    health_score = farmer_context.get("health_score")
    farmer_id    = farmer_context.get('farmer_id', '')

    ndvi_label = (
        "(STRESSED)" if ndvi is not None and ndvi < 0.35
        else "(MODERATE)" if ndvi is not None and ndvi < 0.6
        else "(HEALTHY)" if ndvi is not None
        else "(Not available)"
    )

    if health_score is None:
        risk_label = "Not available — run /predict first"
    elif health_score < 40:
        risk_label = "HIGH RISK — Loan likely rejected"
    elif health_score < 60:
        risk_label = "MEDIUM RISK — Small loan eligible"
    else:
        risk_label = "LOW RISK — Standard/full loan eligible"

    system_content = (
        f"You are KisanSaathi, an AI agricultural advisor for Indian farmers.{data_banner}\n"
        f"FARMER PROFILE:\n"
        f"- Name: {farmer_context.get('farmer_name', 'Farmer')}\n"
        f"- Farmer ID (UUID): {farmer_id}  <- USE THIS EXACT VALUE when calling any tool\n"
        f"- Location: {farmer_context.get('farmer_district', '')}, {farmer_context.get('farmer_state', '')}\n"
        f"- Current Crop: {farmer_context.get('current_crop', 'Unknown')}\n"
        f"- Farm Size: {_fmt(farmer_context.get('area_ha'), '.1f')} hectares\n"
        f"- NDVI (Satellite): {_fmt(ndvi, '.3f')} {ndvi_label}\n"
        f"- Health Score: {_fmt(health_score, '.1f')}/100 -- {risk_label}\n"
        f"- Predicted Yield: {_fmt(farmer_context.get('predicted_yield'), '.0f')} kg/ha\n"
        f"- NPK Applied: {_fmt(farmer_context.get('npk_intensity_kgha'), '.0f')} kg/ha\n"
        f"- Irrigation Ratio: {_fmt(farmer_context.get('irr_ratio'), '.2f')}\n"
        f"- Water Deficit Index (WDI): {_fmt(farmer_context.get('wdi'), '.2f')}\n"
        f"- Soil Health Score: {_fmt(farmer_context.get('district_soil_score'), '.1f')}\n"
        f"- GPS: {_fmt(farmer_context.get('centroid_lat'), '.4f')}, {_fmt(farmer_context.get('centroid_lng'), '.4f')}\n"
        f"- Kharif Temp: {_fmt(farmer_context.get('kharif_avg_maxtemp'), '.1f')}C | Rain: {_fmt(farmer_context.get('kharif_total_rain'), '.0f')} mm\n"
        f"- Rabi Temp: {_fmt(farmer_context.get('rabi_avg_maxtemp'), '.1f')}C\n"
        f"\n"
        f"TOOL USAGE RULES:\n"
        f"- farmer_id for ALL tools MUST be exactly: {farmer_id}\n"
        f"- NEVER invent, guess, or use a placeholder farmer_id.\n"
        f"- Current data_status: {data_status}. Only call tools when data_status is 'complete'.\n"
        f"- Answer from FARMER PROFILE above for health score, NDVI, yield, NPK — do NOT call tools for these.\n"
        f"- Call get_farmer_data   -> farm status, NDVI, health score (only if farmer asks to REFRESH or data shows Unknown).\n"
        f"- Call get_weather       -> rain, temperature, irrigation timing questions.\n"
        f"- Call get_crop_advice   -> score improvement, loan eligibility (needs prediction data).\n"
        f"- Call get_market_price  -> mandi prices (see get_market_price rules below).\n"
        f"\n"
        f"get_market_price RULES:\n"
        f"- If farmer asks about their own district price: call get_market_price(farmer_id='{farmer_id}').\n"
        f"- If farmer asks for a DIFFERENT district or state price: call get_market_price with the district/state they named.\n"
        f"- If district/state is unknown and farmer did not mention one: ASK the farmer first. Do NOT call the tool.\n"
        f"- If API returns error or no data: tell farmer plainly — 'Abhi mandi prices fetch nahi ho pa rahi, thodi der baad try karein.' Do NOT retry.\n"
        f"\n"
        f"CRITICAL ANTI-LOOP RULES:\n"
        f"- Each tool may be called AT MOST ONCE per user message.\n"
        f"- If any tool returns error=True, 'not found', 'Database error', or 'API error': STOP. Respond to the user plainly. Do NOT call another tool.\n"
        f"- If a required field is missing (district, crop, etc.): ASK the user. Do NOT loop through tools trying to find it.\n"
        f"- If you have called 2+ tools without giving a final answer: STOP and respond now.\n"
        f"- Tool errors and missing data are FINAL — respond to the user, not the tool.\n"
        f"\n"
        f"RESPONSE RULES:\n"
        f"1. Respond in Hinglish (Hindi + English mix) unless farmer writes in pure English.\n"
        f"2. ALWAYS reference farmer's actual data — NEVER give generic advice.\n"
        f"3. Keep responses concise — max 150 words unless farmer asks for more detail.\n"
        f"4. Always give 2-3 concrete next steps at the end.\n"
        f"5. Use Rs for prices, C for temperature, kg/ha for quantities.\n"
        f"6. NEVER guess score deltas or yields — use get_crop_advice tool for that.\n"
        f"7. On tool error: say what went wrong plainly, then answer from FARMER PROFILE.\n"
        f"8. NEVER call a tool when data_status is 'no_farm' or 'no_prediction' — explain and guide instead."
    )


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
