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
            """
            
            with self.engine.connect() as conn:
                conn.execute(text(create_table_query))
                conn.commit()
                
            logger.info("Jobs table created successfully")
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

# Global instance
postgresql_client = PostgreSQLClient()
