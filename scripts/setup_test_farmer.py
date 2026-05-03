import requests
import json

BASE = "http://127.0.0.1:8000"

print("=" * 60)
print("STEP 1: Register Farmer")
print("=" * 60)

farmer_res = requests.post(f"{BASE}/farmers/register", json={
    "name": "Arjun Yadav",
    "phone": "+91-9876543100",
    "state_name": "Uttar Pradesh",
    "dist_name": "Agra"
})
print("Status:", farmer_res.status_code)
farmer_data = farmer_res.json()
print("Response:", json.dumps(farmer_data, indent=2))

if farmer_res.status_code not in (200, 201):
    print("FAILED - stopping.")
    exit(1)

farmer_id = farmer_data["farmer_id"]
print(f"\nFarmer ID: {farmer_id}")

print("\n" + "=" * 60)
print("STEP 2: Register Farm Field (near Agra, UP)")
print("=" * 60)

# Agra coordinates — real agricultural area near Agra district
farm_res = requests.post(f"{BASE}/farm/register", json={
    "farmer_id": farmer_id,
    "field_name": "Yamuna Khadar Field",
    "coordinates": [
        [78.0164, 27.1767],
        [78.0264, 27.1767],
        [78.0264, 27.1867],
        [78.0164, 27.1867],
        [78.0164, 27.1767]
    ],
    "area_hectares": 2.5
})
print("Status:", farm_res.status_code)
farm_data = farm_res.json()
print("Response:", json.dumps(farm_data, indent=2))

if farm_res.status_code not in (200, 201):
    print("FAILED - stopping.")
    exit(1)

field_id = farm_data["field_id"]
print(f"\nField ID: {field_id}")

print("\n" + "=" * 60)
print("STEP 3: Run Prediction (Wheat crop, 2025)")
print("=" * 60)

pred_res = requests.post(f"{BASE}/predict", json={
    "field_id": field_id,
    "crop_type": "WHEAT.YIELD.Kg.per.ha.",
    "npk_input": 120.0,
    "year": 2025,
    "irrigation_ratio": 0.85
})
print("Status:", pred_res.status_code)
pred_data = pred_res.json()
print("Response:", json.dumps(pred_data, indent=2, default=str))

print("\n" + "=" * 60)
print("COMPLETE! Here is your test summary:")
print("=" * 60)
print(f"farmer_id  : {farmer_id}")
print(f"field_id   : {field_id}")
print(f"farmer_name: Arjun Yadav")
print(f"state      : Uttar Pradesh")
print(f"district   : Agra")
print(f"phone      : +91-9876543100")
print(f"crop       : Wheat")
print(f"year       : 2025")
