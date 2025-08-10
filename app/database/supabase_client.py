"""
PostgreSQL database client for job management using Supabase PostgreSQL connection
"""
import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from sqlalchemy import create_engine, text
from app.core.config import settings

logger = logging.getLogger(__name__)

class PostgreSQLClient:
    """PostgreSQL client for managing job data via Supabase PostgreSQL connection"""
    
    def __init__(self):
        self.engine = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize PostgreSQL client"""
        try:
            # Read database URL from environment variable
            database_url = os.getenv('SUPABASE_URL') or settings.SUPABASE_URL
            
            if not database_url or database_url == "":
                logger.warning("SUPABASE_URL not set in environment variables")
                return
            
            # Create synchronous engine exactly as in the example
            self.engine = create_engine(database_url)
            
            logger.info("PostgreSQL client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL client: {e}")
            self.engine = None
    
    def ensure_jobs_table_exists(self):
        """
        Check if jobs table exists, create it if it doesn't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping table creation.")
                return False
                
            logger.info("Checking if jobs table exists...")
            
            # Create the table using CREATE TABLE IF NOT EXISTS
            create_table_query = """
            CREATE TABLE IF NOT EXISTS jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                apply_link TEXT,
                posted_date DATE,
                source TEXT DEFAULT 'gemini_api',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(title, company, posted_date)
            );
            
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
            CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date);
            CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
            """
            
            with self.engine.connect() as conn:
                conn.execute(text(create_table_query))
                conn.commit()
                
            logger.info("Jobs table created successfully")
            return True
                
        except Exception as e:
            logger.error(f"Error ensuring jobs table exists: {e}")
            return False
    
    def insert_jobs(self, jobs: List[Dict[str, Any]]) -> int:
        """
        Insert jobs into the database, avoiding duplicates
        Returns the number of jobs successfully inserted
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Cannot insert jobs.")
                return 0
                
            if not jobs:
                return 0
            
            logger.info(f"Attempting to insert {len(jobs)} jobs into database")
            
            # Prepare jobs data for insertion
            jobs_to_insert = []
            for job in jobs:
                job_data = {
                    'title': job.get('title', ''),
                    'company': job.get('company', ''),  # Map organization to company
                    'location': job.get('location', ''),
                    'apply_link': job.get('apply_link', ''),
                    'posted_date': self._parse_date(job.get('apply_last_date')),
                    'source': 'gemini_api'
                }
                
                # Only add if we have required fields
                if job_data['title'] and job_data['company']:
                    jobs_to_insert.append(job_data)
            
            if not jobs_to_insert:
                logger.warning("No valid jobs to insert")
                return 0
            
            # Insert jobs using parameterized queries with ON CONFLICT DO NOTHING
            inserted_count = 0
            
            insert_query = """
            INSERT INTO jobs (title, company, location, apply_link, posted_date, source)
            VALUES (:title, :company, :location, :apply_link, :posted_date, :source)
            ON CONFLICT (title, company, posted_date) DO NOTHING
            """
            
            with self.engine.connect() as conn:
                for job_data in jobs_to_insert:
                    try:
                        result = conn.execute(text(insert_query), job_data)
                        if result.rowcount > 0:
                            inserted_count += 1
                    except Exception as e:
                        logger.error(f"Error inserting job {job_data.get('title', 'Unknown')}: {e}")
                        continue
                
                conn.commit()
            
            logger.info(f"Successfully inserted {inserted_count} jobs")
            return inserted_count
            
        except Exception as e:
            logger.error(f"Error inserting jobs: {e}")
            return 0
    
    def get_all_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch all jobs from the database
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Returning empty job list.")
                return []
                
            logger.info(f"Fetching up to {limit} jobs from database")
            
            select_query = """
            SELECT id, title, company, location, apply_link, posted_date, source, created_at
            FROM jobs
            ORDER BY posted_date DESC, created_at DESC
            LIMIT :limit
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(select_query), {'limit': limit})
                rows = result.fetchall()
                
                logger.info(f"Retrieved {len(rows)} jobs from database")
                
                # Convert to the format expected by frontend
                formatted_jobs = []
                for row in rows:
                    formatted_job = {
                        'id': str(row.id),
                        'title': row.title,
                        'organization': row.company,  # Map company back to organization
                        'location': row.location,
                        'apply_link': row.apply_link,
                        'apply_last_date': str(row.posted_date) if row.posted_date else None,
                        'source': row.source,
                        'created_at': str(row.created_at) if row.created_at else None
                    }
                    formatted_jobs.append(formatted_job)
                
                return formatted_jobs
            
        except Exception as e:
            logger.error(f"Error fetching jobs: {e}")
            return []
    
    def get_jobs_count(self) -> int:
        """Get total count of jobs in database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Returning count of 0.")
                return 0
                
            count_query = "SELECT COUNT(*) as count FROM jobs"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(count_query))
                row = result.fetchone()
                return row.count if row else 0
        except Exception as e:
            logger.error(f"Error getting jobs count: {e}")
            return 0
    
    def get_jobs_by_source(self, limit: int = 100, source: str = None) -> List[Dict[str, Any]]:
        """
        Fetch jobs from the database filtered by source
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Returning empty job list.")
                return []
                
            logger.info(f"Fetching up to {limit} jobs from database with source filter: {source}")
            
            select_query = """
            SELECT id, title, company, location, apply_link, posted_date, source, created_at
            FROM jobs
            WHERE source = :source
            ORDER BY posted_date DESC, created_at DESC
            LIMIT :limit
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(select_query), {'source': source, 'limit': limit})
                rows = result.fetchall()
                
                logger.info(f"Retrieved {len(rows)} jobs from database with source filter")
                
                # Convert to the format expected by frontend
                formatted_jobs = []
                for row in rows:
                    formatted_job = {
                        'id': str(row.id),
                        'title': row.title,
                        'organization': row.company,  # Map company back to organization
                        'location': row.location,
                        'apply_link': row.apply_link,
                        'apply_last_date': str(row.posted_date) if row.posted_date else None,
                        'source': row.source,
                        'created_at': str(row.created_at) if row.created_at else None
                    }
                    formatted_jobs.append(formatted_job)
                
                return formatted_jobs
            
        except Exception as e:
            logger.error(f"Error fetching jobs by source: {e}")
            return []
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to YYYY-MM-DD format"""
        if not date_str:
            return None
        
        try:
            # If it's already in YYYY-MM-DD format
            if len(date_str) == 10 and date_str.count('-') == 2:
                datetime.strptime(date_str, '%Y-%m-%d')
                return date_str
            
            # Try other common formats
            for fmt in ['%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d']:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    return parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            logger.warning(f"Could not parse date: {date_str}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {e}")
            return None

    def ensure_users_table_exists(self):
        """
        Check if users table exists, create it if it doesn't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping users table creation.")
                return False
                
            logger.info("Checking if users table exists...")
            
            # Create the users table using CREATE TABLE IF NOT EXISTS
            create_table_query = """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                google_id TEXT UNIQUE,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                picture TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
            CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
            """
            
            with self.engine.connect() as conn:
                conn.execute(text(create_table_query))
                conn.commit()
                
            logger.info("Users table created successfully")
            return True
                
        except Exception as e:
            logger.error(f"Error ensuring users table exists: {e}")
            return False

    def create_or_update_user(self, user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new user or update existing user in the database
        Returns the user data with database ID
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Cannot create/update user.")
                return None
                
            logger.info(f"Creating/updating user: {user_data.get('email')}")
            
            # First, try to find existing user by google_id or email
            select_query = """
            SELECT id, google_id, email, name, picture, is_active, created_at, updated_at
            FROM users 
            WHERE google_id = :google_id OR email = :email
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(select_query), {
                    'google_id': user_data.get('id'),
                    'email': user_data.get('email')
                })
                existing_user = result.fetchone()
                
                if existing_user:
                    # Update existing user
                    update_query = """
                    UPDATE users 
                    SET name = :name, picture = :picture, updated_at = NOW()
                    WHERE id = :user_id
                    RETURNING id, google_id, email, name, picture, is_active, created_at, updated_at
                    """
                    
                    result = conn.execute(text(update_query), {
                        'user_id': existing_user.id,
                        'name': user_data.get('name'),
                        'picture': user_data.get('picture', '')
                    })
                    updated_user = result.fetchone()
                    conn.commit()
                    
                    logger.info(f"Updated existing user: {user_data.get('email')}")
                    
                    return {
                        'id': str(updated_user.id),
                        'google_id': updated_user.google_id,
                        'email': updated_user.email,
                        'name': updated_user.name,
                        'picture': updated_user.picture,
                        'is_active': updated_user.is_active,
                        'created_at': updated_user.created_at.isoformat() if updated_user.created_at else None,
                        'updated_at': updated_user.updated_at.isoformat() if updated_user.updated_at else None
                    }
                else:
                    # Create new user
                    insert_query = """
                    INSERT INTO users (google_id, email, name, picture, is_active)
                    VALUES (:google_id, :email, :name, :picture, :is_active)
                    RETURNING id, google_id, email, name, picture, is_active, created_at, updated_at
                    """
                    
                    result = conn.execute(text(insert_query), {
                        'google_id': user_data.get('id'),
                        'email': user_data.get('email'),
                        'name': user_data.get('name'),
                        'picture': user_data.get('picture', ''),
                        'is_active': user_data.get('is_active', True)
                    })
                    new_user = result.fetchone()
                    conn.commit()
                    
                    logger.info(f"Created new user: {user_data.get('email')}")
                    
                    return {
                        'id': str(new_user.id),
                        'google_id': new_user.google_id,
                        'email': new_user.email,
                        'name': new_user.name,
                        'picture': new_user.picture,
                        'is_active': new_user.is_active,
                        'created_at': new_user.created_at.isoformat() if new_user.created_at else None,
                        'updated_at': new_user.updated_at.isoformat() if new_user.updated_at else None
                    }
                
        except Exception as e:
            logger.error(f"Error creating/updating user: {e}")
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by database ID
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Cannot get user.")
                return None
                
            select_query = """
            SELECT id, google_id, email, name, picture, is_active, created_at, updated_at
            FROM users 
            WHERE id = :user_id
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(select_query), {'user_id': user_id})
                user = result.fetchone()
                
                if user:
                    return {
                        'id': str(user.id),
                        'google_id': user.google_id,
                        'email': user.email,
                        'name': user.name,
                        'picture': user.picture,
                        'is_active': user.is_active,
                        'created_at': user.created_at.isoformat() if user.created_at else None,
                        'updated_at': user.updated_at.isoformat() if user.updated_at else None
                    }
                return None
                
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Cannot get user.")
                return None
                
            select_query = """
            SELECT id, google_id, email, name, picture, is_active, created_at, updated_at
            FROM users 
            WHERE email = :email
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(select_query), {'email': email})
                user = result.fetchone()
                
                if user:
                    return {
                        'id': str(user.id),
                        'google_id': user.google_id,
                        'email': user.email,
                        'name': user.name,
                        'picture': user.picture,
                        'is_active': user.is_active,
                        'created_at': user.created_at.isoformat() if user.created_at else None,
                        'updated_at': user.updated_at.isoformat() if user.updated_at else None
                    }
                return None
                
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            return None

# Global instance
postgresql_client = PostgreSQLClient()
