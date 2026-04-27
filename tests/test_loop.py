import asyncio
import sys
import logging
from uuid import uuid4
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from chatbot.agent import run_agent
from database import create_pool

async def main():
    print("Testing loop...")
    pool = await create_pool('postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require')
    async with pool.acquire() as conn:
        uid = str(uuid4())
        print(f"Creating mock farmer with ID {uid}")
        await conn.execute("INSERT INTO farmers(id, name, phone, state_name, dist_name) VALUES($1, 'Mock', $2, 'Punjab', 'Ludhiana')", uid, uid[:20])
        # Insert a chat to trigger it
        print("Running agent...")
        res = await run_agent(uid, "what is my score?")
        print("AGENT RETURNED:", res)
        # cleanup
        await conn.execute("DELETE FROM farmers WHERE id=$1", uid)

if __name__ == '__main__':
    asyncio.run(main())
