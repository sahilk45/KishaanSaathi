import asyncio
import sys
import logging
logging.basicConfig(level=logging.DEBUG)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from chatbot.agent import run_agent

async def test():
    farmer_id = '30156622-0b76-43e6-8eef-33bb6f7eae0c'
    res = await run_agent(farmer_id, 'mera health score batao')
    print("FINAL REPLY:", res)

if __name__ == '__main__':
    asyncio.run(test())
