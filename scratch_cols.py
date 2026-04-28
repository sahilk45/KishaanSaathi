import os
import asyncio
import asyncpg
import json

async def main():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    
    conn = await asyncpg.connect(dsn)
    
    try:
        # Fetch columns for district_climate_history
        cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'district_climate_history'")
        
        data = [r['column_name'] for r in cols]
        
        with open('scratch_cols.json', 'w') as f:
            json.dump(data, f, indent=2)
            
    finally:
        await conn.close()

asyncio.run(main())
