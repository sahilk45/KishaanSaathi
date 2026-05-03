"""
e2e_test.py — End-to-end API test for KisanSaathi chatbot
Run while uvicorn is running: python e2e_test.py
"""
import sys
import json
import time
import requests

BASE    = "http://127.0.0.1:8000"
FARMER  = "c59f6f44-1a98-4eaa-8cf0-3581316a32bb"
THREAD  = f"test-thread-{int(time.time())}"   # fresh thread every run

SEP = "=" * 65

def chat(message: str, label: str) -> dict:
    print(f"\n{SEP}")
    print(f"[{label}]")
    print(f"  Q: {message}")
    t0 = time.time()
    resp = requests.post(f"{BASE}/chat", json={
        "farmer_id": FARMER,
        "message":   message,
        "thread_id": THREAD,
        "history":   [],
    }, timeout=60)
    elapsed = time.time() - t0
    data = resp.json()
    reply = data.get("reply", "NO REPLY")
    print(f"  A ({elapsed:.1f}s): {reply[:300]}")
    if "Koi response generate nahi hua" in reply:
        print("  *** FAIL: Got fallback 'no response' reply ***")
    elif "technical issue" in reply:
        print("  *** FAIL: Got error reply ***")
    elif len(reply) > 20:
        print("  *** PASS ***")
    return data

def test_open_meteo():
    """Direct test of Open-Meteo API."""
    print(f"\n{SEP}")
    print("[OPEN-METEO DIRECT TEST]  lat=27.18, lon=78.02 (Agra)")
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 27.18,
            "longitude": 78.02,
            "daily": "temperature_2m_max,precipitation_sum",
            "current_weather": "true",
            "timezone": "Asia/Kolkata",
            "forecast_days": 3,
        },
        timeout=10,
    )
    if resp.status_code == 200:
        d = resp.json()
        cw = d.get("current_weather", {})
        print(f"  Current temp: {cw.get('temperature')}°C  wind: {cw.get('windspeed')} km/h")
        daily = d.get("daily", {})
        for i, date in enumerate(daily.get("time", [])[:3]):
            print(f"  {date}: max {daily['temperature_2m_max'][i]}°C  rain {daily['precipitation_sum'][i]} mm")
        print("  *** PASS: Open-Meteo is working ***")
    else:
        print(f"  *** FAIL: HTTP {resp.status_code} ***")

def test_api_health():
    print(f"\n{SEP}")
    print("[API HEALTH CHECK]")
    try:
        r = requests.get(f"{BASE}/docs", timeout=8)
        print(f"  /docs status: {r.status_code} {'OK' if r.status_code == 200 else 'FAIL'}")
    except Exception as e:
        print(f"  Server not reachable: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print(SEP)
    print("KisanSaathi End-to-End Test")
    print(f"Farmer: {FARMER}")
    print(f"Thread: {THREAD}")

    test_open_meteo()
    test_api_health()   # verify server is up before chats

    # Test 1: Health score from profile (should NOT call any tool)
    chat("Mera health score kya hai?", "T1: Health Score (profile data)")

    # Test 2: Market price (should call get_market_price, NOT get_weather)
    chat("Prices of Wheat in my district?", "T2: Market Price (get_market_price)")

    # Test 3: Weather (should call get_weather -> Open-Meteo)
    chat("Aaj barish hogi kya?", "T3: Weather (get_weather -> Open-Meteo)")

    # Test 4: General advice (from profile, no tools needed)
    chat("Meri fasal ki health kaisi hai?", "T4: Crop Health (from profile)")

    print(f"\n{SEP}")
    print("TEST COMPLETE")
