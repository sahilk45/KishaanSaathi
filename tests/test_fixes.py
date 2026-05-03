"""Quick test: confirm that invalid farmer_id/field_id returns 422 not 500."""
import urllib.request, json, urllib.error

results = []

# Test 1: farm/register with non-UUID farmer_id (was 500, should now be 422)
try:
    payload = json.dumps({
        "farmer_id": "farmer_001",
        "field_name": "X",
        "coordinates": [[1,1],[2,1],[2,2],[1,2],[1,1]]
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/farm/register",
        data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    urllib.request.urlopen(req)
    results.append("FAIL  /farm/register: got 200, expected 422")
except urllib.error.HTTPError as e:
    code = e.code
    body = json.loads(e.read())
    if code == 422:
        results.append(f"PASS  /farm/register: 422 => {body['detail'][0]['msg']}")
    else:
        results.append(f"FAIL  /farm/register: got {code} => {body}")

# Test 2: predict with non-UUID field_id (was 500, should now be 422)
try:
    payload = json.dumps({
        "field_id": "field_001",
        "crop_type": "WHEAT.YIELD.Kg.per.ha.",
        "npk_input": 50,
        "year": 2024
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/predict",
        data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    urllib.request.urlopen(req)
    results.append("FAIL  /predict: got 200, expected 422")
except urllib.error.HTTPError as e:
    code = e.code
    body = json.loads(e.read())
    if code == 422:
        results.append(f"PASS  /predict: 422 => {body['detail'][0]['msg']}")
    else:
        results.append(f"FAIL  /predict: got {code} => {body}")

# Test 3: health check
r = urllib.request.urlopen("http://127.0.0.1:8000/health")
health = json.loads(r.read())
results.append(f"PASS  /health: {health}")

# Test 4: crops list
r = urllib.request.urlopen("http://127.0.0.1:8000/crops")
crops = json.loads(r.read())
results.append(f"PASS  /crops: {len(crops['crops'])} crop types returned")

print()
for line in results:
    icon = "[OK]" if line.startswith("PASS") else "[FAIL]"
    print(icon, line)
print()
