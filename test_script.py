import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/kishandb"))
    row = await conn.fetchrow("SELECT id FROM farm_fields LIMIT 1")
    if row:
        print("FIELD_ID:", row["id"])
    else:
        print("No fields found")
    await conn.close()

asyncio.run(run())
