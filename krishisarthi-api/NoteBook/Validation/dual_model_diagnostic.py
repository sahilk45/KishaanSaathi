# -*- coding: utf-8 -*-
"""
Dual-Model Diagnostic Script
Compares krishi_xgb_final.pkl (NoteBook/Model) vs krishi_twin_xgb_model_complete.pkl (Encoder_and_model)
to determine the correct output scale and identify the target variable mismatch.
"""
import os
import warnings
import joblib
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODELS = {
    "A_krishi_xgb_final (NoteBook/Model)": {
        "model": os.path.join(BASE_DIR, "NoteBook", "Model", "krishi_xgb_final.pkl"),
        "crop":  os.path.join(BASE_DIR, "NoteBook", "Model", "crop_encoder.pkl"),
        "state": os.path.join(BASE_DIR, "NoteBook", "Model", "state_encoder.pkl"),
    },
    "B_krishi_twin_complete (Encoder_and_model)": {
        "model": os.path.join(BASE_DIR, "Encoder_and_model", "krishi_twin_xgb_model_complete.pkl"),
        "crop":  os.path.join(BASE_DIR, "Encoder_and_model", "crop_encoder.pkl"),
        "state": os.path.join(BASE_DIR, "Encoder_and_model", "state_encoder.pkl"),
    }
}

print("="*70)
print("  DUAL-MODEL TARGET SCALE DIAGNOSTIC")
print("="*70)

# Inspect feature names and hyperparameters of both models
for name, paths in MODELS.items():
    model = joblib.load(paths["model"])
    params = model.get_params()
    print(f"\n[{name}]")
    print(f"  Features   : {list(model.feature_names_in_)}")
    print(f"  n_estimators: {params.get('n_estimators')}, max_depth: {params.get('max_depth')}, lr: {params.get('learning_rate')}")

print("\n" + "="*70)
print("  LOADING CSV AND BUILDING FEATURES")
print("="*70)

# Load dataset
csv_path = os.path.join(BASE_DIR, "Dataset", "KrishiTwin_Final_Engineered.csv")
df = pd.read_csv(csv_path)
df.columns = [c.replace('..', '.').strip() for c in df.columns]
df.rename(columns={'State.Name': 'State Name', 'dist.name': 'dist_name', 'dist.code': 'dist_code'}, inplace=True)
df['dist_name']  = df['dist_name'].astype(str).str.lower().str.strip()
df['State Name'] = df['State Name'].astype(str).str.lower().str.strip()
df = df.sort_values(['dist_code', 'year']).reset_index(drop=True)

LAG_COLS = ['NPK_Intensity_KgHa', 'Irrigation_Intensity_Ratio', 'WDI', 'Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'Rabi_Avg_MaxTemp']
for col in LAG_COLS:
    for lag in [1, 2, 3]:
        df[f'{col}_Lag{lag}'] = df.groupby('dist_code')[col].shift(lag)
for col in ['Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'NPK_Intensity_KgHa']:
    df[f'{col}_Delta1'] = df[col] - df[f'{col}_Lag1']
for col in ['Kharif_Avg_MaxTemp', 'Kharif_Total_Rain']:
    df[f'{col}_Roll3'] = df.groupby('dist_code')[col].transform(lambda x: x.shift(1).rolling(window=3, min_periods=1).mean())

yield_cols = [c for c in df.columns if 'YIELD' in c.upper() and df[c].dtype in [np.float64, 'float64']]
print(f"  Dataset rows: {len(df)}, Yield columns: {len(yield_cols)}")

print("\n" + "="*70)
print("  RUNNING PREDICTIONS ON AGRA WHEAT 2015 (Ground Truth: ~3,200 kg/ha)")
print("="*70)

for name, paths in MODELS.items():
    model   = joblib.load(paths["model"])
    le_crop = joblib.load(paths["crop"])
    le_state= joblib.load(paths["state"])
    feats   = list(model.feature_names_in_)

    # Build state + crop encoding
    df2 = df.copy()
    df2['State_Encoded'] = df2['State Name'].apply(
        lambda s: int(le_state.transform([s])[0]) if s in le_state.classes_ else -1
    )

    # Find wheat yield column name
    wheat_col = next((c for c in yield_cols if 'WHEAT' in c.upper()), None)
    if not wheat_col:
        print(f"  [{name}]: Wheat column not found!")
        continue

    df2['Crop_Encoded'] = int(le_crop.transform([wheat_col])[0]) if wheat_col in le_crop.classes_ else -1
    df2['Actual_Yield'] = df2[wheat_col]

    # Filter Agra 2015
    agra = df2[(df2['dist_name'] == 'agra') & (df2['year'] == 2015)].copy()
    agra = agra.dropna(subset=['NPK_Intensity_KgHa_Lag3'])

    if agra.empty:
        print(f"  [{name}]: No Agra 2015 data found!")
        continue

    # Check all feats are available
    missing = [f for f in feats if f not in agra.columns]
    if missing:
        print(f"  [{name}]: Missing features: {missing}")
        continue

    raw_pred   = float(model.predict(agra[feats])[0])
    actual     = float(agra['Actual_Yield'].values[0])

    expm1_pred = float(np.expm1(raw_pred))
    x1000_pred = raw_pred * 1000.0

    print(f"\n  [{name}]")
    print(f"    Actual Agra Wheat 2015 : {actual:.0f} kg/ha")
    print(f"    Raw model output       : {raw_pred:.4f}")
    print(f"    If expm1(raw)          : {expm1_pred:.0f} kg/ha  (error: {abs(expm1_pred-actual):.0f})")
    print(f"    If raw * 1000          : {x1000_pred:.0f} kg/ha  (error: {abs(x1000_pred-actual):.0f})")

    # Determine correct scale
    err_expm1 = abs(expm1_pred - actual)
    err_x1000 = abs(x1000_pred - actual)

    if err_expm1 < err_x1000:
        correct_scale = "log1p (expm1 gives correct result)"
    elif err_x1000 < err_expm1:
        correct_scale = "raw/1000 (multiply by 1000 gives correct result)"
    else:
        correct_scale = "UNKNOWN"
    print(f"    >>> Correct Scale Inference: {correct_scale}")

print("\n" + "="*70)
print("  FINAL VERDICT")
print("="*70)
print("  Based on correct scale above, choose which model to deploy.")
print("="*70)
