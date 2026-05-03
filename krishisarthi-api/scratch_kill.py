import os
import asyncio
import asyncpg

async def main():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    
    conn = await asyncpg.connect(dsn)
    
    try:
        # Kill all queries running for more than 1 minute except ours
        query = """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE pid <> pg_backend_pid()
          AND state = 'active'
          AND now() - query_start > interval '1 minute';
        """
        killed = await conn.fetch(query)
        print(f"Killed {len(killed)} stuck queries.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

asyncio.run(main())
