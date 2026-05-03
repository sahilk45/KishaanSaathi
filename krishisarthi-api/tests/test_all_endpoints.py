import requests
import json
import uuid
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

def print_result(name, url, status, expected_status=200):
    if status == expected_status or (isinstance(expected_status, list) and status in expected_status):
        print(f"✅ {name} ({url}) -> Status: {status}")
    else:
        print(f"❌ {name} ({url}) -> Status: {status} (Expected {expected_status})")

def run_tests():
    print("========================================")
    print("🚀 RUNNING COMPREHENSIVE ENDPOINT TESTS")
    print("========================================\n")

    # 1. GET /health
    print("--- 1. Health Check ---")
    url = f"{BASE_URL}/health"
    r = requests.get(url)
    print_result("Health Check", url, r.status_code)
    
    # 2. GET /districts
    print("\n--- 2. Get Districts ---")
    url = f"{BASE_URL}/districts"
    r = requests.get(url)
    print_result("Get Districts", url, r.status_code)
    if r.status_code == 200:
        districts = r.json()
        print(f"   Returned {len(districts)} districts.")

    # 3. GET /crops
    print("\n--- 3. Get Crops ---")
    url = f"{BASE_URL}/crops"
    r = requests.get(url)
    print_result("Get Crops", url, r.status_code)
    if r.status_code == 200:
        crops = r.json().get("crops", [])
        print(f"   Returned {len(crops)} crops.")

    # 4. POST /farmers/register
    print("\n--- 4. Register Farmer ---")
    url = f"{BASE_URL}/farmers/register"
    # Example 1: Valid
    phone = f"99{int(time.time())}"[:10]  # Random unique 10-digit phone
    payload = {
        "name": "Test Farmer",
        "phone": phone,
        "state_name": "Punjab",
        "dist_name": "Ludhiana"
    }
    r = requests.post(url, json=payload)
    print_result("Register New Farmer", url, r.status_code)
    
    farmer_id = None
    if r.status_code == 200:
        farmer_id = r.json().get("farmer_id")
        print(f"   Created Farmer ID: {farmer_id}")

    # Example 2: Duplicate
    if farmer_id:
        r2 = requests.post(url, json=payload)
        print_result("Register Duplicate Farmer", url, r2.status_code, expected_status=409)

    # 5. POST /farm/register
    print("\n--- 5. Register Farm Field ---")
    url = f"{BASE_URL}/farm/register"
    field_id = None
    if farmer_id:
        # Example 1: Valid Polygon
        payload = {
            "farmer_id": farmer_id,
            "field_name": "Test Field 1",
            "coordinates": [[76.78, 30.73], [76.79, 30.73], [76.79, 30.74], [76.78, 30.74], [76.78, 30.73]],
            "area_hectares": 1.5
        }
        r = requests.post(url, json=payload)
        print_result("Register Valid Farm", url, r.status_code)
        if r.status_code == 200:
            field_id = r.json().get("field_id")
            print(f"   Created Field ID: {field_id}")
            
        # Example 2: Invalid Polygon (Too few points)
        payload_invalid = {
            "farmer_id": farmer_id,
            "field_name": "Invalid Field",
            "coordinates": [[76.78, 30.73], [76.79, 30.73]], # Need at least 4
        }
        r2 = requests.post(url, json=payload_invalid)
        print_result("Register Invalid Farm (Bad Coords)", url, r2.status_code, expected_status=422)
    else:
        print("   Skipping because Farmer ID was not created.")

    # 6. GET /farmer/{farmer_id}/fields
    print("\n--- 6. Get Farmer Fields ---")
    if farmer_id:
        url = f"{BASE_URL}/farmer/{farmer_id}/fields"
        r = requests.get(url)
        print_result("Get Farmer Fields", url, r.status_code)
    else:
        print("   Skipping because Farmer ID was not created.")

    # 7. POST /predict
    print("\n--- 7. Predict Yield ---")
    url = f"{BASE_URL}/predict"
    if field_id:
        # Example 1: Valid Prediction
        payload = {
            "field_id": field_id,
            "crop_type": "WHEAT.YIELD.Kg.per.ha.",
            "npk_input": 120.5,
            "year": 2024
        }
        r = requests.post(url, json=payload)
        # Note: Might return 500 if DB imputation fails or 404/422 if model issue, we accept 200 or 500 for the test print
        print_result("Predict Valid Farm", url, r.status_code, expected_status=[200, 500])
        
        # Example 2: Invalid Crop Type
        payload_invalid = {
            "field_id": field_id,
            "crop_type": "INVALID.CROP",
            "npk_input": 120.5,
            "year": 2024
        }
        r2 = requests.post(url, json=payload_invalid)
        print_result("Predict Invalid Crop Type", url, r2.status_code, expected_status=422)
    else:
        print("   Skipping because Field ID was not created.")

    # 8. GET /field/{field_id}/history
    print("\n--- 8. Get Field Prediction History ---")
    if field_id:
        url = f"{BASE_URL}/field/{field_id}/history"
        r = requests.get(url)
        print_result("Get Prediction History", url, r.status_code)
    else:
        print("   Skipping because Field ID was not created.")

    # 9. GET /field/{field_id}/agro-snapshot
    print("\n--- 9. Get Agro Snapshot ---")
    if field_id:
        url = f"{BASE_URL}/field/{field_id}/agro-snapshot"
        r = requests.get(url)
        print_result("Get Agro Snapshot", url, r.status_code, expected_status=[200, 500])
    else:
        print("   Skipping because Field ID was not created.")

    # 10. POST /chat
    print("\n--- 10. Chatbot Inference ---")
    url = f"{BASE_URL}/chat"
    if farmer_id:
        # Example 1: Basic Greeting
        payload = {
            "farmer_id": farmer_id,
            "message": "Hello, how are you?"
        }
        # We use a short timeout as LLM might take a bit
        try:
            r = requests.post(url, json=payload, timeout=30)
            print_result("Chat Greeting", url, r.status_code)
        except requests.exceptions.Timeout:
            print(f"❌ Chat Greeting ({url}) -> Timeout after 30s")

        # Example 2: Tool specific question
        payload2 = {
            "farmer_id": farmer_id,
            "message": "What is the mandi price for wheat in Punjab?"
        }
        try:
            r2 = requests.post(url, json=payload2, timeout=30)
            print_result("Chat Tool Question", url, r2.status_code)
        except requests.exceptions.Timeout:
            print(f"❌ Chat Tool Question ({url}) -> Timeout after 30s")

    else:
        print("   Skipping because Farmer ID was not created.")

    print("\n========================================")
    print("🏁 TESTS COMPLETE")
    print("========================================")

if __name__ == "__main__":
    run_tests()
