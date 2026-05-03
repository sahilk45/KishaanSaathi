import asyncio
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import database

async def main():
    pool = await database.create_pool('postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require')
    uid = '58c40d7d-0621-4378-9c77-f06215384321'
    async with pool.acquire() as conn:
        farmer = await conn.fetchrow("SELECT * FROM farmers WHERE id = $1", uid)
        print("FARMER:", dict(farmer) if farmer else "NOT FOUND")

        farm = await conn.fetchrow("SELECT * FROM farm_fields WHERE farmer_id = $1", uid)
        print("FARM FIELD:", dict(farm) if farm else "NOT FOUND")

        if farm:
            pred = await conn.fetchrow("SELECT * FROM field_predictions WHERE field_id = $1", str(farm['id']))
            print("PREDICTION:", dict(pred) if pred else "NOT FOUND")

if __name__ == '__main__':
    asyncio.run(main())
