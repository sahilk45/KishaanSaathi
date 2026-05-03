import pandas as pd
import os

CSV_PATH = r'D:\CA_content\Python\KissanSathi\krishisarthi-api\Dataset\KrishiTwin_Final_Engineered.csv'
df = pd.read_csv(CSV_PATH)

# Clean names and find Agra
df['dist_name'] = df['dist_name'].str.lower().str.strip()
agra_df = df[df['dist_name'] == 'agra'].sort_values('year', ascending=False)

if len(agra_df) < 3:
    print("Not enough data for Agra")
    exit()

# Lags are from the most recent years in the dataset (usually 2019, 2018, 2017)
# But wait, in the dataset, the latest year is usually 2019.
latest_years = agra_df.head(3).to_dict('records')
lag1 = latest_years[0]
lag2 = latest_years[1]
lag3 = latest_years[2]

# Farmer Saksham inputs for Year 2026
farmer_npk = 120.0  # standard
farmer_irr = 0.50   # 50%
farmer_crop = "Wheat"
farmer_state = lag1['State Name'] # Should be Uttar Pradesh
soil_score = lag1['District_Soil_Health_Score']
wdi = lag1['WDI']  # Usually constant or we can take lag1

print("="*50)
print(" ?? Farmer: Saksham | Location: Agra, UP")
print("="*50)

features = {
    # 1. Base / Dynamic Inputs
    "year": 2026,
    "State_Name": farmer_state,
    "Crop_Type": farmer_crop,
    "NPK_Intensity_KgHa": farmer_npk,
    "Irrigation_Intensity_Ratio": farmer_irr,
    "WDI": wdi,
    "Kharif_Avg_MaxTemp": lag1['Kharif_Avg_MaxTemp'], # Assumed for current year if no live data
    "Kharif_Total_Rain": lag1['Kharif_Total_Rain'],
    "Rabi_Avg_MaxTemp": lag1['Rabi_Avg_MaxTemp'],
    "District_Soil_Health_Score": soil_score,
    
    # 2. Lag Features (from CSV t-1, t-2, t-3)
    "NPK_Intensity_KgHa_Lag1": lag1['NPK_Intensity_KgHa'],
    "NPK_Intensity_KgHa_Lag2": lag2['NPK_Intensity_KgHa'],
    "NPK_Intensity_KgHa_Lag3": lag3['NPK_Intensity_KgHa'],
    
    "Irrigation_Intensity_Ratio_Lag1": lag1['Irrigation_Intensity_Ratio'],
    "Irrigation_Intensity_Ratio_Lag2": lag2['Irrigation_Intensity_Ratio'],
    "Irrigation_Intensity_Ratio_Lag3": lag3['Irrigation_Intensity_Ratio'],
    
    "WDI_Lag1": lag1['WDI'],
    "WDI_Lag2": lag2['WDI'],
    "WDI_Lag3": lag3['WDI'],
    
    "Kharif_Avg_MaxTemp_Lag1": lag1['Kharif_Avg_MaxTemp'],
    "Kharif_Avg_MaxTemp_Lag2": lag2['Kharif_Avg_MaxTemp'],
    "Kharif_Avg_MaxTemp_Lag3": lag3['Kharif_Avg_MaxTemp'],
    
    "Kharif_Total_Rain_Lag1": lag1['Kharif_Total_Rain'],
    "Kharif_Total_Rain_Lag2": lag2['Kharif_Total_Rain'],
    "Kharif_Total_Rain_Lag3": lag3['Kharif_Total_Rain'],
    
    "Rabi_Avg_MaxTemp_Lag1": lag1['Rabi_Avg_MaxTemp'],
    "Rabi_Avg_MaxTemp_Lag2": lag2['Rabi_Avg_MaxTemp'],
    "Rabi_Avg_MaxTemp_Lag3": lag3['Rabi_Avg_MaxTemp'],
    
    # 3. Delta Features (Current - Lag1)
    "Kharif_Avg_MaxTemp_Delta1": lag1['Kharif_Avg_MaxTemp'] - lag1['Kharif_Avg_MaxTemp'], # assumed 0 if temp is same
    "Kharif_Total_Rain_Delta1": lag1['Kharif_Total_Rain'] - lag1['Kharif_Total_Rain'],
    "NPK_Intensity_KgHa_Delta1": farmer_npk - lag1['NPK_Intensity_KgHa'],
    
    # 4. Rolling Features (Mean of Lag1, Lag2, Lag3)
    "Kharif_Avg_MaxTemp_Roll3": (lag1['Kharif_Avg_MaxTemp'] + lag2['Kharif_Avg_MaxTemp'] + lag3['Kharif_Avg_MaxTemp']) / 3.0,
    "Kharif_Total_Rain_Roll3": (lag1['Kharif_Total_Rain'] + lag2['Kharif_Total_Rain'] + lag3['Kharif_Total_Rain']) / 3.0,
}

# Add State_Encoded and Crop_Encoded to match 33 exactly (simulate)
features["State_Encoded"] = 19
features["Crop_Encoded"] = 22
del features["State_Name"]
del features["Crop_Type"]

print(f"{'Feature Name':<35} | {'Value':>12}")
print("-" * 50)
for k, v in features.items():
    if isinstance(v, float):
        print(f"{k:<35} | {v:>12.4f}")
    else:
        print(f"{k:<35} | {v:>12}")
print("="*50)
print(f"Total Features Calculated: {len(features)}")
