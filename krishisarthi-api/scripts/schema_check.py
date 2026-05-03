import asyncio, os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path('.env'))
import asyncpg

async def check():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'), timeout=10)

    # Get ALL farmers with their prediction status
    farmers = await conn.fetch("""
        SELECT f.id, f.name, f.dist_name, f.state_name,
               COUNT(ff.id) AS field_count,
               COUNT(fp.id) AS pred_count
        FROM farmers f
        LEFT JOIN farm_fields ff ON ff.farmer_id = f.id
        LEFT JOIN field_predictions fp ON fp.field_id::text = ff.id::text
        GROUP BY f.id, f.name, f.dist_name, f.state_name
        ORDER BY pred_count DESC
        LIMIT 10
    """)
    print("All farmers (with field/prediction counts):")
    for f in farmers:
        status = "READY" if f['pred_count'] > 0 else ("HAS FARM" if f['field_count'] > 0 else "NO FARM")
        print(f"  [{status}] id={f['id']}  name={f['name']}  dist={f['dist_name']}  fields={f['field_count']}  preds={f['pred_count']}")

    # Check climate for ludhiana specifically
    climate = await conn.fetchrow("""
        SELECT COUNT(*) AS cnt, AVG(kharif_avg_maxtemp) AS temp, AVG(district_soil_health_score) AS soil
        FROM district_climate_history WHERE LOWER(dist_name) = 'ludhiana'
    """)
    print(f"\nLudhiana climate rows: {climate['cnt']}  avg_temp={climate['temp']}  soil={climate['soil']}")

    await conn.close()

asyncio.run(check())
