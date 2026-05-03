# -*- coding: utf-8 -*-
import os
import time
import warnings
import joblib
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# --- Configuration ---
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH   = os.path.join(BASE_DIR, "Encoder_and_model", "krishi_twin_xgb_model_complete.pkl")
CROP_ENC     = os.path.join(BASE_DIR, "Encoder_and_model", "crop_encoder.pkl")
STATE_ENC    = os.path.join(BASE_DIR, "Encoder_and_model", "state_encoder.pkl")

print("="*70)
print("             KRISHISARTHI PRODUCTION READINESS AUDIT")
print("="*70)

# 1. Load Artifacts
model    = joblib.load(MODEL_PATH)
le_crop  = joblib.load(CROP_ENC)
le_state = joblib.load(STATE_ENC)

# Get the EXACT feature order required by the model
EXPECTED_FEATURES = model.feature_names_in_

# 2. Setup Test Data
def get_mock_input(year=2015, crop_full="WHEAT.YIELD.Kg.per.ha.", state="uttar pradesh"):
    data = {
        'year': year,
        'State_Encoded': le_state.transform([state])[0] if state in le_state.classes_ else 0,
        'Crop_Encoded': le_crop.transform([crop_full])[0],
        'NPK_Intensity_KgHa': 120.0,
        'Irrigation_Intensity_Ratio': 0.8,
        'WDI': 0.3,
        'Kharif_Avg_MaxTemp': 32.0,
        'Kharif_Total_Rain': 900.0,
        'Rabi_Avg_MaxTemp': 26.0,
        'District_Soil_Health_Score': 140.0,
    }
    for i in range(1, 4):
        data[f'NPK_Intensity_KgHa_Lag{i}'] = 120.0
        data[f'Irrigation_Intensity_Ratio_Lag{i}'] = 0.8
        data[f'WDI_Lag{i}'] = 0.3
        data[f'Kharif_Avg_MaxTemp_Lag{i}'] = 32.0
        data[f'Kharif_Total_Rain_Lag{i}'] = 900.0
        data[f'Rabi_Avg_MaxTemp_Lag{i}'] = 26.0
    
    data['Kharif_Avg_MaxTemp_Delta1'] = 0.0
    data['Kharif_Total_Rain_Delta1'] = 0.0
    data['NPK_Intensity_KgHa_Delta1'] = 0.0
    data['Kharif_Avg_MaxTemp_Roll3'] = 32.0
    data['Kharif_Total_Rain_Roll3'] = 900.0
    
    df = pd.DataFrame([data])
    return df[EXPECTED_FEATURES]

# --- TEST 1: LATENCY ---
print(f"[TEST 1] Latency Check")
sample = get_mock_input()
latencies = []
for _ in range(50):
    t0 = time.time()
    model.predict(sample)
    latencies.append((time.time() - t0) * 1000)
avg_latency = np.mean(latencies)
print(f"  - Avg Inference Time: {avg_latency:.2f} ms")
status1 = "PASS" if avg_latency < 50 else "WARN"

# --- TEST 2: YIELD INFLATION ---
print(f"\n[TEST 2] Yield Inflation Stress Test")
extreme = get_mock_input()
extreme['NPK_Intensity_KgHa'] = 500.0
extreme['Kharif_Total_Rain'] = 3000.0
extreme['Kharif_Avg_MaxTemp'] = 45.0
pred_extreme = np.expm1(model.predict(extreme))[0]
print(f"  - Extreme Input Prediction: {pred_extreme:.0f} kg/ha")
status2 = "PASS" if pred_extreme < 20000 else "FAIL"

# --- TEST 3: ZERO INPUTS ---
print(f"\n[TEST 3] Zero-Input Resilience")
zero_data = get_mock_input()
zero_data['NPK_Intensity_KgHa'] = 0.0
zero_data['Irrigation_Intensity_Ratio'] = 0.0
pred_zero = np.expm1(model.predict(zero_data))[0]
print(f"  - Zero NPK/Irr Prediction: {pred_zero:.0f} kg/ha")
status3 = "PASS" if pred_zero > 0 else "WARN"

# --- TEST 4: FUTURE YEAR STABILITY ---
baseline_val = np.expm1(model.predict(get_mock_input(year=2015)))[0]
future_val = np.expm1(model.predict(get_mock_input(year=2026)))[0]
print(f"\n[TEST 4] Year 2026 Stability")
print(f"  - Year 2015 Baseline  : {baseline_val:.0f} kg/ha")
print(f"  - Year 2026 Prediction: {future_val:.0f} kg/ha")
status4 = "PASS" if abs(future_val - baseline_val) < 1.0 else "WARN"

# --- TEST 5: MULTI-CROP COVERAGE ---
print(f"\n[TEST 5] Multi-Crop Coverage")
test_crops = [
    "WHEAT.YIELD.Kg.per.ha.",
    "RICE YIELD (Kg per ha)",
    "MAIZE.YIELD.Kg.per.ha.",
    "SUGARCANE YIELD (Kg per ha)"
]
found_crops = 0
for c in test_crops:
    try:
        c_data = get_mock_input(crop_full=c)
        np.expm1(model.predict(c_data))
        found_crops += 1
    except: pass
print(f"  - Tested {len(test_crops)} major crops: {found_crops}/{len(test_crops)} successful")
status5 = "PASS" if found_crops == len(test_crops) else "FAIL"

# --- FINAL SUMMARY ---
print("\n" + "="*70)
print("FINAL DEPLOYMENT VERDICT")
print("="*70)
print(f"1. Latency (<50ms)        : {status1}")
print(f"2. Inflation Safeguard    : {status2}")
print(f"3. Resilience (Zero-In)   : {status3}")
print(f"4. Time-Series Stability  : {status4}")
print(f"5. Crop Coverage          : {status5}")

overall = "GREEN - READY" if all(s == "PASS" for s in [status1, status2, status5]) else "YELLOW - CAUTION"
print(f"\nOVERALL STATUS: {overall}")
print("="*70)
