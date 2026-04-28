import os
import asyncio
import asyncpg

async def main():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    
    conn = await asyncpg.connect(dsn)
    
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM district_climate_history")
        print(f"Current rows: {count}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

asyncio.run(main())
