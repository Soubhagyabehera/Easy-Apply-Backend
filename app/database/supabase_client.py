"""
PostgreSQL database client for job management using Supabase PostgreSQL connection
"""
import logging
import os
import json
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
                job_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                apply_link TEXT,
                posted_date DATE,
                vacancies INTEGER,
                fee DECIMAL(10,2),
                job_description TEXT,
                eligibility_criteria JSONB,
                required_documents TEXT[],
                application_deadline DATE,
                contract_or_permanent TEXT CHECK (contract_or_permanent IN ('contract', 'permanent')),
                job_type TEXT CHECK (job_type IN ('central', 'state', 'psu')),
                source TEXT DEFAULT 'manual',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
            CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date);
            CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
            CREATE INDEX IF NOT EXISTS idx_jobs_vacancies ON jobs(vacancies);
            CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
            CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_eligibility ON jobs USING GIN(eligibility_criteria);
            CREATE INDEX IF NOT EXISTS idx_jobs_application_deadline ON jobs(application_deadline);
            CREATE INDEX IF NOT EXISTS idx_jobs_contract_or_permanent ON jobs(contract_or_permanent);
            CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);
            """
            
            with self.engine.connect() as conn:
                conn.execute(text(create_table_query))
                conn.commit()
                
                # Add missing columns if they don't exist (migration)
                migration_queries = [
                    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_deadline DATE;",
                    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS contract_or_permanent TEXT CHECK (contract_or_permanent IN ('contract', 'permanent'));",
                    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_type TEXT CHECK (job_type IN ('central', 'state', 'psu'));"
                ]
                
                for query in migration_queries:
                    try:
                        conn.execute(text(query))
                    except Exception as e:
                        logger.warning(f"Migration query failed (might already exist): {e}")
                
                conn.commit()
                
            logger.info("Jobs table created/updated successfully")
            return True
                
        except Exception as e:
            logger.error(f"Error ensuring jobs table exists: {e}")
            return False
    
    def _generate_job_id(self, title: str, company: str, posted_date: str) -> str:
        """
        Generate composite primary key: jobname_company_dateofposting
        """
        # Clean and format the components
        clean_title = ''.join(c for c in title if c.isalnum() or c in ' -_').strip().replace(' ', '_')
        clean_company = ''.join(c for c in company if c.isalnum() or c in ' -_').strip().replace(' ', '_')
        clean_date = posted_date.replace('-', '') if posted_date else 'unknown'
        
        return f"{clean_title}_{clean_company}_{clean_date}".lower()
    
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
                posted_date_str = self._parse_date(job.get('posted_date') or job.get('apply_last_date'))
                
                # Properly serialize complex data types for PostgreSQL
                eligibility_criteria = job.get('eligibility_criteria', {})
                required_documents = job.get('required_documents', [])
                
                # Parse application deadline
                application_deadline_str = self._parse_date(job.get('application_deadline'))
                
                job_data = {
                    'job_id': self._generate_job_id(
                        job.get('title', ''),
                        job.get('company', '') or job.get('organization', ''),
                        posted_date_str or ''
                    ),
                    'title': job.get('title', ''),
                    'company': job.get('company', '') or job.get('organization', ''),
                    'location': job.get('location', ''),
                    'apply_link': job.get('apply_link', ''),
                    'posted_date': posted_date_str,
                    'vacancies': job.get('vacancies'),
                    'fee': job.get('fee'),
                    'job_description': job.get('job_description', ''),
                    'eligibility_criteria': json.dumps(eligibility_criteria) if eligibility_criteria else '{}',
                    'required_documents': required_documents if isinstance(required_documents, list) else [],
                    'application_deadline': application_deadline_str,
                    'contract_or_permanent': job.get('contract_or_permanent'),
                    'job_type': job.get('job_type'),
                    'source': job.get('source', 'manual')
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
            INSERT INTO jobs (job_id, title, company, location, apply_link, posted_date, 
                            vacancies, fee, job_description, eligibility_criteria, 
                            required_documents, application_deadline, contract_or_permanent, 
                            job_type, source)
            VALUES (:job_id, :title, :company, :location, :apply_link, :posted_date,
                   :vacancies, :fee, :job_description, :eligibility_criteria,
                   :required_documents, :application_deadline, :contract_or_permanent,
                   :job_type, :source)
            ON CONFLICT (job_id) DO NOTHING
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
            SELECT id, job_id, title, company, location, apply_link, posted_date, vacancies, fee, 
                   job_description, eligibility_criteria, required_documents, source, created_at
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
            SELECT id, job_id, title, company, location, apply_link, posted_date, vacancies, fee, 
                   job_description, eligibility_criteria, required_documents, application_deadline,
                   contract_or_permanent, job_type, source, created_at
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
                    # Properly deserialize JSON data from database
                    eligibility_criteria = {}
                    if row.eligibility_criteria:
                        try:
                            if isinstance(row.eligibility_criteria, str):
                                eligibility_criteria = json.loads(row.eligibility_criteria)
                            else:
                                eligibility_criteria = row.eligibility_criteria
                        except (json.JSONDecodeError, TypeError):
                            eligibility_criteria = {}
                    
                    formatted_job = {
                        'id': str(row.id),  # UUID for backward compatibility
                        'job_id': row.job_id,  # Composite key
                        'title': row.title,
                        'company': row.company,
                        'organization': row.company,  # Map company to organization for backward compatibility
                        'location': row.location,
                        'apply_link': row.apply_link,
                        'posted_date': str(row.posted_date) if row.posted_date else None,
                        'apply_last_date': str(row.posted_date) if row.posted_date else None,  # Backward compatibility
                        'vacancies': row.vacancies,
                        'fee': float(row.fee) if row.fee else None,
                        'job_description': row.job_description,
                        'eligibility_criteria': eligibility_criteria,
                        'required_documents': list(row.required_documents) if row.required_documents else [],
                        'source': row.source,
                        'created_at': str(row.created_at) if row.created_at else None
                    }
                    formatted_jobs.append(formatted_job)
                
                return formatted_jobs
            
        except Exception as e:
            logger.error(f"Error fetching jobs by source: {e}")
            return []
    
    def get_all_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch all jobs from the database without source filtering
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Returning empty job list.")
                return []
                
            logger.info(f"Fetching up to {limit} jobs from database")
            
            select_query = """
            SELECT id, job_id, title, company, location, apply_link, posted_date, vacancies, fee, 
                   job_description, eligibility_criteria, required_documents, source, created_at
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
                    # Properly deserialize JSON data from database
                    eligibility_criteria = {}
                    if row.eligibility_criteria:
                        try:
                            if isinstance(row.eligibility_criteria, str):
                                eligibility_criteria = json.loads(row.eligibility_criteria)
                            else:
                                eligibility_criteria = row.eligibility_criteria
                        except (json.JSONDecodeError, TypeError):
                            eligibility_criteria = {}
                    
                    formatted_job = {
                        'id': str(row.id),  # UUID for backward compatibility
                        'job_id': row.job_id,  # Composite key
                        'title': row.title,
                        'company': row.company,
                        'organization': row.company,  # Map company to organization for backward compatibility
                        'location': row.location,
                        'apply_link': row.apply_link,
                        'posted_date': str(row.posted_date) if row.posted_date else None,
                        'apply_last_date': str(row.posted_date) if row.posted_date else None,  # Backward compatibility
                        'vacancies': row.vacancies,
                        'fee': float(row.fee) if row.fee else None,
                        'job_description': row.job_description,
                        'eligibility_criteria': eligibility_criteria,
                        'required_documents': list(row.required_documents) if row.required_documents else [],
                        'source': row.source,
                        'created_at': str(row.created_at) if row.created_at else None
                    }
                    formatted_jobs.append(formatted_job)
                
                return formatted_jobs
            
        except Exception as e:
            logger.error(f"Error fetching all jobs: {e}")
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

    def get_job_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific job by its job_id
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Cannot get job.")
                return None
                
            select_query = """
            SELECT job_id, title, company, location, apply_link, posted_date, vacancies, fee, 
                   job_description, eligibility_criteria, required_documents, source, created_at, updated_at
            FROM jobs 
            WHERE job_id = :job_id
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(select_query), {'job_id': job_id})
                row = result.fetchone()
                
                if row:
                    # Properly deserialize JSON data from database
                    eligibility_criteria = {}
                    if row.eligibility_criteria:
                        try:
                            if isinstance(row.eligibility_criteria, str):
                                eligibility_criteria = json.loads(row.eligibility_criteria)
                            else:
                                eligibility_criteria = row.eligibility_criteria
                        except (json.JSONDecodeError, TypeError):
                            eligibility_criteria = {}
                    
                    return {
                        'job_id': row.job_id,
                        'title': row.title,
                        'company': row.company,
                        'organization': row.company,  # Backward compatibility
                        'location': row.location,
                        'apply_link': row.apply_link,
                        'posted_date': str(row.posted_date) if row.posted_date else None,
                        'apply_last_date': str(row.posted_date) if row.posted_date else None,  # Backward compatibility
                        'vacancies': row.vacancies,
                        'fee': float(row.fee) if row.fee else None,
                        'job_description': row.job_description,
                        'eligibility_criteria': eligibility_criteria,
                        'required_documents': list(row.required_documents) if row.required_documents else [],
                        'source': row.source,
                        'created_at': str(row.created_at) if row.created_at else None,
                        'updated_at': str(row.updated_at) if row.updated_at else None
                    }
                return None
                
        except Exception as e:
            logger.error(f"Error getting job by ID: {e}")
            return None

    def update_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """
        Update a job by its job_id
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Cannot update job.")
                return False
                
            # Build dynamic update query based on provided fields
            update_fields = []
            params = {'job_id': job_id}
            
            for field in ['title', 'company', 'location', 'apply_link', 'posted_date', 
                         'vacancies', 'fee', 'job_description', 'eligibility_criteria', 
                         'required_documents', 'source']:
                if field in job_data:
                    update_fields.append(f"{field} = :{field}")
                    # Serialize complex data types for PostgreSQL
                    if field == 'eligibility_criteria':
                        params[field] = json.dumps(job_data[field]) if job_data[field] else '{}'
                    elif field == 'required_documents':
                        params[field] = job_data[field] if isinstance(job_data[field], list) else []
                    else:
                        params[field] = job_data[field]
            
            if not update_fields:
                logger.warning("No fields to update")
                return False
            
            # Add updated_at timestamp
            update_fields.append("updated_at = NOW()")
            
            update_query = f"""
            UPDATE jobs 
            SET {', '.join(update_fields)}
            WHERE job_id = :job_id
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(update_query), params)
                conn.commit()
                
                if result.rowcount > 0:
                    logger.info(f"Successfully updated job {job_id}")
                    return True
                else:
                    logger.warning(f"No job found with ID {job_id}")
                    return False
                
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
            return False

    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job by its job_id
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Cannot delete job.")
                return False
                
            delete_query = "DELETE FROM jobs WHERE job_id = :job_id"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(delete_query), {'job_id': job_id})
                conn.commit()
                
                if result.rowcount > 0:
                    logger.info(f"Successfully deleted job {job_id}")
                    return True
                else:
                    logger.warning(f"No job found with ID {job_id}")
                    return False
                
        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {e}")
            return False

    def get_jobs_with_filters(self, limit: int = 100, **filters) -> List[Dict[str, Any]]:
        """
        Fetch jobs with advanced filtering options
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Returning empty job list.")
                return []
                
            # Build dynamic WHERE clause based on filters
            where_conditions = []
            params = {'limit': limit}
            
            # Handle different filter types
            if filters.get('location'):
                where_conditions.append("location ILIKE :location")
                params['location'] = f"%{filters['location']}%"
            
            if filters.get('company'):
                where_conditions.append("company ILIKE :company")
                params['company'] = f"%{filters['company']}%"
            
            if filters.get('source'):
                where_conditions.append("source = :source")
                params['source'] = filters['source']
            
            if filters.get('min_vacancies'):
                where_conditions.append("vacancies >= :min_vacancies")
                params['min_vacancies'] = filters['min_vacancies']
            
            if filters.get('max_fee'):
                where_conditions.append("(fee IS NULL OR fee <= :max_fee)")
                params['max_fee'] = filters['max_fee']
            
            if filters.get('posted_after'):
                where_conditions.append("posted_date >= :posted_after")
                params['posted_after'] = filters['posted_after']
            
            if filters.get('search_term'):
                where_conditions.append("(title ILIKE :search_term OR job_description ILIKE :search_term)")
                params['search_term'] = f"%{filters['search_term']}%"
            
            # Build the complete query
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            select_query = f"""
            SELECT job_id, title, company, location, apply_link, posted_date, vacancies, fee, 
                   job_description, eligibility_criteria, required_documents, source, created_at
            FROM jobs
            WHERE {where_clause}
            ORDER BY posted_date DESC, created_at DESC
            LIMIT :limit
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(select_query), params)
                rows = result.fetchall()
                
                logger.info(f"Retrieved {len(rows)} jobs with filters: {filters}")
                
                # Convert to the format expected by frontend
                formatted_jobs = []
                for row in rows:
                    # Properly deserialize JSON data from database
                    eligibility_criteria = {}
                    if row.eligibility_criteria:
                        try:
                            if isinstance(row.eligibility_criteria, str):
                                eligibility_criteria = json.loads(row.eligibility_criteria)
                            else:
                                eligibility_criteria = row.eligibility_criteria
                        except (json.JSONDecodeError, TypeError):
                            eligibility_criteria = {}
                    
                    formatted_job = {
                        'job_id': row.job_id,
                        'title': row.title,
                        'company': row.company,
                        'organization': row.company,  # Backward compatibility
                        'location': row.location,
                        'apply_link': row.apply_link,
                        'posted_date': str(row.posted_date) if row.posted_date else None,
                        'apply_last_date': str(row.posted_date) if row.posted_date else None,  # Backward compatibility
                        'vacancies': row.vacancies,
                        'fee': float(row.fee) if row.fee else None,
                        'job_description': row.job_description,
                        'eligibility_criteria': eligibility_criteria,
                        'required_documents': list(row.required_documents) if row.required_documents else [],
                        'source': row.source,
                        'created_at': str(row.created_at) if row.created_at else None
                    }
                    formatted_jobs.append(formatted_job)
                
                return formatted_jobs
            
        except Exception as e:
            logger.error(f"Error fetching jobs with filters: {e}")
            return []

    def ensure_photo_editor_tables_exist(self):
        """
        Check if photo editor tables exist, create them if they don't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping photo editor table creation.")
                return False
                
            logger.info("Checking if photo editor tables exist...")
            
            # Photo Processing History Table
            create_history_table_sql = """
            CREATE TABLE IF NOT EXISTS photo_processing_history (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                -- Original file information
                original_filename TEXT NOT NULL,
                original_size_bytes INTEGER NOT NULL,
                original_width INTEGER NOT NULL,
                original_height INTEGER NOT NULL,
                original_format TEXT NOT NULL,
                
                -- Processing parameters
                target_width INTEGER NOT NULL,
                target_height INTEGER NOT NULL,
                output_format TEXT NOT NULL CHECK (output_format IN ('JPG', 'PNG', 'PDF')),
                background_color TEXT,
                maintain_aspect_ratio BOOLEAN DEFAULT FALSE,
                max_file_size_kb INTEGER,
                
                -- Output file information
                processed_filename TEXT NOT NULL,
                processed_size_bytes INTEGER NOT NULL,
                processed_width INTEGER NOT NULL,
                processed_height INTEGER NOT NULL,
                compression_ratio DECIMAL(5,2),
                
                -- Processing metadata
                processing_time_ms INTEGER,
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                
                -- File storage information
                file_id TEXT UNIQUE NOT NULL,
                storage_path TEXT,
                thumbnail_path TEXT,
                download_count INTEGER DEFAULT 0,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE,
                last_accessed TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Photo Processing Batches Table
            create_batches_table_sql = """
            CREATE TABLE IF NOT EXISTS photo_processing_batches (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                batch_id TEXT UNIQUE NOT NULL,
                total_files INTEGER NOT NULL,
                successful_files INTEGER DEFAULT 0,
                failed_files INTEGER DEFAULT 0,
                
                -- Processing parameters (same for all files in batch)
                target_width INTEGER NOT NULL,
                target_height INTEGER NOT NULL,
                output_format TEXT NOT NULL CHECK (output_format IN ('JPG', 'PNG', 'PDF')),
                background_color TEXT,
                maintain_aspect_ratio BOOLEAN DEFAULT FALSE,
                max_file_size_kb INTEGER,
                
                -- Batch metadata
                total_processing_time_ms INTEGER,
                zip_file_path TEXT,
                zip_file_size_bytes INTEGER,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE,
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Photo Editor Settings Table
            create_settings_table_sql = """
            CREATE TABLE IF NOT EXISTS photo_editor_settings (
                id SERIAL PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                
                -- Default processing preferences
                default_width INTEGER DEFAULT 200,
                default_height INTEGER DEFAULT 200,
                default_output_format TEXT DEFAULT 'JPG' CHECK (default_output_format IN ('JPG', 'PNG', 'PDF')),
                default_background_color TEXT DEFAULT '#ffffff',
                default_maintain_aspect_ratio BOOLEAN DEFAULT FALSE,
                default_max_file_size_kb INTEGER,
                
                -- User preferences
                auto_optimize_size BOOLEAN DEFAULT TRUE,
                preferred_quality INTEGER DEFAULT 95 CHECK (preferred_quality BETWEEN 1 AND 100),
                save_processing_history BOOLEAN DEFAULT TRUE,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
            
            # Create indexes
            create_indexes_sql = [
                "CREATE INDEX IF NOT EXISTS idx_photo_history_user_id ON photo_processing_history(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_photo_history_session_id ON photo_processing_history(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_photo_history_file_id ON photo_processing_history(file_id);",
                "CREATE INDEX IF NOT EXISTS idx_photo_history_created_at ON photo_processing_history(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_photo_batches_user_id ON photo_processing_batches(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_photo_batches_session_id ON photo_processing_batches(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_photo_batches_batch_id ON photo_processing_batches(batch_id);",
                "CREATE INDEX IF NOT EXISTS idx_photo_batches_created_at ON photo_processing_batches(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_photo_settings_user_id ON photo_editor_settings(user_id);"
            ]
            
            with self.engine.connect() as connection:
                # Create tables
                connection.execute(text(create_history_table_sql))
                connection.execute(text(create_batches_table_sql))
                connection.execute(text(create_settings_table_sql))
                
                # Create indexes
                for index_sql in create_indexes_sql:
                    connection.execute(text(index_sql))
                
                connection.commit()
                
            logger.info("Photo editor tables created/verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create photo editor tables: {e}")
            return False
    
    def save_photo_processing_history(self, processing_data: Dict[str, Any]) -> Optional[str]:
        """Save photo processing history to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO photo_processing_history (
                user_id, session_id, original_filename, original_size_bytes,
                original_width, original_height, original_format, target_width,
                target_height, output_format, background_color, maintain_aspect_ratio,
                max_file_size_kb, processed_filename, processed_size_bytes,
                processed_width, processed_height, compression_ratio, processing_time_ms,
                success, error_message, file_id, storage_path, thumbnail_path
            ) VALUES (
                :user_id, :session_id, :original_filename, :original_size_bytes,
                :original_width, :original_height, :original_format, :target_width,
                :target_height, :output_format, :background_color, :maintain_aspect_ratio,
                :max_file_size_kb, :processed_filename, :processed_size_bytes,
                :processed_width, :processed_height, :compression_ratio, :processing_time_ms,
                :success, :error_message, :file_id, :storage_path, :thumbnail_path
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), processing_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Photo processing history saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save photo processing history: {e}")
            return None
    
    def save_photo_processing_batch(self, batch_data: Dict[str, Any]) -> Optional[str]:
        """Save photo processing batch to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO photo_processing_batches (
                user_id, session_id, batch_id, total_files, successful_files,
                failed_files, target_width, target_height, output_format,
                background_color, maintain_aspect_ratio, max_file_size_kb,
                total_processing_time_ms, zip_file_path, zip_file_size_bytes
            ) VALUES (
                :user_id, :session_id, :batch_id, :total_files, :successful_files,
                :failed_files, :target_width, :target_height, :output_format,
                :background_color, :maintain_aspect_ratio, :max_file_size_kb,
                :total_processing_time_ms, :zip_file_path, :zip_file_size_bytes
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), batch_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Photo processing batch saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save photo processing batch: {e}")
            return None
    
    def ensure_pdf_tools_tables_exist(self):
        """
        Check if PDF tools tables exist, create them if they don't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping PDF tools table creation.")
                return False
                
            logger.info("Checking if PDF tools tables exist...")
            
            # PDF Processing History Table
            create_pdf_history_table_sql = """
            CREATE TABLE IF NOT EXISTS pdf_processing_history (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                -- Operation details
                operation_type TEXT NOT NULL CHECK (operation_type IN ('merge', 'split', 'compress', 'extract', 'convert')),
                input_files INTEGER NOT NULL,
                total_input_size BIGINT NOT NULL,
                output_size BIGINT,
                total_pages INTEGER,
                compression_ratio DECIMAL(5,2),
                compression_level TEXT,
                
                -- Processing metadata
                processing_time_ms INTEGER,
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                
                -- File storage information
                file_id TEXT UNIQUE NOT NULL,
                storage_path TEXT,
                original_filenames TEXT[],
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """
            
            # PDF Batch Processing Table
            create_pdf_batch_table_sql = """
            CREATE TABLE IF NOT EXISTS pdf_batch_processing (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                batch_id TEXT UNIQUE NOT NULL,
                operation_type TEXT NOT NULL,
                input_files INTEGER NOT NULL,
                output_files INTEGER NOT NULL,
                total_input_size BIGINT NOT NULL,
                total_output_size BIGINT,
                total_pages INTEGER,
                
                -- Processing metadata
                processing_time_ms INTEGER,
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                original_filename TEXT,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE,
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Create indexes
            create_pdf_indexes_sql = [
                "CREATE INDEX IF NOT EXISTS idx_pdf_history_user_id ON pdf_processing_history(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_history_session_id ON pdf_processing_history(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_history_file_id ON pdf_processing_history(file_id);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_history_operation ON pdf_processing_history(operation_type);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_history_created_at ON pdf_processing_history(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_batch_user_id ON pdf_batch_processing(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_batch_session_id ON pdf_batch_processing(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_batch_batch_id ON pdf_batch_processing(batch_id);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_batch_operation ON pdf_batch_processing(operation_type);",
                "CREATE INDEX IF NOT EXISTS idx_pdf_batch_created_at ON pdf_batch_processing(created_at);"
            ]
            
            with self.engine.connect() as connection:
                # Create tables
                connection.execute(text(create_pdf_history_table_sql))
                connection.execute(text(create_pdf_batch_table_sql))
                
                # Create indexes
                for index_sql in create_pdf_indexes_sql:
                    connection.execute(text(index_sql))
                
                connection.commit()
                
            logger.info("PDF tools tables created/verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create PDF tools tables: {e}")
            return False
    
    def save_pdf_processing_history(self, processing_data: Dict[str, Any]) -> Optional[str]:
        """Save PDF processing history to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO pdf_processing_history (
                user_id, session_id, operation_type, input_files, total_input_size,
                output_size, total_pages, compression_ratio, compression_level,
                processing_time_ms, success, error_message, file_id, storage_path,
                original_filenames
            ) VALUES (
                :user_id, :session_id, :operation_type, :input_files, :total_input_size,
                :output_size, :total_pages, :compression_ratio, :compression_level,
                :processing_time_ms, :success, :error_message, :file_id, :storage_path,
                :original_filenames
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), processing_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"PDF processing history saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save PDF processing history: {e}")
            return None
    
    def save_pdf_batch_processing(self, batch_data: Dict[str, Any]) -> Optional[str]:
        """Save PDF batch processing to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO pdf_batch_processing (
                user_id, session_id, batch_id, operation_type, input_files,
                output_files, total_input_size, total_output_size, total_pages,
                processing_time_ms, success, error_message, original_filename
            ) VALUES (
                :user_id, :session_id, :batch_id, :operation_type, :input_files,
                :output_files, :total_input_size, :total_output_size, :total_pages,
                :processing_time_ms, :success, :error_message, :original_filename
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), batch_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"PDF batch processing saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save PDF batch processing: {e}")
            return None
    
    def ensure_signature_tables_exist(self):
        """
        Check if signature creator tables exist, create them if they don't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping signature tables creation.")
                return False
                
            logger.info("Checking if signature creator tables exist...")
            
            # Signature Data Table
            create_signature_table_sql = """
            CREATE TABLE IF NOT EXISTS signature_data (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                -- Signature details
                signature_id TEXT UNIQUE NOT NULL,
                signature_type TEXT NOT NULL CHECK (signature_type IN ('text', 'drawn', 'uploaded')),
                signature_text TEXT,
                original_filename TEXT,
                
                -- Style settings
                font_style TEXT,
                font_size INTEGER,
                signature_size TEXT CHECK (signature_size IN ('small', 'medium', 'large')),
                color TEXT,
                background_transparent BOOLEAN DEFAULT TRUE,
                
                -- File information
                file_size BIGINT NOT NULL,
                processing_time_ms INTEGER,
                storage_path TEXT NOT NULL,
                thumbnail_path TEXT,
                
                -- Status
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Create indexes
            create_signature_indexes_sql = [
                "CREATE INDEX IF NOT EXISTS idx_signature_user_id ON signature_data(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_signature_session_id ON signature_data(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_signature_signature_id ON signature_data(signature_id);",
                "CREATE INDEX IF NOT EXISTS idx_signature_type ON signature_data(signature_type);",
                "CREATE INDEX IF NOT EXISTS idx_signature_created_at ON signature_data(created_at);"
            ]
            
            with self.engine.connect() as connection:
                # Create table
                connection.execute(text(create_signature_table_sql))
                
                # Create indexes
                for index_sql in create_signature_indexes_sql:
                    connection.execute(text(index_sql))
                
                connection.commit()
                
            logger.info("Signature creator tables created/verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create signature creator tables: {e}")
            return False
    
    def save_signature_data(self, signature_data: Dict[str, Any]) -> Optional[str]:
        """Save signature data to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO signature_data (
                user_id, session_id, signature_id, signature_type, signature_text,
                original_filename, font_style, font_size, signature_size, color,
                background_transparent, file_size, processing_time_ms, storage_path,
                thumbnail_path, success, error_message
            ) VALUES (
                :user_id, :session_id, :signature_id, :signature_type, :signature_text,
                :original_filename, :font_style, :font_size, :signature_size, :color,
                :background_transparent, :file_size, :processing_time_ms, :storage_path,
                :thumbnail_path, :success, :error_message
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), signature_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Signature data saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save signature data: {e}")
            return None
    
    def ensure_scanner_tables_exist(self):
        """
        Check if document scanner tables exist, create them if they don't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping scanner tables creation.")
                return False
                
            logger.info("Checking if document scanner tables exist...")
            
            # Document Scanner Data Table
            create_scanner_table_sql = """
            CREATE TABLE IF NOT EXISTS document_scanner_data (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                -- Scan details
                scan_id TEXT UNIQUE NOT NULL,
                input_files INTEGER NOT NULL,
                output_format TEXT NOT NULL CHECK (output_format IN ('PDF', 'PNG', 'JPG')),
                enhancement_level TEXT CHECK (enhancement_level IN ('light', 'medium', 'high')),
                auto_crop BOOLEAN DEFAULT TRUE,
                page_size TEXT CHECK (page_size IN ('A4', 'Letter')),
                
                -- File information
                total_input_size BIGINT NOT NULL,
                output_size BIGINT NOT NULL,
                processing_time_ms INTEGER,
                storage_path TEXT NOT NULL,
                original_filenames TEXT[],
                
                -- Status
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Create indexes
            create_scanner_indexes_sql = [
                "CREATE INDEX IF NOT EXISTS idx_scanner_user_id ON document_scanner_data(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_scanner_session_id ON document_scanner_data(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_scanner_scan_id ON document_scanner_data(scan_id);",
                "CREATE INDEX IF NOT EXISTS idx_scanner_output_format ON document_scanner_data(output_format);",
                "CREATE INDEX IF NOT EXISTS idx_scanner_created_at ON document_scanner_data(created_at);"
            ]
            
            with self.engine.connect() as connection:
                # Create table
                connection.execute(text(create_scanner_table_sql))
                
                # Create indexes
                for index_sql in create_scanner_indexes_sql:
                    connection.execute(text(index_sql))
                
                connection.commit()
                
            logger.info("Document scanner tables created/verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create document scanner tables: {e}")
            return False
    
    def save_scan_data(self, scan_data: Dict[str, Any]) -> Optional[str]:
        """Save document scan data to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO document_scanner_data (
                user_id, session_id, scan_id, input_files, output_format,
                enhancement_level, auto_crop, page_size, total_input_size,
                output_size, processing_time_ms, storage_path, original_filenames,
                success, error_message
            ) VALUES (
                :user_id, :session_id, :scan_id, :input_files, :output_format,
                :enhancement_level, :auto_crop, :page_size, :total_input_size,
                :output_size, :processing_time_ms, :storage_path, :original_filenames,
                :success, :error_message
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), scan_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Document scan data saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save document scan data: {e}")
            return None
    
    def ensure_converter_tables_exist(self):
        """
        Check if format converter tables exist, create them if they don't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping converter tables creation.")
                return False
                
            logger.info("Checking if format converter tables exist...")
            
            # Format Converter Data Table
            create_converter_table_sql = """
            CREATE TABLE IF NOT EXISTS format_converter_data (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                -- Conversion details
                conversion_id TEXT UNIQUE NOT NULL,
                conversion_type TEXT NOT NULL CHECK (conversion_type IN ('pdf_to_images', 'images_to_pdf', 'document_format')),
                input_format TEXT NOT NULL,
                output_format TEXT NOT NULL,
                input_files INTEGER NOT NULL,
                output_files INTEGER NOT NULL,
                
                -- File information
                total_input_size BIGINT NOT NULL,
                total_output_size BIGINT NOT NULL,
                processing_time_ms INTEGER,
                original_filename TEXT,
                original_filenames TEXT[],
                
                -- Conversion settings
                dpi INTEGER,
                quality INTEGER,
                page_size TEXT,
                
                -- Status
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Create indexes
            create_converter_indexes_sql = [
                "CREATE INDEX IF NOT EXISTS idx_converter_user_id ON format_converter_data(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_converter_session_id ON format_converter_data(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_converter_conversion_id ON format_converter_data(conversion_id);",
                "CREATE INDEX IF NOT EXISTS idx_converter_type ON format_converter_data(conversion_type);",
                "CREATE INDEX IF NOT EXISTS idx_converter_input_format ON format_converter_data(input_format);",
                "CREATE INDEX IF NOT EXISTS idx_converter_output_format ON format_converter_data(output_format);",
                "CREATE INDEX IF NOT EXISTS idx_converter_created_at ON format_converter_data(created_at);"
            ]
            
            with self.engine.connect() as connection:
                # Create table
                connection.execute(text(create_converter_table_sql))
                
                # Create indexes
                for index_sql in create_converter_indexes_sql:
                    connection.execute(text(index_sql))
                
                connection.commit()
                
            logger.info("Format converter tables created/verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create format converter tables: {e}")
            return False
    
    def save_conversion_data(self, conversion_data: Dict[str, Any]) -> Optional[str]:
        """Save format conversion data to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO format_converter_data (
                user_id, session_id, conversion_id, conversion_type, input_format,
                output_format, input_files, output_files, total_input_size,
                total_output_size, processing_time_ms, original_filename,
                original_filenames, dpi, quality, page_size, success, error_message
            ) VALUES (
                :user_id, :session_id, :conversion_id, :conversion_type, :input_format,
                :output_format, :input_files, :output_files, :total_input_size,
                :total_output_size, :processing_time_ms, :original_filename,
                :original_filenames, :dpi, :quality, :page_size, :success, :error_message
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), conversion_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Format conversion data saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save format conversion data: {e}")
            return None
    
    def ensure_optimizer_tables_exist(self):
        """
        Check if size optimizer tables exist, create them if they don't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping optimizer tables creation.")
                return False
                
            logger.info("Checking if size optimizer tables exist...")
            
            # Size Optimizer Data Table
            create_optimizer_table_sql = """
            CREATE TABLE IF NOT EXISTS size_optimizer_data (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                
                -- Optimization details
                optimization_id TEXT UNIQUE NOT NULL,
                file_type TEXT NOT NULL CHECK (file_type IN ('image', 'pdf')),
                original_format TEXT NOT NULL,
                output_format TEXT NOT NULL,
                compression_level TEXT CHECK (compression_level IN ('light', 'medium', 'aggressive')),
                
                -- Optimization settings
                target_size_kb INTEGER,
                max_width INTEGER,
                max_height INTEGER,
                remove_metadata BOOLEAN DEFAULT FALSE,
                remove_annotations BOOLEAN DEFAULT FALSE,
                final_quality INTEGER,
                
                -- File information
                original_size BIGINT NOT NULL,
                optimized_size BIGINT NOT NULL,
                compression_ratio DECIMAL(5,2),
                total_pages INTEGER,
                processing_time_ms INTEGER,
                storage_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                
                -- Status
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                
                -- Timestamps
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Create indexes
            create_optimizer_indexes_sql = [
                "CREATE INDEX IF NOT EXISTS idx_optimizer_user_id ON size_optimizer_data(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_optimizer_session_id ON size_optimizer_data(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_optimizer_optimization_id ON size_optimizer_data(optimization_id);",
                "CREATE INDEX IF NOT EXISTS idx_optimizer_file_type ON size_optimizer_data(file_type);",
                "CREATE INDEX IF NOT EXISTS idx_optimizer_compression_level ON size_optimizer_data(compression_level);",
                "CREATE INDEX IF NOT EXISTS idx_optimizer_created_at ON size_optimizer_data(created_at);"
            ]
            
            with self.engine.connect() as connection:
                # Create table
                connection.execute(text(create_optimizer_table_sql))
                
                # Create indexes
                for index_sql in create_optimizer_indexes_sql:
                    connection.execute(text(index_sql))
                
                connection.commit()
                
            logger.info("Size optimizer tables created/verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create size optimizer tables: {e}")
            return False
    
    def save_optimization_data(self, optimization_data: Dict[str, Any]) -> Optional[str]:
        """Save size optimization data to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO size_optimizer_data (
                user_id, session_id, optimization_id, file_type, original_format,
                output_format, compression_level, target_size_kb, max_width,
                max_height, remove_metadata, remove_annotations, final_quality,
                original_size, optimized_size, compression_ratio, total_pages,
                processing_time_ms, storage_path, original_filename, success, error_message
            ) VALUES (
                :user_id, :session_id, :optimization_id, :file_type, :original_format,
                :output_format, :compression_level, :target_size_kb, :max_width,
                :max_height, :remove_metadata, :remove_annotations, :final_quality,
                :original_size, :optimized_size, :compression_ratio, :total_pages,
                :processing_time_ms, :storage_path, :original_filename, :success, :error_message
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), optimization_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Size optimization data saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save size optimization data: {e}")
            return None
    
    def ensure_document_manager_tables_exist(self):
        """
        Check if document manager tables exist, create them if they don't
        """
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized. Skipping document manager tables creation.")
                return False
                
            logger.info("Checking if document manager tables exist...")
            
            # Document Types Reference Table
            create_document_types_table_sql = """
            CREATE TABLE IF NOT EXISTS document_types (
                id SERIAL PRIMARY KEY,
                type_code VARCHAR(50) UNIQUE NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                category VARCHAR(30) NOT NULL,
                is_required BOOLEAN DEFAULT FALSE,
                description TEXT,
                accepted_formats TEXT[], -- ['pdf', 'jpg', 'png']
                max_size_mb INTEGER DEFAULT 10,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
            
            # User Documents Table
            create_user_documents_table_sql = """
            CREATE TABLE IF NOT EXISTS user_documents (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id UUID NOT NULL,
                document_type VARCHAR(50) NOT NULL,
                document_category VARCHAR(30) NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                file_format VARCHAR(10) NOT NULL,
                upload_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                is_active BOOLEAN DEFAULT TRUE,
                metadata JSONB DEFAULT '{}',
                
                -- Ensure one active document per type per user
                UNIQUE(user_id, document_type) DEFERRABLE INITIALLY DEFERRED
            );
            """
            
            # Job Document Requirements Table
            create_job_requirements_table_sql = """
            CREATE TABLE IF NOT EXISTS job_document_requirements (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                job_id VARCHAR(100) NOT NULL,
                document_type VARCHAR(50) NOT NULL,
                is_required BOOLEAN DEFAULT TRUE,
                required_format VARCHAR(10),
                max_size_kb INTEGER,
                min_width_px INTEGER,
                min_height_px INTEGER,
                max_width_px INTEGER,
                max_height_px INTEGER,
                naming_convention VARCHAR(255),
                special_requirements JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
            
            # Document Processing History Table
            create_processing_history_table_sql = """
            CREATE TABLE IF NOT EXISTS document_processing_history (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id UUID NOT NULL,
                job_id VARCHAR(100) NOT NULL,
                original_document_id UUID NOT NULL,
                processed_file_path TEXT NOT NULL,
                processing_type VARCHAR(50) NOT NULL,
                processing_parameters JSONB DEFAULT '{}',
                processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                download_count INTEGER DEFAULT 0,
                last_downloaded TIMESTAMP WITH TIME ZONE
            );
            """
            
            # Insert default document types
            insert_document_types_sql = """
            INSERT INTO document_types (type_code, display_name, category, is_required, description, accepted_formats, max_size_mb) VALUES
            -- Personal Documents
            ('resume', 'Resume/Bio-data', 'personal', TRUE, 'Current resume or bio-data', ARRAY['pdf', 'doc', 'docx'], 5),
            ('photo', 'Passport Size Photograph', 'personal', TRUE, 'Recent passport size photograph', ARRAY['jpg', 'jpeg', 'png'], 2),
            ('signature', 'Signature', 'personal', TRUE, 'Digital signature', ARRAY['jpg', 'jpeg', 'png', 'pdf'], 1),
            
            -- Educational Certificates
            ('certificate_10th', '10th Class Certificate', 'educational', TRUE, '10th standard/SSC certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            ('certificate_12th', '12th Class Certificate', 'educational', TRUE, '12th standard/HSC certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            ('certificate_graduation', 'Graduation Certificate', 'educational', TRUE, 'Bachelor degree certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            ('certificate_post_graduation', 'Post-Graduation Certificate', 'educational', FALSE, 'Master degree certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            
            -- Identity Documents
            ('aadhaar', 'Aadhaar Card', 'identity', TRUE, 'Aadhaar card copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 3),
            ('pan', 'PAN Card', 'identity', TRUE, 'PAN card copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 2),
            ('voter_id', 'Voter ID Card', 'identity', FALSE, 'Voter ID card copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 2),
            ('passport', 'Passport', 'identity', FALSE, 'Passport copy', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            
            -- Certificates
            ('caste_certificate', 'Caste Certificate', 'other', FALSE, 'Caste/category certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            ('domicile_certificate', 'Domicile Certificate', 'other', FALSE, 'Domicile/residence certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            ('income_certificate', 'Income Certificate', 'other', FALSE, 'Income certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            ('disability_certificate', 'Disability Certificate', 'other', FALSE, 'Disability certificate (if applicable)', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            
            -- Experience Documents
            ('experience_certificate', 'Experience Certificate', 'experience', FALSE, 'Work experience certificate', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5),
            ('relieving_letter', 'Relieving Letter', 'experience', FALSE, 'Relieving letter from previous employer', ARRAY['pdf', 'jpg', 'jpeg', 'png'], 5)
            
            ON CONFLICT (type_code) DO NOTHING;
            """
            
            # Create indexes
            create_document_manager_indexes_sql = [
                "CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_user_documents_type ON user_documents(document_type);",
                "CREATE INDEX IF NOT EXISTS idx_user_documents_active ON user_documents(user_id, is_active);",
                "CREATE INDEX IF NOT EXISTS idx_job_requirements_job_id ON job_document_requirements(job_id);",
                "CREATE INDEX IF NOT EXISTS idx_processing_history_user_job ON document_processing_history(user_id, job_id);",
                "CREATE INDEX IF NOT EXISTS idx_document_types_category ON document_types(category);",
                "CREATE INDEX IF NOT EXISTS idx_document_types_type_code ON document_types(type_code);"
            ]
            
            with self.engine.connect() as connection:
                # Create tables
                connection.execute(text(create_document_types_table_sql))
                connection.execute(text(create_user_documents_table_sql))
                connection.execute(text(create_job_requirements_table_sql))
                connection.execute(text(create_processing_history_table_sql))
                
                # Insert default document types
                connection.execute(text(insert_document_types_sql))
                
                # Create indexes
                for index_sql in create_document_manager_indexes_sql:
                    connection.execute(text(index_sql))
                
                connection.commit()
                
            logger.info("Document manager tables created/verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create document manager tables: {e}")
            return False
    
    def save_document_upload(self, document_data: Dict[str, Any]) -> Optional[str]:
        """Save document upload to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO user_documents (
                user_id, document_type, document_category, original_filename,
                file_path, file_size_bytes, file_format, metadata
            ) VALUES (
                :user_id, :document_type, :document_category, :original_filename,
                :file_path, :file_size_bytes, :file_format, :metadata
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), document_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Document upload saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save document upload: {e}")
            return None
    
    def save_document_processing_history(self, processing_data: Dict[str, Any]) -> Optional[str]:
        """Save document processing history to database"""
        try:
            if self.engine is None:
                logger.warning("PostgreSQL client not initialized")
                return None
            
            insert_sql = """
            INSERT INTO document_processing_history (
                user_id, job_id, original_document_id, processed_file_path,
                processing_type, processing_parameters
            ) VALUES (
                :user_id, :job_id, :original_document_id, :processed_file_path,
                :processing_type, :processing_parameters
            ) RETURNING id;
            """
            
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_sql), processing_data)
                connection.commit()
                record_id = result.fetchone()[0]
                logger.info(f"Document processing history saved with ID: {record_id}")
                return str(record_id)
                
        except Exception as e:
            logger.error(f"Failed to save document processing history: {e}")
            return None

# Global instance
postgresql_client = PostgreSQLClient()
