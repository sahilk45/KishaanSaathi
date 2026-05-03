import os
import asyncio
import asyncpg
import json
from datetime import datetime
from uuid import UUID

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

async def main():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    farmer_id = "740e8268-730f-4bf6-bc2d-540e7d3325e5"
    
    conn = await asyncpg.connect(dsn)
    
    try:
        farmer = await conn.fetchrow("SELECT * FROM farmers WHERE id = $1::uuid", farmer_id)
        fields = await conn.fetch("SELECT id, field_name, polygon_id, city_name, state_name, center_lat, center_lon, area_hectares, created_at FROM farm_fields WHERE farmer_id = $1::uuid", farmer_id)
        predictions = await conn.fetch("SELECT field_id, year, crop_type, npk_input, irrigation_ratio, predicted_yield, final_health_score, risk_level, loan_decision, calculated_at FROM field_predictions WHERE farmer_id = $1::uuid", farmer_id)
        threads = await conn.fetch("SELECT thread_id, summary, created_at FROM chat_threads WHERE farmer_id = $1::uuid", farmer_id)
        
        thread_ids = [t['thread_id'] for t in threads]
        messages = []
        if thread_ids:
            query = "SELECT msg_id, thread_id, role, tool_name, created_at, content FROM chat_messages WHERE thread_id = ANY($1::varchar[]) ORDER BY created_at DESC LIMIT 20"
            messages = await conn.fetch(query, thread_ids)
            
        data = {
            "farmer": dict(farmer) if farmer else None,
            "fields": [dict(f) for f in fields],
            "predictions": [dict(p) for p in predictions],
            "threads": [dict(t) for t in threads],
            "messages_sample": [dict(m) for m in messages]
        }
        
        with open('scratch_fetch.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=CustomEncoder, indent=2)
            
    finally:
        await conn.close()

asyncio.run(main())
