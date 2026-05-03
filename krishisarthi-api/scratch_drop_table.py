import os
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def drop_table():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    conn = await asyncpg.connect(dsn)
    
    try:
        print("Dropping district_climate_history...")
        await conn.execute("DROP TABLE IF EXISTS district_climate_history;")
        print("Dropped successfully.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(drop_table())
