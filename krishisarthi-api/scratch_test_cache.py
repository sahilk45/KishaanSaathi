import asyncio
from fastapi.testclient import TestClient
from main import app

async def test_cache_logic():
    with TestClient(app) as client:
        # Request 1
        req1 = {
            "field_id": "13eee978-de31-4b68-bad9-5ced53c50e72",
            "crop_type": "WHEAT.YIELD.Kg.per.ha.",
            "npk_input": 120.0,
            "irrigation_ratio": 0.8,
            "year": 2025
        }
        print("--- REQUEST 1: NPK 120 ---")
        res1 = client.post("/predict", json=req1)
        print("Status:", res1.status_code)
        
        # Request 2 (change NPK)
        req2 = req1.copy()
        req2["npk_input"] = 150.0
        print("\n--- REQUEST 2: NPK 150 ---")
        res2 = client.post("/predict", json=req2)
        print("Status:", res2.status_code)
        
        # Request 3 (same as Request 2, should hit cache)
        print("\n--- REQUEST 3: NPK 150 (Should hit cache) ---")
        res3 = client.post("/predict", json=req2)
        print("Status:", res3.status_code)

if __name__ == "__main__":
    asyncio.run(test_cache_logic())
