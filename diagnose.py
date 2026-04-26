"""
diagnose.py — Full pipeline diagnostic for KisanSaathi chatbot
Run with:  python diagnose.py <farmer_id>
Or with no args to auto-detect the first farmer in DB.
"""
import asyncio
import sys
import os
from pathlib import Path

# Load .env from the same directory as this script
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# Fix GROQ key alias
if os.getenv("GROK_API_KEY") and not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = os.environ["GROK_API_KEY"]

import asyncpg
import uuid as _uuid

DATABASE_URL = os.getenv("DATABASE_URL", "")
FARMER_ID_ARG = sys.argv[1] if len(sys.argv) > 1 else None

SEP = "=" * 60

async def run():
    print(SEP)
    print("DATABASE_URL set:", bool(DATABASE_URL))
    if not DATABASE_URL:
        print("❌ DATABASE_URL is empty — check .env")
        return

    # ── 1. Connect ──────────────────────────────────────────────────────────
    print(SEP)
    print("TEST 1: DB Connection")
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=10)
        print("✅ Connected to Neon DB")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("   → Run on mobile hotspot. Port 5432 may be blocked on your network.")
        return

    # ── 2. Tables ───────────────────────────────────────────────────────────
    print(SEP)
    print("TEST 2: Required Tables")
    tables = ["farmers", "farm_fields", "field_predictions",
              "district_climate_history", "chat_threads", "chat_messages"]
    for t in tables:
        count = await conn.fetchval(f"SELECT COUNT(*) FROM {t}")
        print(f"  {'✅' if count is not None else '❌'} {t}: {count} rows")

    # ── 3. Farmer ───────────────────────────────────────────────────────────
    print(SEP)
    print("TEST 3: Farmers in DB")
    farmers = await conn.fetch("SELECT id, name, state_name, dist_name, phone FROM farmers LIMIT 5")
    if not farmers:
        print("❌ No farmers registered. Run setup_test_farmer.py first.")
        await conn.close()
        return
    for f in farmers:
        print(f"  farmer_id={f['id']}  name={f['name']}  state={f['state_name']}  dist={f['dist_name']}")

    # Pick the farmer to test
    if FARMER_ID_ARG:
        try:
            test_id = _uuid.UUID(FARMER_ID_ARG)
        except ValueError:
            print(f"❌ Invalid farmer_id arg: {FARMER_ID_ARG}")
            await conn.close()
            return
    else:
        test_id = farmers[0]["id"]

    print(f"\n→ Testing with farmer_id = {test_id}")

    # ── 4. Farm Fields ──────────────────────────────────────────────────────
    print(SEP)
    print("TEST 4: Farm Fields for this farmer")
    fields = await conn.fetch(
        "SELECT id, field_name, city_name, state_name, area_hectares FROM farm_fields WHERE farmer_id = $1",
        test_id,
    )
    if not fields:
        print("❌ No farm fields registered for this farmer.")
        print("   → Call POST /farm/register or run setup_test_farmer.py")
        await conn.close()
        return
    for ff in fields:
        print(f"  field_id={ff['id']}  name={ff['field_name']}  city={ff['city_name']}  area={ff['area_hectares']} ha")

    field_id = fields[0]["id"]

    # ── 5. Predictions ──────────────────────────────────────────────────────
    print(SEP)
    print("TEST 5: Predictions for latest field")
    preds = await conn.fetch(
        """SELECT crop_type, year, final_health_score, predicted_yield, ndvi_value
           FROM field_predictions WHERE field_id = $1
           ORDER BY year DESC, calculated_at DESC LIMIT 3""",
        str(field_id),
    )
    if not preds:
        print("❌ No predictions exist for this field.")
        print("   → Call POST /predict first. Without this, chatbot has no health score/yield data.")
        print("   → The LLM will see 'Unknown' everywhere and try to call get_farmer_data tool.")
    else:
        for p in preds:
            print(f"  crop={p['crop_type']}  year={p['year']}  health={p['final_health_score']}  yield={p['predicted_yield']}  ndvi={p['ndvi_value']}")

    # ── 6. Climate Data ─────────────────────────────────────────────────────
    print(SEP)
    print("TEST 6: Climate history for farmer's district")
    farmer_row = await conn.fetchrow("SELECT dist_name FROM farmers WHERE id = $1", test_id)
    dist = (farmer_row["dist_name"] or "").lower().strip()
    climate = await conn.fetchrow(
        "SELECT COUNT(*) AS cnt FROM district_climate_history WHERE LOWER(dist_name) = $1",
        dist,
    )
    if climate and climate["cnt"] > 0:
        print(f"  ✅ {climate['cnt']} climate rows found for district='{dist}'")
    else:
        print(f"  ❌ No climate rows for district='{dist}'")
        print(f"   → Check spelling. Run: SELECT DISTINCT dist_name FROM district_climate_history LIMIT 20")
        all_dists = await conn.fetch("SELECT DISTINCT dist_name FROM district_climate_history LIMIT 10")
        print(f"   Sample districts in DB: {[r['dist_name'] for r in all_dists]}")

    # ── 7. Chat Thread ──────────────────────────────────────────────────────
    print(SEP)
    print("TEST 7: Chat threads for this farmer")
    threads = await conn.fetch(
        "SELECT id, thread_id, summary FROM chat_threads WHERE farmer_id = $1 LIMIT 3",
        test_id,
    )
    if threads:
        for t in threads:
            print(f"  thread_id={t['thread_id']}  summary={'yes' if t['summary'] else 'none'}")
    else:
        print("  (no threads yet — will be created on first chat)")

    # ── 8. Chatbot profile fetch simulation ────────────────────────────────
    print(SEP)
    print("TEST 8: Simulating _fetch_farmer_profile() call")
    farmer2 = await conn.fetchrow("SELECT name, state_name, dist_name FROM farmers WHERE id = $1", test_id)
    farm2   = await conn.fetchrow(
        "SELECT id, city_name, state_name, area_hectares, center_lat, center_lon FROM farm_fields WHERE farmer_id = $1 ORDER BY created_at DESC LIMIT 1",
        test_id,
    )
    if not farm2:
        print("  data_status = 'no_farm' ← LLM sees all Unknown → calls get_farmer_data → LOOP")
    else:
        season2 = await conn.fetchrow(
            "SELECT crop_type, final_health_score, predicted_yield, ndvi_value FROM field_predictions WHERE field_id = $1 ORDER BY year DESC LIMIT 1",
            str(farm2["id"]),
        )
        if not season2:
            print("  data_status = 'no_prediction' ← LLM sees Unknown crop/score → may call tools")
            print("  → Run POST /predict to generate a prediction row.")
        else:
            print(f"  data_status = 'complete' ✅")
            print(f"  crop={season2['crop_type']}  health={season2['final_health_score']}  yield={season2['predicted_yield']}  ndvi={season2['ndvi_value']}")

    print(SEP)
    print("GROQ_API_KEY set:", bool(os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")))
    print("LLM_PROVIDER:", os.getenv("LLM_PROVIDER", "groq"))
    print("GROQ_MODEL:", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
    print(SEP)
    print("DIAGNOSIS COMPLETE")
    await conn.close()

asyncio.run(run())
