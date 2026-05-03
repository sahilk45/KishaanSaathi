import os
from typing import Union, Annotated
import json
import httpx
import asyncpg
import asyncio
import time
import numpy as np
import pandas as pd
from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import var_child_runnable_config
from dotenv import load_dotenv

from chatbot.models_loader import get_models, _is_kharif, _current_season, KHARIF_ALT_CROPS, RABI_ALT_CROPS, BENCHMARK_YIELDS

load_dotenv()

def _resolve_config(config: RunnableConfig | None) -> dict:
    """Return config dict, falling back to LangChain's context variable when config is None.
    LangChain sets var_child_runnable_config when ainvoke is called with a config,
    even if the config isn't injected into the tool function parameter directly.
    """
    if config is not None:
        return config
    try:
        ctx = var_child_runnable_config.get()
        return ctx if ctx is not None else {}
    except LookupError:
        return {}

DB_URL = os.getenv("DATABASE_URL")
MANDI_JSON_PATH = os.getenv("MANDI_JSON_PATH")
AGMARKNET_URL = os.getenv("AGMARKNET_URL")
OPEN_METEO_URL = os.getenv("OPEN_METEO_URL")

# Hinglish to English Map
HINGLISH_CROP_MAP = {
    "gehu": "wheat", "gehun": "wheat", "wheat": "wheat",
    "chawal": "rice", "dhan": "rice",  "rice": "rice",
    "makka": "maize", "maize": "maize", "corn": "maize",
    "bajra": "pearl millet", "bajra millet": "pearl millet",
    "jowar": "sorghum", "jwar": "sorghum",
    "jau": "barley", "barley": "barley",
    "chana": "chickpea", "chane": "chickpea", "chickpea": "chickpea",
    "arhar": "pigeonpea", "tur": "pigeonpea", "toor": "pigeonpea",
    "masoor": "lentil", "masur": "lentil", "lentil": "lentil",
    "mung": "moong", "moong": "moong",
    "urad": "black gram",
    "sarson": "mustard", "rai": "mustard", "mustard": "mustard",
    "mungfali": "groundnut", "moongphali": "groundnut", "groundnut": "groundnut",
    "soybean": "soyabean", "soya": "soyabean",
    "til": "sesamum", "sesame": "sesamum",
    "sunflower": "sunflower", "surajmukhi": "sunflower",
    "ganna": "sugarcane", "ganne": "sugarcane", "sugarcane": "sugarcane",
    "kapas": "cotton", "cotton": "cotton",
    "pyaaj": "onion", "pyaz": "onion", "onion": "onion",
    "tamatar": "tomato", "tamaatar": "tomato", "tomato": "tomato",
    "aloo": "potato", "aaloo": "potato", "potato": "potato",
    "lahsun": "garlic", "lasun": "garlic", "garlic": "garlic",
    "adrak": "ginger", "ginger": "ginger",
    "mirch": "chilli", "lal mirch": "chilli", "chilli": "chilli",
    "dhaniya": "coriander", "coriander": "coriander",
}

def normalize_crop(raw: str) -> str:
    return HINGLISH_CROP_MAP.get(raw.lower().strip(), raw.strip())

def score_band(s: float) -> str:
    if s >= 65: return "LOW RISK ✅ — Loan Eligible"
    if s >= 45: return "MEDIUM RISK ⚠️"
    return "HIGH RISK ❌"

def _compute_health_score(predicted_yield, soil_health_score, npk, wdi,
                           irr_ratio, kharif_rain, kharif_temp,
                           rabi_temp, ndvi, crop_type) -> float:
    benchmark = BENCHMARK_YIELDS.get(crop_type, 2000.0)
    yield_sc  = min((predicted_yield / benchmark) * 100, 100) if benchmark > 0 else 50.0
    soil_base = min((soil_health_score / 200) * 100, 100)
    npk_pen   = min((abs(npk - 120) / 120) * 30, 30)
    soil_sc   = max(soil_base - npk_pen, 0)
    wdi_sc    = (1 - wdi) * 100
    irr_sc    = max((1 - abs(1 - irr_ratio)) * 100, 0)
    rain_sc   = min((kharif_rain / 600) * 100, 100)
    water_sc  = 0.5 * wdi_sc + 0.3 * irr_sc + 0.2 * rain_sc
    clim_sc   = max(100 - max(0, kharif_temp - 35) * 5 - max(0, rabi_temp - 25) * 5, 0)
    ndvi_sc   = min(ndvi * 125, 100) if ndvi is not None else min(yield_sc * 0.8, 100)
    return round(yield_sc*0.25 + soil_sc*0.20 + water_sc*0.25 + clim_sc*0.15 + ndvi_sc*0.15, 2)

def _predict_yield(inputs: dict) -> float:
    _xgb_kharif, _xgb_rabi, _kharif_features, _rabi_features, _le_crop, _le_state, _ = get_models()
    try:    crop_enc  = int(_le_crop.transform([inputs["Crop_Type"]])[0])
    except: crop_enc  = 0
    try:    state_enc = int(_le_state.transform([inputs["State_Name"]])[0])
    except: state_enc = 0

    kharif    = _is_kharif(inputs["Crop_Type"])
    mdl       = _xgb_kharif    if kharif else _xgb_rabi
    feat_list = _kharif_features if kharif else _rabi_features

    feat_dict = {
        "year":                            inputs.get("year", 2015),
        "State_Encoded":                   state_enc,
        "Crop_Encoded":                    crop_enc,
        "NPK_Intensity_KgHa":              inputs["NPK_Intensity_KgHa"],
        "Irrigation_Intensity_Ratio":      inputs["Irrigation_Intensity_Ratio"],
        "WDI":                             inputs["WDI"],
        "Kharif_Avg_MaxTemp":              inputs["Kharif_Avg_MaxTemp"],
        "Kharif_Total_Rain":               inputs["Kharif_Total_Rain"],
        "Rabi_Avg_MaxTemp":                inputs["Rabi_Avg_MaxTemp"],
        "District_Soil_Health_Score":      inputs["District_Soil_Health_Score"],
        "NPK_Intensity_KgHa_Lag1":         inputs["NPK_Lag1"],
        "NPK_Intensity_KgHa_Lag2":         inputs["NPK_Lag2"],
        "NPK_Intensity_KgHa_Lag3":         inputs["NPK_Lag3"],
        "Irrigation_Intensity_Ratio_Lag1": inputs["Irr_Lag1"],
        "Irrigation_Intensity_Ratio_Lag2": inputs["Irr_Lag2"],
        "Irrigation_Intensity_Ratio_Lag3": inputs["Irr_Lag3"],
        "WDI_Lag1":                        inputs["WDI_Lag1"],
        "WDI_Lag2":                        inputs["WDI_Lag2"],
        "WDI_Lag3":                        inputs["WDI_Lag3"],
        "Kharif_Avg_MaxTemp_Lag1":         inputs["KTemp_Lag1"],
        "Kharif_Avg_MaxTemp_Lag2":         inputs["KTemp_Lag2"],
        "Kharif_Avg_MaxTemp_Lag3":         inputs["KTemp_Lag3"],
        "Kharif_Total_Rain_Lag1":          inputs["KRain_Lag1"],
        "Kharif_Total_Rain_Lag2":          inputs["KRain_Lag2"],
        "Kharif_Total_Rain_Lag3":          inputs["KRain_Lag3"],
        "Rabi_Avg_MaxTemp_Lag1":           inputs["RTemp_Lag1"],
        "Rabi_Avg_MaxTemp_Lag2":           inputs["RTemp_Lag2"],
        "Rabi_Avg_MaxTemp_Lag3":           inputs["RTemp_Lag3"],
        "Kharif_Avg_MaxTemp_Delta1":  inputs["Kharif_Avg_MaxTemp"] - inputs["KTemp_Lag1"],
        "Kharif_Total_Rain_Delta1":   inputs["Kharif_Total_Rain"]  - inputs["KRain_Lag1"],
        "NPK_Intensity_KgHa_Delta1":  inputs["NPK_Intensity_KgHa"] - inputs["NPK_Lag1"],
        "Kharif_Avg_MaxTemp_Roll3": (inputs["KTemp_Lag1"]+inputs["KTemp_Lag2"]+inputs["KTemp_Lag3"]) / 3.0,
        "Kharif_Total_Rain_Roll3":  (inputs["KRain_Lag1"]+inputs["KRain_Lag2"]+inputs["KRain_Lag3"]) / 3.0,
    }
    feat_df  = pd.DataFrame([feat_dict])[feat_list]
    log_pred = float(mdl.predict(feat_df)[0])
    return float(np.expm1(min(max(log_pred, 0.0), 11.0)))

@tool
async def list_mandis(crop: str, config: RunnableConfig) -> str:
    """Lists APMC mandis in farmer's district for a given crop.
    Crop name can be in Hindi/Hinglish — it will be translated automatically."""
    farmer_id = config.get("configurable", {}).get("farmer_id")
    crop_en = normalize_crop(crop)
    try:
        conn = await asyncpg.connect(DB_URL)
        row  = await conn.fetchrow(
            "SELECT state_name, dist_name FROM farmers WHERE id = $1", farmer_id)
        await conn.close()
    except Exception as e: return f"❌ DB Error: {e}"

    if not row: return "❌ Farmer not found."
    state, district = row["state_name"], row["dist_name"]

    try:
        with open(MANDI_JSON_PATH, "r", encoding="utf-8") as f:
            mandi_data = json.load(f)
    except FileNotFoundError: return "❌ Mandi master JSON not found."

    mandis = []
    for s_key, districts in mandi_data.items():
        if s_key.lower() == state.lower():
            for d_key, m_list in districts.items():
                if d_key.lower() == district.lower():
                    mandis = m_list
                    break

    if not mandis: return f"⚠️ {district} ({state}) ke liye koi mandi data nahi hai."
    mandi_list = "\n".join(f"  {i+1}. {m}" for i, m in enumerate(mandis))
    
    result = f"📍 {district}, {state} ke APMCs ({crop} ke liye):\n{mandi_list}"
    return f"{result}\n\nKaunsi mandi ka bhav chahiye?"

@tool
async def fetch_crop_price(mandi_name: str, crop: str, config: RunnableConfig) -> str:
    """Fetches live price for a crop at a specific APMC mandi."""
    farmer_id = config.get("configurable", {}).get("farmer_id")
    crop_en = normalize_crop(crop)
    try:
        conn = await asyncpg.connect(DB_URL)
        row  = await conn.fetchrow(
            "SELECT state_name FROM farmers WHERE id = $1", farmer_id)
        await conn.close()
    except Exception as e: return f"❌ DB Error: {e}"

    if not row: return "❌ Farmer not found."
    clean_name = mandi_name.replace("APMC", "").strip()
    params = {
        "api-key": os.getenv("AGMARKNET_API_KEY"),
        "format": "json",
        "filters[state]": row["state_name"],
        "filters[market]": clean_name,
        "filters[commodity]": crop_en,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(AGMARKNET_URL, params=params, timeout=15.0)
    records = resp.json().get("records", [])
    if not records:
        return f"⚠️ Aaj {crop_en} ka data {clean_name} mandi mein available nahi hai."
    r = records[0]
    return (f"✅ Live Mandi Price\n"
            f"   Fasal  : {r['commodity']}\n"
            f"   Mandi  : {r['market']}\n"
            f"   Price  : ₹{r['modal_price']} / Quintal\n"
            f"   Date   : {r['arrival_date']}")

@tool
async def get_weather(days: Union[int, str] = 3, farmer_id: Annotated[str, InjectedToolArg] = "", config: RunnableConfig = None) -> str:
    """Fetches weather forecast for farmer's field for the next N days (1-16). days should be a number like 1, 3, or 7."""
    days = int(days)
    # farmer_id is injected by call_tool; fall back to config for safety
    if not farmer_id:
        cfg = _resolve_config(config)
        farmer_id = cfg.get("configurable", {}).get("farmer_id", "")
    try:
        conn = await asyncpg.connect(DB_URL)
        row  = await conn.fetchrow(
            "SELECT field_name, city_name, center_lat, center_lon "
            "FROM farm_fields WHERE farmer_id = $1 LIMIT 1",
            farmer_id)
        await conn.close()
    except Exception as e: return f"❌ DB Error: {e}"

    if not row: return "⚠️ Khet registered nahi hai."
    lat, lon = float(row["center_lat"]), float(row["center_lon"])

    params = {
        "latitude": lat, "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
        "forecast_days": min(days, 16),
        "timezone": "Asia/Kolkata",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(OPEN_METEO_URL, params=params, timeout=15.0)
    daily = resp.json().get("daily", {})
    dates = daily.get("time", [])
    if not dates: return "⚠️ Mausam data nahi mila."

    lines = [f"🌤️ Mausam — {row['field_name']} ({lat:.3f}, {lon:.3f})"]
    for i in range(len(dates)):
        lines.append(
            f"  📅 {dates[i]} | "
            f"Temp: {daily['temperature_2m_min'][i]}°C – {daily['temperature_2m_max'][i]}°C | "
            f"Barish: {daily['precipitation_sum'][i] or 0} mm | "
            f"Hawa: {daily['windspeed_10m_max'][i] or 0} km/h"
        )
    return "\n".join(lines)

@tool
async def get_crop_advice(mode: str = "advice", target_crop: str = "", farmer_id: Annotated[str, InjectedToolArg] = "", config: RunnableConfig = None) -> str:
    """
    mode='score'    → current health score only.
    mode='advice'   → NPK + Irrigation what-if simulation.
    mode='cropswap' → alternative crops from district history.
    mode='compare'  → compare current crop vs target_crop specifically.
                      Requires target_crop e.g. target_crop='RICE YIELD (Kg per ha)'
    """
    start_time = time.perf_counter()
    # farmer_id is injected by call_tool; fall back to config for safety
    if not farmer_id:
        cfg = _resolve_config(config)
        farmer_id = cfg.get("configurable", {}).get("farmer_id", "")

    try:
        conn   = await asyncpg.connect(DB_URL)
        farm   = await conn.fetchrow("""
            SELECT ff.id AS field_id, ff.city_name, ff.state_name,
                   f.state_name AS farmer_state, f.dist_name AS farmer_dist
            FROM farm_fields ff
            JOIN farmers f ON f.id = ff.farmer_id
            WHERE ff.farmer_id = $1
            ORDER BY ff.created_at DESC LIMIT 1
        """, farmer_id)
        if not farm:
            await conn.close()
            return "⚠️ Farm not found."
            
        season = await conn.fetchrow("""
            SELECT crop_type, npk_input, irrigation_ratio, wdi_used,
                   ndvi_value, final_health_score, predicted_yield, year,
                   kharif_temp_used, kharif_rain_used, rabi_temp_used, soil_score_used
            FROM field_predictions
            WHERE field_id = $1
            ORDER BY year DESC LIMIT 1
        """, str(farm["field_id"]))
        
        dist_name = (farm["city_name"] or farm["farmer_dist"] or "").lower().strip()
        
        # Fetch lag history from PostgreSQL instead of CSV
        dist_hist = await conn.fetch("""
            SELECT * FROM district_climate_history
            WHERE LOWER(dist_name) = $1
            ORDER BY year DESC
            LIMIT 5
        """, dist_name)
        
        await conn.close()
    except Exception as e: return f"❌ DB Error: {e}"

    if not season: return "⚠️ Koi prediction data nahi hai. Pehle field prediction karein."
    if len(dist_hist) < 3:
        return f"⚠️ '{dist_name}' ke liye DB mein 3 saal ka data nahi mila."

    lag1, lag2, lag3 = dist_hist[0], dist_hist[1], dist_hist[2]

    requested_year  = int(season["year"] or 2026)
    latest_db_year = int(lag1['year'])
    effective_year  = latest_db_year if requested_year > latest_db_year else requested_year

    def _v(val, fb): return float(val) if val is not None else fb

    crop_type  = season["crop_type"]
    is_kharif  = _is_kharif(crop_type)
    model_used = "Kharif" if is_kharif else "Rabi"

    base = {
        "State_Name":                 farm["state_name"] or farm["farmer_state"],
        "Crop_Type":                  crop_type,
        "year":                       effective_year,
        "NPK_Intensity_KgHa":         _v(season["npk_input"],         lag1['npk_intensity_kgha']),
        "Irrigation_Intensity_Ratio": _v(season["irrigation_ratio"],   lag1['irrigation_intensity_ratio']),
        "WDI":                        _v(season["wdi_used"],           lag1['wdi']),
        "Kharif_Avg_MaxTemp":         _v(season["kharif_temp_used"],   lag1['kharif_avg_maxtemp']),
        "Kharif_Total_Rain":          _v(season["kharif_rain_used"],   lag1['kharif_total_rain']),
        "Rabi_Avg_MaxTemp":           _v(season["rabi_temp_used"],     lag1['rabi_avg_maxtemp']),
        "District_Soil_Health_Score": _v(season["soil_score_used"],    lag1['district_soil_health_score']),
        "ndvi":                       season["ndvi_value"],
        "NPK_Lag1":   lag1['npk_intensity_kgha'],   "NPK_Lag2":   lag2['npk_intensity_kgha'],   "NPK_Lag3":   lag3['npk_intensity_kgha'],
        "Irr_Lag1":   lag1['irrigation_intensity_ratio'], "Irr_Lag2": lag2['irrigation_intensity_ratio'], "Irr_Lag3": lag3['irrigation_intensity_ratio'],
        "WDI_Lag1":   lag1['wdi'],   "WDI_Lag2":   lag2['wdi'],   "WDI_Lag3":   lag3['wdi'],
        "KTemp_Lag1": lag1['kharif_avg_maxtemp'], "KTemp_Lag2": lag2['kharif_avg_maxtemp'], "KTemp_Lag3": lag3['kharif_avg_maxtemp'],
        "KRain_Lag1": lag1['kharif_total_rain'],  "KRain_Lag2": lag2['kharif_total_rain'],  "KRain_Lag3": lag3['kharif_total_rain'],
        "RTemp_Lag1": lag1['rabi_avg_maxtemp'],   "RTemp_Lag2": lag2['rabi_avg_maxtemp'],   "RTemp_Lag3": lag3['rabi_avg_maxtemp'],
    }

    current_yield = _v(season["predicted_yield"], _predict_yield(base))
    current_score = _v(season["final_health_score"],
                       _compute_health_score(current_yield,
                           base["District_Soil_Health_Score"], base["NPK_Intensity_KgHa"],
                           base["WDI"], base["Irrigation_Intensity_Ratio"],
                           base["Kharif_Total_Rain"], base["Kharif_Avg_MaxTemp"],
                           base["Rabi_Avg_MaxTemp"], base["ndvi"], crop_type))
    band = score_band(current_score)

    if mode == "score":
        return (
            f"📊 CURRENT HEALTH SCORE\n"
            f"   Fasal      : {crop_type}\n"
            f"   District   : {dist_name}\n"
            f"   Yield      : {current_yield:.0f} kg/ha\n"
            f"   Score      : {current_score:.1f} / 100\n"
            f"   Risk Band  : {band}\n"
            f"   Data Basis : DB lags {lag1['year']}, {lag2['year']}, {lag3['year']}\n"
            f"   Model Used : {model_used} XGBoost\n"
            + (f"\n✅ Aap loan ke liye eligible hain!" if current_score >= 65
               else f"\n⚠️  Score thoda aur badhana hoga loan eligibility ke liye (target: 65+).")
        )

    # Convert yield column names to the db schema naming convention
    def db_yield_col(c):
        return 'yield_' + c.lower().replace(' ', '_').replace('.', '_').replace('(', '').replace(')', '').replace('_yield', '').replace('_kg_per_ha', '').replace('_kg_per_ha_', '').replace('__', '_').strip('_')

    if mode == "cropswap":
        season_now  = _current_season()
        alt_cols    = KHARIF_ALT_CROPS if season_now == "kharif" else RABI_ALT_CROPS

        lines = [
            f"🔄 ALTERNATIVE CROPS — {dist_name.title()} district | Season: {season_now.upper()}",
            f"   (Based on last 5 years of district DB data)\n"
        ]
        found_any = False
        for col in alt_cols:
            db_col = db_yield_col(col)
            # calculate 5 yr average
            vals = [r[db_col] for r in dist_hist if db_col in r and r[db_col] is not None]
            if len(vals) == 0: continue
            avg  = sum(vals) / len(vals)
            benchmark = BENCHMARK_YIELDS.get(col, 1500.0)
            perf = (avg / benchmark) * 100 if benchmark > 0 else 50
            
            alt_base   = {**base, "Crop_Type": col}
            try:
                alt_yield = _predict_yield(alt_base)
                alt_score = _compute_health_score(
                    alt_yield, base["District_Soil_Health_Score"],
                    base["NPK_Intensity_KgHa"], base["WDI"],
                    base["Irrigation_Intensity_Ratio"], base["Kharif_Total_Rain"],
                    base["Kharif_Avg_MaxTemp"], base["Rabi_Avg_MaxTemp"],
                    base["ndvi"], col)
                lines.append(
                    f"  🌾 {col}\n"
                    f"     District 5yr Avg Yield : {avg:.0f} kg/ha\n"
                    f"     Model Predicted Yield  : {alt_yield:.0f} kg/ha\n"
                    f"     Simulated Score        : {alt_score:.1f}/100 — {score_band(alt_score)}\n"
                    f"     Aapke current NPK ({base['NPK_Intensity_KgHa']:.0f} kg/ha) "
                    f"aur Irrigation ({base['Irrigation_Intensity_Ratio']:.0%}) par yeh fasal "
                    f"{'behtar' if alt_score > current_score else 'similar'} performance degi.\n"
                )
                found_any = True
            except Exception:
                continue

        if not found_any:
            return f"⚠️ {dist_name} ke liye alternate crop simulation nahi ho saki."
        lines.append(f"📌 Current fasal ({crop_type}) ka score: {current_score:.1f}/100 ({band})")
        return "\n".join(lines)

    if mode == "compare":
        if not target_crop:
            return "⚠️ target_crop parameter missing. Please specify which crop to compare."

        target_crop_en = normalize_crop(target_crop)
        matched_col = None
        for col in BENCHMARK_YIELDS.keys():
            if target_crop_en.upper() in col.upper():
                matched_col = col
                break

        if not matched_col:
            return (f"⚠️ '{target_crop}' ({target_crop_en}) ka data DB mein nahi mila.\n"
                    f"   Available crops: {[c for c in BENCHMARK_YIELDS.keys()]}")

        target_base  = {**base, "Crop_Type": matched_col}
        try:
            target_yield = _predict_yield(target_base)
            target_score = _compute_health_score(
                target_yield, base["District_Soil_Health_Score"],
                base["NPK_Intensity_KgHa"], base["WDI"],
                base["Irrigation_Intensity_Ratio"], base["Kharif_Total_Rain"],
                base["Kharif_Avg_MaxTemp"], base["Rabi_Avg_MaxTemp"],
                base["ndvi"], matched_col)
        except Exception as e:
            return f"❌ {matched_col} ke liye simulation fail hui: {e}"

        db_target_col = db_yield_col(matched_col)
        vals_target = [r[db_target_col] for r in dist_hist if db_target_col in r and r[db_target_col] is not None]
        dist_avg_target = sum(vals_target)/len(vals_target) if vals_target else 0

        db_current_col = db_yield_col(crop_type)
        vals_current = [r[db_current_col] for r in dist_hist if db_current_col in r and r[db_current_col] is not None]
        dist_avg_current = sum(vals_current)/len(vals_current) if vals_current else current_yield

        yield_diff  = target_yield - current_yield
        score_diff  = target_score - current_score
        yield_arrow = "📈" if yield_diff > 0 else "📉"
        score_arrow = "⬆️" if score_diff > 0 else "⬇️"

        return "\n".join([
            f"🔄 CROP COMPARISON — {dist_name.title()} District",
            f"   Same NPK ({base['NPK_Intensity_KgHa']:.0f} kg/ha) aur "
            f"Irrigation ({base['Irrigation_Intensity_Ratio']:.0%}) par:\n",

            f"  📌 Current  : {crop_type}",
            f"     Yield    : {current_yield:.0f} kg/ha",
            f"     Score    : {current_score:.1f}/100 — {score_band(current_score)}",
            f"     District 5yr Avg: {dist_avg_current:.0f} kg/ha\n",

            f"  🌾 Switch To: {matched_col}",
            f"     Yield    : {target_yield:.0f} kg/ha  {yield_arrow} ({yield_diff:+.0f} kg/ha)",
            f"     Score    : {target_score:.1f}/100 — {score_band(target_score)}  "
            f"{score_arrow} ({score_diff:+.1f} points)",
            f"     District 5yr Avg: {dist_avg_target:.0f} kg/ha\n",

            f"  📊 Verdict  : "
            + ("Is badlaav se aapka yield aur score DONO behtar honge." if yield_diff > 0 and score_diff > 0
               else "Yield badhega lekin score thoda kam ho sakta hai." if yield_diff > 0
               else "Yeh fasal aapke district mein relatively kam perform karti hai."
                    " Badlaav sochkar karein."),

            "",
            f"  ⚠️  Note: Yeh simulation aapke CURRENT inputs par hai. "
            f"{matched_col.split()[0]} ke liye alag NPK/Irrigation optimal ho sakta hai."
            + ("\n   [CROPSWAP_RECOMMENDED]" if target_score < 65 else "")
        ])

    orig_npk = base["NPK_Intensity_KgHa"]
    orig_irr = base["Irrigation_Intensity_Ratio"]

    best_npk, best_npk_score = None, current_score
    for npk_val in [60, 80, 100, 120, 140, 160]:
        if abs(npk_val - orig_npk) < 5: continue
        m         = {**base, "NPK_Intensity_KgHa": float(npk_val)}
        ny        = _predict_yield(m)
        ns        = _compute_health_score(ny, m["District_Soil_Health_Score"], npk_val,
                        m["WDI"], m["Irrigation_Intensity_Ratio"], m["Kharif_Total_Rain"],
                        m["Kharif_Avg_MaxTemp"], m["Rabi_Avg_MaxTemp"], m["ndvi"], m["Crop_Type"])
        if ns > best_npk_score and (ns - current_score > 0.5):
            best_npk_score = ns
            best_npk = {"npk_val": npk_val, "new_yield": ny, "new_score": ns,
                        "gain": ns - current_score}

    best_irr, best_irr_score = None, current_score
    for irr_val in [0.3, 0.5, 0.7, 0.85, 1.0]:
        if abs(irr_val - orig_irr) < 0.05: continue
        m  = {**base, "Irrigation_Intensity_Ratio": float(irr_val)}
        ny = _predict_yield(m)
        ns = _compute_health_score(ny, m["District_Soil_Health_Score"], m["NPK_Intensity_KgHa"],
                m["WDI"], irr_val, m["Kharif_Total_Rain"],
                m["Kharif_Avg_MaxTemp"], m["Rabi_Avg_MaxTemp"], m["ndvi"], m["Crop_Type"])
        if ns > best_irr_score and (ns - current_score > 0.5):
            best_irr_score = ns
            best_irr = {"irr_val": irr_val, "new_yield": ny, "new_score": ns,
                        "gain": ns - current_score}

    lines = [
        f"📊 CURRENT STATUS  [{model_used} Model]",
        f"   Fasal     : {crop_type}",
        f"   District  : {dist_name}",
        f"   Yield     : {current_yield:.0f} kg/ha",
        f"   Score     : {current_score:.1f} / 100  →  {band}",
        f"   Data Basis: DB lags {lag1['year']}, {lag2['year']}, {lag3['year']}",
        f"   Year Used : {effective_year}"
        + (f"  ⚠️  (requested {requested_year}, snapped to DB max)" if effective_year != requested_year else ""),
        ""
    ]

    if current_score >= 65 and not best_npk and not best_irr:
        lines += [
            "✅ LOAN ELIGIBLE — Aapki fasal pehle se hi kaafi achi hai!",
            f"   Score {current_score:.1f}/100 — Aap abhi loan ke liye eligible hain.",
            "",
            "💡 Koi bhi badlaav zaroori nahi hai. Lekin agar aap aur improve karna",
            "   chahte hain ya doosri fasal try karna chahte hain, toh batayein.",
            "   [CROPSWAP_ELIGIBLE]"
        ]
        return "\n".join(lines)

    if not best_npk and not best_irr:
        lines += [
            "✅ Aapki farming already optimal hai! Koi improvement nahi mila.",
            "   [CROPSWAP_ELIGIBLE]"
        ]
        return "\n".join(lines)

    lines.append("💡 BEST IMPROVEMENT OPTIONS — Aap inme se EK option choose karein:\n")
    option_num = 1

    if best_irr:
        irr_val    = best_irr["irr_val"]
        irr_note   = (
            "Hum jaante hain ki hamesha 100% sinchai possible nahi hoti."
            if irr_val >= 0.85 else
            f"Aapke {dist_name} district ki soil health aur pichle saalon ke data ke hisaab se,"
        )
        irr_impact = (
            f"agar aap sinchai kam karke {irr_val:.0%} par laayen to bhi yield badh sakti hai."
            if irr_val < orig_irr else
            f"agar aap poore khet mein sinchai {irr_val:.0%} tak rakh saken to yield behtar hogi."
        )
        lines += [
            f"  Option {option_num}: Sinchai (Irrigation) Badlaav",
            f"   {irr_note} {irr_impact}",
            f"   → Irrigation: {orig_irr:.0%}  →  {irr_val:.0%}",
            f"   → Nayi Yield : {best_irr['new_yield']:.0f} kg/ha",
            f"   → Naya Score : {best_irr['new_score']:.1f}/100  →  {score_band(best_irr['new_score'])}",
            f"   → Gain       : +{best_irr['gain']:.1f} score points",
            ""
        ]
        option_num += 1

    if best_npk:
        npk_val    = best_npk["npk_val"]
        npk_reason = (
            "Zyada chemical khad mitti ki sehat ko nuksan pahuncha raha hai."
            if npk_val < orig_npk else
            "Sahi poshan milne se paudhe zyada healthy honge aur yield badhegi."
        )
        lines += [
            f"  Option {option_num}: Fertilizer (NPK) Badlaav",
            f"   Aapke district ke pichle data ke hisaab se yeh NPK level zyada effective hai.",
            f"   → NPK      : {orig_npk:.0f}  →  {npk_val} kg/ha",
            f"   → Reason   : {npk_reason}",
            f"   → Nayi Yield: {best_npk['new_yield']:.0f} kg/ha",
            f"   → Naya Score: {best_npk['new_score']:.1f}/100  →  {score_band(best_npk['new_score'])}",
            f"   → Gain      : +{best_npk['gain']:.1f} score points",
            ""
        ]

    if current_score < 65:
        lines += [
            "⚠️  [MEDIUM_HIGH_RISK] — Aapka score abhi bhi loan threshold (65) se neeche hai.",
            "   District history mein kuch aur faslein better perform karti hain.",
            "   [CROPSWAP_RECOMMENDED]"
        ]

    return "\n".join(lines)
