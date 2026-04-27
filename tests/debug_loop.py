import asyncio
import sys
import logging
from uuid import uuid4

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from chatbot.graph.workflow import agrisage_graph
from langchain_core.messages import HumanMessage

async def main():
    print("Testing loop...")
    uid = '30156622-0b76-43e6-8eef-33bb6f7eae0c'
    
    initial_state = {
        "messages":                [HumanMessage(content="what is my health score?")],
        "farmer_id":               uid,
        "thread_id":               "test-thread",
        "tool_call_count":         0,
        "tool_call_counts":        {},  # Fix #4: per-tool counts
    }

    
    async for event in agrisage_graph.astream(initial_state, config={"recursion_limit": 50}):
        for node_name, values in event.items():
            print(f"\n--- NODE: {node_name} ---")
            if "messages" in values:
                for msg in values["messages"]:
                    print(f"[{getattr(msg, 'type', type(msg))}] {getattr(msg, 'content', '')[:200]}")
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        print("  -> TOOLS CALLED:", msg.tool_calls)

if __name__ == '__main__':
    asyncio.run(main())
