# -*- coding: utf-8 -*-
"""
NoteBook/test_walkforward_model.py
====================================
Tests krishi_xgb_final.pkl (Walk-Forward model) with proper 33-feature
computation from KrishiTwin_Final_Engineered.csv.

Checks:
  - Are yields realistic or inflated?
  - Per-crop / per-district accuracy
  - Comparison vs actual yield in CSV

Run: python test_walkforward_model.py
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import joblib

# ── Paths ─────────────────────────────────────────────────────────────────────
NOTEBOOK_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH   = os.path.join(NOTEBOOK_DIR, "Model", "krishi_xgb_final.pkl")
CROP_ENC     = os.path.join(NOTEBOOK_DIR, "Model", "crop_encoder.pkl")
STATE_ENC    = os.path.join(NOTEBOOK_DIR, "Model", "state_encoder.pkl")
CSV_PATH     = os.path.join(NOTEBOOK_DIR, "..", "Dataset", "KrishiTwin_Final_Engineered.csv")

# ── Load artifacts ─────────────────────────────────────────────────────────────
print("="*65)
print("  LOADING MODEL ARTIFACTS")
print("="*65)
model    = joblib.load(MODEL_PATH)
le_crop  = joblib.load(CROP_ENC)
le_state = joblib.load(STATE_ENC)

print(f"  Model     : {MODEL_PATH.split(os.sep)[-1]}")
print(f"  Crop enc  : {len(le_crop.classes_)} classes")
print(f"  State enc : {len(le_state.classes_)} classes")
print(f"  XGB trees : {model.n_estimators}")

# ── Load CSV & clean ───────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  LOADING CSV & BUILDING ALL 33 FEATURES")
print("="*65)

df = pd.read_csv(CSV_PATH)
df.columns = [c.replace('..', '.').strip() for c in df.columns]
rename_map = {'State.Name': 'State Name', 'dist.name': 'dist_name', 'dist.code': 'dist_code'}
df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
df['dist_name']  = df['dist_name'].astype(str).str.lower().str.strip()
df['State Name'] = df['State Name'].astype(str).str.lower().str.strip()
df = df.sort_values(['dist_code', 'year']).reset_index(drop=True)
print(f"  CSV rows   : {len(df):,}")
print(f"  Year range : {df['year'].min()} – {df['year'].max()}")
print(f"  Districts  : {df['dist_code'].nunique()}")

# ── STEP 1: Lag Features ───────────────────────────────────────────────────────
LAG_COLS  = ['NPK_Intensity_KgHa', 'Irrigation_Intensity_Ratio', 'WDI',
             'Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'Rabi_Avg_MaxTemp']
LAG_YEARS = [1, 2, 3]

for col in LAG_COLS:
    if col in df.columns:
        for lag in LAG_YEARS:
            df[f'{col}_Lag{lag}'] = df.groupby('dist_code')[col].shift(lag)

# ── STEP 2: Delta Features (YoY change) ───────────────────────────────────────
DELTA_COLS = ['Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'NPK_Intensity_KgHa']
for col in DELTA_COLS:
    lag1 = f'{col}_Lag1'
    if lag1 in df.columns:
        df[f'{col}_Delta1'] = df[col] - df[lag1]

# ── STEP 3: 3-Year Rolling Mean ────────────────────────────────────────────────
ROLLING_COLS = ['Kharif_Avg_MaxTemp', 'Kharif_Total_Rain']
for col in ROLLING_COLS:
    if col in df.columns:
        df[f'{col}_Roll3'] = (
            df.groupby('dist_code')[col]
              .transform(lambda x: x.shift(1).rolling(window=3, min_periods=1).mean())
        )

# ── STEP 4: Encode State & Crop ───────────────────────────────────────────────
df['State_Encoded'] = df['State Name'].apply(
    lambda s: int(le_state.transform([s])[0]) if s in le_state.classes_ else -1
)

# ── STEP 5: Melt to long format (one row per district-year-crop) ───────────────
yield_cols = [c for c in df.columns if 'YIELD' in c.upper() and
              c not in ['RICE YIELD (Kg per ha)', 'PEARL MILLET YIELD (Kg per ha)',
                        'CHICKPEA YIELD (Kg per ha)', 'GROUNDNUT YIELD (Kg per ha)',
                        'SUGARCANE YIELD (Kg per ha)']]
# Actually use all yield cols found
all_yield_cols = [c for c in df.columns if 'YIELD' in c.upper() or 'Yield' in c]
# Identify numeric yield columns
yield_value_cols = []
for c in df.columns:
    if ('YIELD' in c.upper() or 'yield' in c.lower()) and df[c].dtype in [float, int, 'float64', 'int64']:
        yield_value_cols.append(c)

BASE_FEATURES = [
    'dist_code', 'year', 'State Name', 'dist_name',
    'NPK_Intensity_KgHa', 'Irrigation_Intensity_Ratio', 'WDI',
    'Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'Rabi_Avg_MaxTemp',
    'District_Soil_Health_Score', 'State_Encoded',
]
lag_cols_all = [c for c in df.columns if '_Lag' in c or '_Delta' in c or '_Roll' in c]

id_cols     = BASE_FEATURES + lag_cols_all
melt_cols   = [c for c in yield_value_cols if c in df.columns]

df_melted = df[id_cols + melt_cols].melt(
    id_vars=id_cols, value_vars=melt_cols,
    var_name='Crop_Type', value_name='Actual_Yield'
)

# Encode crop
df_melted['Crop_Encoded'] = df_melted['Crop_Type'].apply(
    lambda c: int(le_crop.transform([c])[0]) if c in le_crop.classes_ else -1
)

# Drop rows with unknown crop/state encoding
df_melted = df_melted[(df_melted['Crop_Encoded'] >= 0) & (df_melted['State_Encoded'] >= 0)]

# Drop rows where lag is NaN (first 3 years per district)
lag_feature_cols = [f'{c}_Lag{l}' for c in LAG_COLS for l in LAG_YEARS if c in df.columns]
df_melted = df_melted.dropna(subset=lag_feature_cols).reset_index(drop=True)

print(f"  Total prediction rows after melting + lag drop: {len(df_melted):,}")
print(f"  Unique crops   : {df_melted['Crop_Type'].nunique()}")
print(f"  Unique districts: {df_melted['dist_code'].nunique()}")

# ── STEP 6: Build feature matrix (33 features, exact order) ──────────────────
BASE_MODEL_FEATURES = [
    'year', 'State_Encoded', 'Crop_Encoded',
    'NPK_Intensity_KgHa', 'Irrigation_Intensity_Ratio', 'WDI',
    'Kharif_Avg_MaxTemp', 'Kharif_Total_Rain', 'Rabi_Avg_MaxTemp',
    'District_Soil_Health_Score',
]
LAG_MODEL_FEATURES = [c for c in df_melted.columns
                      if ('_Lag' in c or '_Delta' in c or '_Roll' in c)]
ALL_FEATURES = [f for f in BASE_MODEL_FEATURES + LAG_MODEL_FEATURES if f in df_melted.columns]

print(f"\n  Total features fed to model: {len(ALL_FEATURES)}")

X = df_melted[ALL_FEATURES]

# ── STEP 7: Predict ───────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  RUNNING PREDICTIONS")
print("="*65)

preds_log = model.predict(X)
preds_raw = np.maximum(np.expm1(preds_log), 0)
df_melted['Predicted_Yield'] = preds_raw

# ── STEP 8: Analysis ──────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  ANALYSIS REPORT — Walk-Forward Model (33 Features)")
print("="*65)

actual  = df_melted['Actual_Yield'].values
pred    = df_melted['Predicted_Yield'].values

from sklearn.metrics import r2_score, mean_absolute_error

overall_r2   = r2_score(actual, pred)
overall_mae  = mean_absolute_error(actual, pred)
overall_mape = np.mean(np.abs((actual - pred) / np.maximum(actual, 1))) * 100
overall_bias = np.mean(pred - actual)  # +ve = over-prediction, -ve = under

print(f"\n  -- OVERALL METRICS --")
print(f"  R2 Score       : {overall_r2:.4f}")
print(f"  MAE (kg/ha)    : {overall_mae:.1f}")
print(f"  MAPE           : {overall_mape:.1f}%")
print(f"  Bias (Pred-Act): {overall_bias:+.1f} kg/ha  {'[OVER-PREDICTING]' if overall_bias > 0 else '[UNDER-PREDICTING]'}")

# Inflation check
print(f"\n  -- YIELD RANGE CHECK --")
print(f"  Actual   | Min: {actual.min():.0f}  Max: {actual.max():.0f}  Mean: {actual.mean():.0f}")
print(f"  Predicted| Min: {pred.min():.0f}  Max: {pred.max():.0f}  Mean: {pred.mean():.0f}")

# High prediction outliers
HIGH_THRESH = 10000
n_inflated  = (pred > HIGH_THRESH).sum()
pct_inflated = n_inflated / len(pred) * 100
print(f"\n  -- INFLATION CHECK (predicted > {HIGH_THRESH} kg/ha) --")
print(f"  Count  : {n_inflated:,} / {len(pred):,} rows ({pct_inflated:.2f}%)")
print(f"  Max predicted yield: {pred.max():.0f} kg/ha")

# Per-crop summary
print(f"\n  -- PER-CROP SUMMARY --")
print(f"  {'Crop':<42} {'Actual Mean':>12} {'Pred Mean':>10} {'Bias':>10} {'MAE':>8} {'% Inflated':>10}")
print(f"  {'-'*95}")
crop_summary = []
for crop, grp in df_melted.groupby('Crop_Type'):
    a = grp['Actual_Yield'].values
    p = grp['Predicted_Yield'].values
    bias  = np.mean(p - a)
    mae   = mean_absolute_error(a, p)
    pct_i = (p > HIGH_THRESH).sum() / len(p) * 100
    crop_summary.append({
        'Crop': crop, 'Actual_Mean': a.mean(), 'Pred_Mean': p.mean(),
        'Bias': bias, 'MAE': mae, 'Pct_Inflated': pct_i
    })
crop_df = pd.DataFrame(crop_summary).sort_values('Pct_Inflated', ascending=False)
for _, row in crop_df.iterrows():
    flag = "  <<< INFLATED" if row['Pct_Inflated'] > 5 else ""
    print(f"  {row['Crop']:<42} {row['Actual_Mean']:>12.0f} {row['Pred_Mean']:>10.0f} "
          f"{row['Bias']:>+10.0f} {row['MAE']:>8.0f} {row['Pct_Inflated']:>9.1f}%{flag}")

# Worst inflated predictions
print(f"\n  -- TOP 10 MOST INFLATED PREDICTIONS --")
worst = df_melted.nlargest(10, 'Predicted_Yield')[
    ['dist_name', 'year', 'Crop_Type', 'Actual_Yield', 'Predicted_Yield']
]
print(f"  {'District':<20} {'Year':>5} {'Crop':<42} {'Actual':>8} {'Predicted':>12}")
print(f"  {'-'*90}")
for _, r in worst.iterrows():
    print(f"  {r['dist_name']:<20} {int(r['year']):>5} {r['Crop_Type']:<42} "
          f"{r['Actual_Yield']:>8.0f} {r['Predicted_Yield']:>12.0f}")

# Last-year test (2015) — what the model sees at training boundary
print(f"\n  -- 2015 TEST CASES (Last training year, Wheat only) --")
wheat_2015 = df_melted[
    (df_melted['year'] == 2015) &
    (df_melted['Crop_Type'] == 'WHEAT.YIELD.Kg.per.ha.')
].copy()
if len(wheat_2015) > 0:
    w_r2  = r2_score(wheat_2015['Actual_Yield'], wheat_2015['Predicted_Yield'])
    w_mae = mean_absolute_error(wheat_2015['Actual_Yield'], wheat_2015['Predicted_Yield'])
    print(f"  Wheat 2015 rows: {len(wheat_2015)}")
    print(f"  R2   : {w_r2:.4f}")
    print(f"  MAE  : {w_mae:.1f} kg/ha")
    print(f"  Max predicted wheat 2015: {wheat_2015['Predicted_Yield'].max():.0f} kg/ha")
    print(f"  Mean actual wheat 2015  : {wheat_2015['Actual_Yield'].mean():.0f} kg/ha")
    print(f"  Mean predicted wheat 2015: {wheat_2015['Predicted_Yield'].mean():.0f} kg/ha")
else:
    print("  No wheat 2015 data found.")

# Agra wheat specifically
print(f"\n  -- AGRA WHEAT TEST CASES (all years) --")
agra_wheat = df_melted[
    (df_melted['dist_name'] == 'agra') &
    (df_melted['Crop_Type'] == 'WHEAT.YIELD.Kg.per.ha.')
].copy()
if len(agra_wheat) > 0:
    print(f"  {'Year':>5} {'Actual':>10} {'Predicted':>12} {'Error':>10} {'Ratio':>8}")
    print(f"  {'-'*50}")
    for _, r in agra_wheat.sort_values('year').iterrows():
        ratio = r['Predicted_Yield'] / max(r['Actual_Yield'], 1)
        print(f"  {int(r['year']):>5} {r['Actual_Yield']:>10.0f} {r['Predicted_Yield']:>12.0f} "
              f"{r['Predicted_Yield']-r['Actual_Yield']:>+10.0f} {ratio:>8.2f}x")
else:
    print("  Agra not found in CSV (dist_name mismatch?)")

# Final verdict
print(f"\n{'='*65}")
print(f"  VERDICT")
print(f"{'='*65}")
if pct_inflated < 1.0 and overall_bias < 200:
    verdict = "GOOD — yields are realistic. No significant inflation."
elif pct_inflated < 5.0:
    verdict = "ACCEPTABLE — minor inflation in a few crop types."
else:
    verdict = "WARNING — significant inflation detected. Review zero-yield rows."
print(f"  {verdict}")
print(f"  Overall R2   : {overall_r2:.4f}  ({'Good' if overall_r2 > 0.75 else 'Needs work'})")
print(f"  Overall Bias : {overall_bias:+.0f} kg/ha  ({'Slight over-predict' if 0 < overall_bias < 500 else 'Over-inflate' if overall_bias >= 500 else 'Under-predict'})")
print(f"  Inflated rows: {pct_inflated:.2f}%")
print(f"{'='*65}\n")
