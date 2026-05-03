import os
import asyncio
import asyncpg
import json

async def main():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    
    conn = await asyncpg.connect(dsn)
    
    try:
        # Fetch district history for agra
        dist_hist = await conn.fetch("SELECT year, yield_wheat, yield_chickpea FROM district_climate_history WHERE LOWER(dist_name) = 'agra' ORDER BY year DESC LIMIT 5")
        
        data = [dict(r) for r in dist_hist]
        
        with open('scratch_agra.json', 'w') as f:
            json.dump(data, f, indent=2)
            
    finally:
        await conn.close()

asyncio.run(main())
