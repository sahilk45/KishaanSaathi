import asyncio
from fastapi.testclient import TestClient
from main import app
from chatbot.tools import get_crop_advice
from langchain_core.runnables import RunnableConfig

async def test_all():
    with TestClient(app) as client:
        req = {
            "farmer_id": "740e8268-730f-4bf6-bc2d-540e7d3325e5",
            "field_id": "13eee978-de31-4b68-bad9-5ced53c50e72",
            "crop_type": "WHEAT.YIELD.Kg.per.ha.",
            "npk_input": 120,
            "irrigation_ratio": 0.8
        }
        
        # 1. Run predict endpoint
        res = client.post("/predict", json=req)
        
    # 2. Test get_crop_advice tool
    config = {"configurable": {"farmer_id": "740e8268-730f-4bf6-bc2d-540e7d3325e5"}}
    result = await get_crop_advice.ainvoke({"mode": "cropswap"}, config=config)
    
    with open('scratch_test_result.txt', 'w', encoding='utf-8') as f:
        f.write(result)

if __name__ == "__main__":
    asyncio.run(test_all())
