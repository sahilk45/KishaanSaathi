import asyncio
import asyncpg

async def find_constraint():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    conn = await asyncpg.connect(dsn)
    
    query = """
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'field_predictions'::regclass
      AND contype = 'u';
    """
    res = await conn.fetch(query)
    print("Unique constraints on field_predictions:", [r['conname'] for r in res])
    await conn.close()

asyncio.run(find_constraint())
