# -*- coding: utf-8 -*-
"""
Full Statistical Validation for Deployment Report
Tests the production model on the full dataset and generates deployment metrics.
"""
import os, warnings, joblib, time
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_absolute_error, mean_absolute_percentage_error
warnings.filterwarnings("ignore")

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "Encoder_and_model", "krishi_twin_xgb_model_complete.pkl")
CROP_ENC   = os.path.join(BASE_DIR, "Encoder_and_model", "crop_encoder.pkl")
STATE_ENC  = os.path.join(BASE_DIR, "Encoder_and_model", "state_encoder.pkl")
CSV_PATH   = os.path.join(BASE_DIR, "Dataset", "KrishiTwin_Final_Engineered.csv")

model    = joblib.load(MODEL_PATH)
le_crop  = joblib.load(CROP_ENC)
le_state = joblib.load(STATE_ENC)
FEATS    = model.feature_names_in_

# --- Build Dataset ---
df = pd.read_csv(CSV_PATH)
df.columns = [c.replace('..', '.').strip() for c in df.columns]
df.rename(columns={'State.Name': 'State Name', 'dist.name': 'dist_name', 'dist.code': 'dist_code'}, inplace=True)
df['dist_name']  = df['dist_name'].astype(str).str.lower().str.strip()
df['State Name'] = df['State Name'].astype(str).str.lower().str.strip()
df = df.sort_values(['dist_code','year']).reset_index(drop=True)
LAG_COLS = ['NPK_Intensity_KgHa','Irrigation_Intensity_Ratio','WDI','Kharif_Avg_MaxTemp','Kharif_Total_Rain','Rabi_Avg_MaxTemp']
for col in LAG_COLS:
    for lag in [1,2,3]: df[f'{col}_Lag{lag}'] = df.groupby('dist_code')[col].shift(lag)
for col in ['Kharif_Avg_MaxTemp','Kharif_Total_Rain','NPK_Intensity_KgHa']:
    df[f'{col}_Delta1'] = df[col] - df[f'{col}_Lag1']
for col in ['Kharif_Avg_MaxTemp','Kharif_Total_Rain']:
    df[f'{col}_Roll3'] = df.groupby('dist_code')[col].transform(lambda x: x.shift(1).rolling(window=3,min_periods=1).mean())
yield_cols = [c for c in df.columns if 'YIELD' in c.upper() and df[c].dtype == 'float64']
df['State_Encoded'] = df['State Name'].apply(lambda s: int(le_state.transform([s])[0]) if s in le_state.classes_ else -1)
df_m = df.melt(id_vars=[c for c in df.columns if c not in yield_cols], value_vars=yield_cols, var_name='Crop_Type', value_name='Actual_Yield')
df_m['Crop_Encoded'] = df_m['Crop_Type'].apply(lambda c: int(le_crop.transform([c])[0]) if c in le_crop.classes_ else -1)
df_m = df_m[(df_m['Crop_Encoded']>=0)&(df_m['State_Encoded']>=0)].dropna(subset=['NPK_Intensity_KgHa_Lag3']).reset_index(drop=True)

# Predict
t0 = time.time()
raw_preds = model.predict(df_m[FEATS])
predict_ms = (time.time() - t0) * 1000
preds = np.maximum(np.expm1(raw_preds), 0)
df_m['Predicted'] = preds
actual = df_m['Actual_Yield'].values

# --- Metrics ---
r2  = r2_score(actual, preds)
mae = mean_absolute_error(actual, preds)
bias = np.mean(preds - actual)
max_pred = preds.max()
min_pred = preds.min()
inflation_rows = (preds > 15000).sum()
inflation_pct  = inflation_rows / len(preds) * 100
n_crops  = df_m['Crop_Type'].nunique()
n_states = df_m['State Name'].nunique()

# Only non-zero actual rows (real crop data)
real = df_m[df_m['Actual_Yield'] > 0].copy()
r2_real  = r2_score(real['Actual_Yield'], real['Predicted'])
mae_real = mean_absolute_error(real['Actual_Yield'], real['Predicted'])

# Per crop performance
crop_stats = df_m.groupby('Crop_Type').apply(
    lambda x: pd.Series({
        'R2':  r2_score(x['Actual_Yield'], x['Predicted']),
        'MAE': mean_absolute_error(x['Actual_Yield'], x['Predicted']),
        'Bias': (x['Predicted'] - x['Actual_Yield']).mean(),
        'N':    len(x)
    })
).sort_values('R2', ascending=False)

# Agra Wheat 2015
agra_w = df_m[(df_m['dist_name']=='agra') & (df_m['Crop_Type']=='WHEAT.YIELD.Kg.per.ha.') & (df_m['year']==2015)]

print("===METRICS===")
print(f"TOTAL_ROWS={len(df_m)}")
print(f"R2_ALL={r2:.4f}")
print(f"MAE_ALL={mae:.1f}")
print(f"BIAS={bias:.1f}")
print(f"R2_REAL={r2_real:.4f}")
print(f"MAE_REAL={mae_real:.1f}")
print(f"MAX_PRED={max_pred:.0f}")
print(f"MIN_PRED={min_pred:.0f}")
print(f"INFLATION_ROWS={inflation_rows}")
print(f"INFLATION_PCT={inflation_pct:.4f}")
print(f"N_CROPS={n_crops}")
print(f"N_STATES={n_states}")
print(f"PRED_TIME_MS={predict_ms:.0f}")
if not agra_w.empty:
    print(f"AGRA_WHEAT_2015_ACTUAL={agra_w['Actual_Yield'].values[0]:.0f}")
    print(f"AGRA_WHEAT_2015_PRED={agra_w['Predicted'].values[0]:.0f}")
print("===CROP_STATS===")
print(crop_stats.to_string())
