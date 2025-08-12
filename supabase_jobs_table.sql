-- Updated Jobs Table Schema for EasyApply
-- This SQL command creates the jobs table with the new comprehensive fields
-- Primary key: id (UUID) - maintains backward compatibility
-- Unique key: job_id (composite: jobname_company_dateofposting) - new requirement

-- Migration script: Update existing jobs table to new schema
-- First, drop the existing table and recreate with new schema
-- CAUTION: This will delete all existing job data
DROP TABLE IF EXISTS jobs;

CREATE TABLE jobs (
    -- Primary key: UUID for backward compatibility
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Unique composite identifier: jobname_company_dateofposting
    job_id TEXT UNIQUE NOT NULL,
    
    -- Core job information
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    apply_link TEXT,
    posted_date DATE,
    
    -- New comprehensive fields
    vacancies INTEGER,
    fee DECIMAL(10,2),
    job_description TEXT,
    eligibility_criteria JSONB,
    required_documents TEXT[],
    
    -- Additional job details
    application_deadline DATE,
    contract_or_permanent TEXT CHECK (contract_or_permanent IN ('contract', 'permanent')),
    job_type TEXT CHECK (job_type IN ('central', 'state', 'psu')),
    
    -- System fields
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date);
CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_vacancies ON jobs(vacancies);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_eligibility ON jobs USING GIN(eligibility_criteria);
CREATE INDEX IF NOT EXISTS idx_jobs_application_deadline ON jobs(application_deadline);
CREATE INDEX IF NOT EXISTS idx_jobs_contract_or_permanent ON jobs(contract_or_permanent);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);

-- Schema creation complete. 
-- The jobs table now supports:
-- - UUID primary key (id) for backward compatibility
-- - Composite unique key (job_id) for new requirements
-- - All new fields: vacancies, fee, job_description, eligibility_criteria, required_documents
-- - Proper indexes for query performance
