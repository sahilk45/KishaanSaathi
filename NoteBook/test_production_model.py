# -*- coding: utf-8 -*-
import sys
import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import joblib

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR    = os.path.join(BASE_DIR, "Encoder_and_model")
MODEL_PATH   = os.path.join(MODEL_DIR, "krishi_twin_xgb_model_complete.pkl")
CROP_ENC     = os.path.join(MODEL_DIR, "crop_encoder.pkl")
STATE_ENC    = os.path.join(MODEL_DIR, "state_encoder.pkl")
CSV_PATH     = os.path.join(BASE_DIR, "Dataset", "KrishiTwin_Final_Engineered.csv")

print("="*65)
print("  VALIDATING PRODUCTION MODEL (Encoder_and_model)")
print("="*65)

# Load artifacts
model    = joblib.load(MODEL_PATH)
le_crop  = joblib.load(CROP_ENC)
le_state = joblib.load(STATE_ENC)

print(f"  Model File : {os.path.basename(MODEL_PATH)}")
print(f"  XGB Params : {model.get_params().get('n_estimators')} estimators, max_depth={model.get_params().get('max_depth')}")

# Load & Prep Data
df = pd.read_csv(CSV_PATH)
df.columns = [c.replace('..', '.').strip() for c in df.columns]
rename_map = {'State.Name': 'State Name', 'dist.name': 'dist_name', 'dist.code': 'dist_code'}
df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
df['dist_name']  = df['dist_name'].astype(str).str.lower().str.strip()
df['State Name'] = df['State Name'].astype(str).str.lower().str.strip()
df = df.sort_values(['dist_code', 'year']).reset_index(drop=True)

# Build 33 Features
LAG_COLS  = ['NPK_Intensity_KgHa', 'Irrigation_Intensity_Ratio', 'WDI', 'Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'Rabi_Avg_MaxTemp']
for col in LAG_COLS:
    for lag in [1, 2, 3]:
        df[f'{col}_Lag{lag}'] = df.groupby('dist_code')[col].shift(lag)

for col in ['Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'NPK_Intensity_KgHa']:
    df[f'{col}_Delta1'] = df[col] - df[f'{col}_Lag1']

for col in ['Kharif_Avg_MaxTemp', 'Kharif_Total_Rain']:
    df[f'{col}_Roll3'] = df.groupby('dist_code')[col].transform(lambda x: x.shift(1).rolling(window=3, min_periods=1).mean())

df['State_Encoded'] = df['State Name'].apply(lambda s: int(le_state.transform([s])[0]) if s in le_state.classes_ else -1)

# Melt
yield_value_cols = [c for c in df.columns if ('YIELD' in c.upper() or 'yield' in c.lower()) and df[c].dtype in [float, int, 'float64', 'int64']]
BASE_FEATURES = ['dist_code', 'year', 'State Name', 'dist_name', 'NPK_Intensity_KgHa', 'Irrigation_Intensity_Ratio', 'WDI', 'Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'Rabi_Avg_MaxTemp', 'District_Soil_Health_Score', 'State_Encoded']
lag_cols_all = [c for c in df.columns if '_Lag' in c or '_Delta' in c or '_Roll' in c]

df_melted = df[BASE_FEATURES + lag_cols_all + yield_value_cols].melt(id_vars=BASE_FEATURES + lag_cols_all, value_vars=yield_value_cols, var_name='Crop_Type', value_name='Actual_Yield')
df_melted['Crop_Encoded'] = df_melted['Crop_Type'].apply(lambda c: int(le_crop.transform([c])[0]) if c in le_crop.classes_ else -1)
df_melted = df_melted[(df_melted['Crop_Encoded'] >= 0) & (df_melted['State_Encoded'] >= 0)].dropna(subset=[f'NPK_Intensity_KgHa_Lag3']).reset_index(drop=True)

# Feature selection
FEATURES = ['year', 'State_Encoded', 'Crop_Encoded', 'NPK_Intensity_KgHa', 'Irrigation_Intensity_Ratio', 'WDI', 'Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'Rabi_Avg_MaxTemp', 'District_Soil_Health_Score'] + lag_cols_all
FEATURES = [f for f in FEATURES if f in df_melted.columns]

# Predict
X = df_melted[FEATURES]
preds_raw = np.maximum(np.expm1(model.predict(X)), 0)
df_melted['Predicted_Yield'] = preds_raw

# Report
from sklearn.metrics import r2_score, mean_absolute_error
actual = df_melted['Actual_Yield'].values
pred = df_melted['Predicted_Yield'].values

print(f"\n  -- OVERALL PERFORMANCE --")
print(f"  R2 Score       : {r2_score(actual, pred):.4f}")
print(f"  MAE (kg/ha)    : {mean_absolute_error(actual, pred):.1f}")
print(f"  Max Predicted  : {pred.max():.0f}")

print(f"\n  -- AGRA WHEAT SAMPLE (2010-2015) --")
agra = df_melted[(df_melted['dist_name'] == 'agra') & (df_melted['Crop_Type'] == 'WHEAT.YIELD.Kg.per.ha.') & (df_melted['year'] >= 2010)]
print(agra[['year', 'Actual_Yield', 'Predicted_Yield']].sort_values('year').to_string(index=False))

print("\n" + "="*65)
print("  TEST COMPLETE")
print("="*65)
