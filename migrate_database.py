#!/usr/bin/env python3
"""
Database Migration Script for EasyApply Jobs Table
This script updates the jobs table schema to include the new fields and dual key system.
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text
from app.core.config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the database migration to update jobs table schema"""
    try:
        # Get database URL from environment or settings
        database_url = os.getenv('SUPABASE_URL') or settings.SUPABASE_URL
        
        if not database_url:
            logger.error("SUPABASE_URL not found in environment variables or settings")
            return False
            
        logger.info("Connecting to database...")
        engine = create_engine(database_url)
        
        # Read the SQL migration file
        sql_file_path = os.path.join(os.path.dirname(__file__), 'supabase_jobs_table.sql')
        
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            sql_content = file.read()
            
        logger.info("Executing database migration...")
        
        # Execute the SQL migration
        with engine.begin() as conn:  # Use begin() for auto-commit transaction
            # First, manually drop the existing table
            logger.info("Dropping existing jobs table...")
            try:
                conn.execute(text("DROP TABLE IF EXISTS jobs CASCADE;"))
                logger.info("✅ Existing jobs table dropped")
            except Exception as e:
                logger.warning(f"Could not drop existing table: {e}")
            
            # Split SQL content by semicolons and execute each statement
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
            
            for statement in statements:
                if statement and not statement.startswith('--') and 'DROP TABLE' not in statement:
                    logger.info(f"Executing: {statement[:100]}...")
                    conn.execute(text(statement))
            
        logger.info("✅ Database migration completed successfully!")
        logger.info("Jobs table has been updated with new schema:")
        logger.info("- UUID 'id' primary key")
        logger.info("- Composite 'job_id' unique key") 
        logger.info("- New fields: vacancies, fee, job_description, eligibility_criteria, required_documents")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
