import asyncio
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

payload = {
    "field_id": "77162d0f-6834-40b3-8e9e-d4da25899729",
    "crop_type": "COTTON.YIELD.Kg.per.ha.",
    "npk_input": 150,
    "year": 2025,
    "irrigation_ratio": 0.5
}

def test():
    with TestClient(app) as client:
        response = client.post("/predict", json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

if __name__ == "__main__":
    test()
