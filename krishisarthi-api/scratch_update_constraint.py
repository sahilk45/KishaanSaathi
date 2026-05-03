import asyncio
import asyncpg
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_migrate")

async def update_constraint():
    dsn = "postgresql://neondb_owner:npg_qrvhmPKE7g8z@ep-lucky-lake-ambn84ss.c-5.us-east-1.aws.neon.tech:5432/neondb?sslmode=require"
    
    logger.info("Connecting to DB...")
    conn = await asyncpg.connect(dsn)
    
    try:
        logger.info("Dropping old constraint...")
        await conn.execute("""
            ALTER TABLE field_predictions 
            DROP CONSTRAINT IF EXISTS field_predictions_field_id_crop_type_year_key;
        """)
        
        logger.info("Adding new 5-column unique constraint...")
        await conn.execute("""
            ALTER TABLE field_predictions 
            ADD CONSTRAINT field_predictions_cache_key 
            UNIQUE (field_id, crop_type, year, npk_input, irrigation_ratio);
        """)
        
        logger.info("Successfully updated constraint.")
    except Exception as e:
        logger.error(f"Failed to update constraint: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(update_constraint())
