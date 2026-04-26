# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
e2e_agra_test.py - Full end-to-end test for Agra farmer
=========================================================
Makes REAL API calls to your running FastAPI server.
Shows every step: registration → polygon → lag features → NDVI → prediction.

Run:  python e2e_agra_test.py
"""

import httpx
import json
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL    = "http://localhost:8001"
DB_URL      = os.getenv("DATABASE_URL")

# ── Real Agra farm polygon (Soorsa Village, Agra district) ──
# These are real GPS coordinates of an agricultural field near Agra
AGRA_POLYGON = [
    [78.0125, 27.1850],
    [78.0175, 27.1850],
    [78.0175, 27.1900],
    [78.0125, 27.1900],
    [78.0125, 27.1850],   # closed ring
]

DIVIDER = "-" * 65

def p(label, value=""):
    print(f"  {label:<35} {value}")

def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:

        # ══════════════════════════════════════════════════════════════
        # STEP 1 — Register Farmer
        # ══════════════════════════════════════════════════════════════
        section("STEP 1 — POST /farmers/register")
        farmer_payload = {
            "name":       "Ramesh Kumar",
            "phone":      "9876543210",
            "state_name": "Uttar Pradesh",
            "dist_name":  "agra",
        }
        print(f"  Request: {json.dumps(farmer_payload, indent=2)}")

        resp = await client.post("/farmers/register", json=farmer_payload)

        if resp.status_code == 409:
            # Already registered — fetch existing
            print(f"\n  ⚠️  Phone already registered. Fetching existing farmer...")
            conn = await asyncpg.connect(DB_URL)
            row  = await conn.fetchrow("SELECT * FROM farmers WHERE phone = $1", "9876543210")
            await conn.close()
            farmer_id = str(row["id"])
        else:
            resp.raise_for_status()
            data      = resp.json()
            farmer_id = data["farmer_id"]

        print(f"\n  ✅ API Response:")
        p("farmer_id",   farmer_id)
        p("Name",        "Ramesh Kumar")
        p("Phone",       "9876543210")
        p("State",       "Uttar Pradesh")
        p("District",    "agra")

        # ══════════════════════════════════════════════════════════════
        # STEP 2 — Register Farm Field (Real Agra GPS polygon)
        # ══════════════════════════════════════════════════════════════
        section("STEP 2 — POST /farm/register")
        field_payload = {
            "farmer_id":   farmer_id,
            "field_name":  "Soorsa Khet",
            "coordinates": AGRA_POLYGON,
            "area_hectares": 2.5,
        }
        print(f"  Polygon: {len(AGRA_POLYGON)} coordinates around Soorsa Village, Agra")
        print(f"  Center approx: lat=27.1875, lon=78.0150")

        resp = await client.post("/farm/register", json=field_payload)
        resp.raise_for_status()
        farm_data  = resp.json()
        field_id   = farm_data["field_id"]
        polygon_id = farm_data["polygon_id"]

        print(f"\n  ✅ API Response:")
        p("field_id",    field_id)
        p("polygon_id",  polygon_id)
        p("Field Name",  "Soorsa Khet")
        p("Area (ha)",   str(farm_data.get("area")))
        p("center_lat",  str(farm_data.get("center_lat")))
        p("center_lon",  str(farm_data.get("center_lon")))
        p("city_name",   str(farm_data.get("city_name")))
        p("state_name",  str(farm_data.get("state_name")))
        p("source",      farm_data.get("source", "?"))

        # ══════════════════════════════════════════════════════════════
        # STEP 3 — Show Lag Feature Calculation from DB
        # ══════════════════════════════════════════════════════════════
        section("STEP 3 — Lag Feature Calculation (year=2026)")
        print("  target_year = 2026")
        print("  Query: SELECT year FROM district_climate_history")
        print("         WHERE dist_name='agra' AND year < 2026")
        print("         ORDER BY year DESC LIMIT 3")

        conn = await asyncpg.connect(DB_URL)

        lag_years = await conn.fetch(
            """
            SELECT year FROM district_climate_history
            WHERE  dist_name = 'agra' AND year < 2026 AND year IS NOT NULL
            ORDER  BY year DESC LIMIT 3
            """
        )
        lag_year_list = [r["year"] for r in lag_years]
        print(f"\n  ✅ Years found in DB: {lag_year_list}")
        print(f"     Weights applied:    [0.5, 0.3, 0.2]")

        # Show actual values for each feature per year
        features = ["kharif_avg_maxtemp", "kharif_total_rain", "rabi_avg_maxtemp", "wdi", "irrigation_intensity_ratio"]
        print(f"\n  {'Feature':<30} {'yr '+str(lag_year_list[0] if lag_year_list else 'N/A'):<15} {'yr '+str(lag_year_list[1] if len(lag_year_list)>1 else 'N/A'):<15} {'yr '+str(lag_year_list[2] if len(lag_year_list)>2 else 'N/A'):<15} {'Weighted Avg'}")
        print(f"  {DIVIDER}")

        computed_features = {}
        for feat in features:
            vals = []
            for yr in lag_year_list:
                row = await conn.fetchrow(
                    f"SELECT {feat} FROM district_climate_history WHERE dist_name='agra' AND year=$1",
                    yr
                )
                vals.append(float(row[feat]) if row and row[feat] is not None else None)

            weights = [0.5, 0.3, 0.2]
            wsum    = sum(v * w for v, w in zip(vals, weights) if v is not None)
            wtotal  = sum(w for v, w in zip(vals, weights) if v is not None)
            wavg    = wsum / wtotal if wtotal > 0 else None
            computed_features[feat] = wavg

            v0 = f"{vals[0]:.2f}" if len(vals) > 0 and vals[0] is not None else "NULL"
            v1 = f"{vals[1]:.2f}" if len(vals) > 1 and vals[1] is not None else "NULL"
            v2 = f"{vals[2]:.2f}" if len(vals) > 2 and vals[2] is not None else "NULL"
            wa = f"{wavg:.4f}"    if wavg is not None else "NULL"
            print(f"  {feat:<30} {v0:<15} {v1:<15} {v2:<15} {wa}")

        await conn.close()

        # ══════════════════════════════════════════════════════════════
        # STEP 4 — POST /predict (year=2026, real inputs)
        # ══════════════════════════════════════════════════════════════
        section("STEP 4 — POST /predict")
        predict_payload = {
            "field_id":        field_id,
            "crop_type":       "WHEAT.YIELD.Kg.per.ha.",
            "npk_input":       120.0,   # Optimal NPK
            "irrigation_ratio": 0.85,   # 85% irrigated
            "year":            2026,
        }
        print(f"  Request payload:")
        for k, v in predict_payload.items():
            p(str(k), str(v))
        print(f"\n  ⚙️  Note: year=2026 stored in DB but XGBoost uses year=2015 (clamped)")

        resp = await client.post("/predict", json=predict_payload)
        resp.raise_for_status()
        pred = resp.json()

        # ══════════════════════════════════════════════════════════════
        # STEP 5 — Display All Results
        # ══════════════════════════════════════════════════════════════
        section("STEP 5 — COMPLETE RESULTS")

        h = pred.get("health", {})

        print(f"\n  {'─── FARMER & FIELD ───'}")
        p("farmer_id",       farmer_id)
        p("field_id",        field_id)
        p("Name",            "Ramesh Kumar")
        p("Phone",           "9876543210")
        p("State",           "Uttar Pradesh")
        p("District",        "agra")
        p("Field Name",      "Soorsa Khet")
        p("GPS (center)",    f"lat=27.1875, lon=78.0150")
        p("Area (ha)",       "2.5")

        print(f"\n  {'─── PREDICTION INPUTS ───'}")
        p("Crop",            pred.get("crop_type"))
        p("Year (stored)",   str(pred.get("year")) + "  ← user input")
        p("Year (model)",    "2015  ← clamped to training cutoff")
        p("NPK Input",       str(predict_payload["npk_input"]) + " kg/ha")
        p("Irrigation Ratio",str(predict_payload["irrigation_ratio"]) + " (85%)")
        p("irr_source",      pred.get("irr_source"))

        print(f"\n  {'─── LAG FEATURES USED (computed above) ───'}")
        p("Years used",         str(lag_year_list) + " → weights [0.5, 0.3, 0.2]")
        p("kharif_avg_maxtemp", f"{pred.get('kharif_temp_used'):.4f} °C")
        p("kharif_total_rain",  f"{pred.get('kharif_rain_used'):.4f} mm")
        p("rabi_avg_maxtemp",   f"{pred.get('rabi_temp_used'):.4f} °C")
        p("wdi_used",           f"{pred.get('wdi_used'):.4f}")
        p("soil_score_used",    f"{pred.get('soil_score_used'):.4f}")

        print(f"\n  {'─── SATELLITE / NDVI ───'}")
        p("source",           pred.get("satellite_source"))
        p("satellite_date",   str(pred.get("satellite_image_date")))
        p("NDVI mean",        str(pred.get("ndvi_mean")))
        p("NDVI max",         str(pred.get("ndvi_max")))
        p("soil_moisture",    str(pred.get("soil_moisture")))
        p("soil_temp_surf",   str(pred.get("soil_temp_surface")))
        p("air_temp",         str(pred.get("air_temp")))
        p("humidity",         str(pred.get("humidity")))
        p("cloud_cover",      str(pred.get("cloud_cover")))

        print(f"\n  {'─── XGBoost MODEL OUTPUT ───'}")
        p("predicted_yield",  f"{pred.get('predicted_yield'):.2f} kg/ha")
        p("benchmark_yield",  f"{pred.get('benchmark_yield'):.2f} kg/ha  (historical avg)")
        p("cached",           str(pred.get("cached")))
        p("calculated_at",    str(pred.get("calculated_at")))

        print(f"\n  {'─── 5-COMPONENT HEALTH SCORE ───'}")
        p("1. Yield Score  (25%)", f"{h.get('yield_score'):.2f}/100")
        p("2. Soil Score   (20%)", f"{h.get('soil_score'):.2f}/100")
        p("3. Water Score  (25%)", f"{h.get('water_score'):.2f}/100")
        p("4. Climate Score(15%)", f"{h.get('climate_score'):.2f}/100")
        p("5. NDVI Score   (15%)", f"{h.get('ndvi_score'):.2f}/100  [{h.get('ndvi_source','?')}]")
        print(f"  {'─'*50}")
        p("FINAL HEALTH SCORE",  f"► {h.get('final_health_score'):.2f}/100")
        p("RISK LEVEL",          f"► {h.get('risk_level')}")
        p("LOAN DECISION",       f"► {h.get('loan_decision')}")

        print(f"\n{'═'*65}")
        print(f"  ✅ END-TO-END TEST COMPLETE")
        print(f"{'═'*65}\n")

if __name__ == "__main__":
    asyncio.run(main())
