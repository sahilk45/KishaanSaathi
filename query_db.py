import asyncio
import sys
import database
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    pool = await database.create_pool('postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require')
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT role, tool_name, content FROM chat_messages ORDER BY created_at DESC LIMIT 15')
        for r in rows:
            print(f"[{r['role']}] {r['tool_name']}: {r['content'][:100]}...")

if __name__ == '__main__':
    asyncio.run(main())
