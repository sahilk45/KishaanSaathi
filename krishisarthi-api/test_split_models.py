import os
import joblib
import pandas as pd
import numpy as np
import time

MODEL_DIR = r"D:\CA_content\Python\KissanSathi\krishisarthi-api\Encoder_and_model"

kharif_model_path = os.path.join(MODEL_DIR, "krishi_kharif_xgb_final.pkl")
rabi_model_path = os.path.join(MODEL_DIR, "krishi_rabi_xgb_final.pkl")
kharif_feat_path = os.path.join(MODEL_DIR, "kharif_feature_list.pkl")
rabi_feat_path = os.path.join(MODEL_DIR, "rabi_feature_list.pkl")

print("--- Loading Models ---")
xgb_kharif = joblib.load(kharif_model_path)
xgb_rabi = joblib.load(rabi_model_path)
feat_kharif = joblib.load(kharif_feat_path)
feat_rabi = joblib.load(rabi_feat_path)

print(f"Kharif Model: {type(xgb_kharif)}")
print(f"Rabi Model: {type(xgb_rabi)}")

print("\n--- Kharif Features ---")
print(f"Total: {len(feat_kharif)}")
print("Contains Rabi_Avg_MaxTemp?", "Rabi_Avg_MaxTemp" in feat_kharif)
print(feat_kharif)

print("\n--- Rabi Features ---")
print(f"Total: {len(feat_rabi)}")
print("Contains Rabi_Avg_MaxTemp?", "Rabi_Avg_MaxTemp" in feat_rabi)
print(feat_rabi)

print("\n--- Testing Inference ---")
# Dummy data for Kharif
dummy_k = {f: 1.0 for f in feat_kharif}
df_k = pd.DataFrame([dummy_k])
t0 = time.perf_counter()
pred_k = np.expm1(xgb_kharif.predict(df_k)[0])
t1 = time.perf_counter()
print(f"Kharif Prediction Time: {(t1-t0)*1000:.2f} ms | Dummy Pred: {pred_k:.2f}")

# Dummy data for Rabi
dummy_r = {f: 1.0 for f in feat_rabi}
df_r = pd.DataFrame([dummy_r])
t0 = time.perf_counter()
pred_r = np.expm1(xgb_rabi.predict(df_r)[0])
t1 = time.perf_counter()
print(f"Rabi Prediction Time: {(t1-t0)*1000:.2f} ms | Dummy Pred: {pred_r:.2f}")

print("\nAll tests passed successfully.")
