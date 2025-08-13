from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from app.services.gemini_service import gemini_job_service
from app.database.supabase_client import postgresql_client
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter()










# Pydantic models for request bodies
class JobDiscoveryRequest(BaseModel):
    skills: Optional[List[str]] = None
    location: Optional[str] = "India"
    job_type: Optional[str] = "government"

class EligibilityCriteria(BaseModel):
    education_qualification: Optional[str] = None
    age_limit: Optional[str] = None
    other_requirement: Optional[str] = None

class ManualJobRequest(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    apply_link: Optional[str] = None
    posted_date: Optional[str] = None
    vacancies: Optional[int] = None
    fee: Optional[float] = None
    job_description: Optional[str] = None
    eligibility_criteria: Optional[EligibilityCriteria] = None
    required_documents: Optional[List[str]] = None
    application_deadline: Optional[str] = None
    contract_or_permanent: Optional[str] = None  # 'contract' or 'permanent'
    job_type: Optional[str] = None  # 'central', 'state', or 'psu'

class BulkJobsRequest(BaseModel):
    jobs: List[ManualJobRequest]

class JobUpdateRequest(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    apply_link: Optional[str] = None
    posted_date: Optional[str] = None
    vacancies: Optional[int] = None
    fee: Optional[float] = None
    job_description: Optional[str] = None
    eligibility_criteria: Optional[EligibilityCriteria] = None
    required_documents: Optional[List[str]] = None
    application_deadline: Optional[str] = None
    contract_or_permanent: Optional[str] = None  # 'contract' or 'permanent'
    job_type: Optional[str] = None  # 'central', 'state', or 'psu'


@router.post("/discover")
async def discover_jobs_ai(request: JobDiscoveryRequest = Body(...)):
    """
    AI-based job discovery using Gemini API with customizable parameters.
    
    This endpoint triggers AI-based job discovery for Indian Government, PSU, and State Government jobs.
    Accepts optional parameters to refine search results and prevents duplicates by checking (title, apply_link).
    
    Request body:
    {
        "skills": ["Python", "Django"],   // array of skills (optional)
        "location": "India",              // string (optional, default: "India")
        "job_type": "government"          // string (optional, default: "government")
    }
    """
    try:
        # Check if Gemini API key is available
        logger.info("Starting AI-based job discovery with custom parameters")
        if not os.getenv("GEMINI_API_KEY"):
            return {
                "status": "error",
                "message": "GEMINI_API_KEY environment variable is not set. Please configure your Gemini API key.",
                "count": 0,
                "data": []
            }
        
        # Log the AI query parameters
        logger.info(f"AI query parameters - Skills: {request.skills}, Location: {request.location}, Job Type: {request.job_type}")
        
        # Use the Gemini service to get jobs (existing service will be enhanced to accept parameters)
        jobs = await gemini_job_service.fetch_government_jobs()
        
        if not jobs:
            logger.warning("No jobs received from AI service")
            return {
                "status": "success",
                "message": "No jobs found matching the criteria",
                "count": 0,
                "data": []
            }
        
        logger.info(f"AI discovery completed: {len(jobs)} jobs found")
        
        # Prepare jobs for insertion with AI-specific tagging
        current_time = datetime.now().isoformat()
        jobs_to_insert = []
        
        for job in jobs:
            job_data = {
                'title': job.get('title', ''),
                'company': job.get('organization', ''),
                'location': job.get('location', ''),
                'apply_link': job.get('apply_link', ''),
                'posted_date': job.get('apply_last_date'),
                'source': 'ai'  # Tag with source = "ai"
            }
            
            # Only add if we have required fields
            if job_data['title'] and (job_data['company'] or job_data['apply_link']):
                jobs_to_insert.append(job_data)
        
        if not jobs_to_insert:
            logger.warning("No valid jobs to insert after processing")
            return {
                "status": "success",
                "message": "No valid jobs found to insert",
                "count": 0,
                "data": []
            }
        
        # Use batch insert with duplicate prevention (existing method handles duplicates)
        inserted_count = postgresql_client.insert_jobs(jobs_to_insert)
        
        logger.info(f"AI job discovery result - Found: {len(jobs)}, Inserted: {inserted_count}")
        
        return {
            "status": "success",
            "message": f"AI job discovery completed successfully. {inserted_count} new jobs added.",
            "count": inserted_count,
            "data": jobs_to_insert[:10]  # Return first 10 for preview
        }
        
    except Exception as e:
        logger.error(f"Error in AI job discovery: {e}")
        return {
            "status": "error",
            "message": f"AI job discovery failed: {str(e)}",
            "count": 0,
            "data": []
        }


@router.post("/manual")
def insert_manual_job(job: ManualJobRequest):
    """
    Insert a manually provided job into the jobs table.
    
    This endpoint allows manual insertion of job data with source tagged as "manual".
    All job details come from the request body.
    
    Request body:
    {
        "title": "Software Engineer",
        "company": "Tech Corp",
        "location": "Mumbai",
        "apply_link": "https://example.com/apply",
        "posted_date": "2024-12-31"
    }
    """
    try:
        # DEBUG: Add detailed logging to verify endpoint is being called
        logger.info("=" * 50)
        logger.info("🔧 MANUAL JOB INSERT ENDPOINT CALLED")
        logger.info(f"📝 Job Title: {job.title}")
        logger.info(f"🏢 Company: {job.company}")
        logger.info(f"📍 Location: {job.location}")
        logger.info(f"🔗 Apply Link: {job.apply_link}")
        logger.info(f"📅 Posted Date: {job.posted_date}")
        logger.info("=" * 50)
        
        logger.info(f"Inserting manual job: {job.title} at {job.company}")
        
        # Prepare job data for insertion with all new fields
        job_data = {
            'title': job.title,
            'company': job.company,
            'location': job.location or '',
            'apply_link': job.apply_link or '',
            'posted_date': job.posted_date,
            'vacancies': job.vacancies,
            'fee': job.fee,
            'job_description': job.job_description or '',
            'eligibility_criteria': job.eligibility_criteria.dict() if job.eligibility_criteria else {},
            'required_documents': job.required_documents or [],
            'source': 'manual'  # Tag with source = "manual"
        }
        
        # Insert single job using existing method
        inserted_count = postgresql_client.insert_jobs([job_data])
        
        if inserted_count > 0:
            logger.info(f"Successfully inserted manual job: {job.title}")
            return {
                "status": "success",
                "message": "Job inserted successfully",
                "data": job_data
            }
        else:
            logger.warning(f"Manual job not inserted (possibly duplicate): {job.title}")
            return {
                "status": "success",
                "message": "Job not inserted (possibly duplicate)",
                "data": job_data
            }
            
    except Exception as e:
        logger.error(f"Error inserting manual job: {e}")
        return {
            "status": "error",
            "message": f"Failed to insert job: {str(e)}",
            "data": None
        }


@router.post("/bulk")
def insert_bulk_jobs(bulk_request: BulkJobsRequest):
    """
    Insert multiple jobs at once into the jobs table.
    
    This endpoint allows bulk insertion of job data with source tagged as "manual".
    Accepts a list of jobs in the request body.
    
    Request body:
    {
        "jobs": [
            {
                "title": "Software Engineer",
                "company": "Tech Corp",
                "location": "Mumbai",
                "apply_link": "https://example.com/apply",
                "posted_date": "2024-12-31"
            },
            {
                "title": "Data Analyst",
                "company": "Data Inc",
                "location": "Delhi",
                "apply_link": "https://datainc.com/apply",
                "posted_date": "2024-12-30"
            }
        ]
    }
    """
    try:
        logger.info("=" * 50)
        logger.info("🔧 BULK JOBS INSERT ENDPOINT CALLED")
        logger.info(f"📊 Number of jobs to insert: {len(bulk_request.jobs)}")
        logger.info("=" * 50)
        
        if not bulk_request.jobs:
            return {
                "status": "error",
                "message": "No jobs provided in the request",
                "data": None
            }
        
        # Prepare all jobs data for bulk insertion
        jobs_to_insert = []
        
        for job in bulk_request.jobs:
            logger.info(f"Processing job: {job.title} at {job.company}")
            
            # Prepare job data for insertion with all new fields
            job_data = {
                'title': job.title,
                'company': job.company,
                'location': job.location,
                'apply_link': job.apply_link,
                'posted_date': job.posted_date,
                'vacancies': job.vacancies,
                'fee': job.fee,
                'job_description': job.job_description,
                'eligibility_criteria': job.eligibility_criteria.dict() if job.eligibility_criteria else {},
                'required_documents': job.required_documents or [],
                'application_deadline': job.application_deadline,
                'contract_or_permanent': job.contract_or_permanent,
                'job_type': job.job_type,
                'source': 'manual'  # Tag with source = "manual"
            }
            
            jobs_to_insert.append(job_data)
        
        # Insert all jobs using existing batch method
        inserted_count = postgresql_client.insert_jobs(jobs_to_insert)
        
        logger.info(f"Bulk insert result - Requested: {len(bulk_request.jobs)}, Inserted: {inserted_count}")
        
        return {
            "status": "success",
            "message": f"Bulk job insertion completed. {inserted_count} out of {len(bulk_request.jobs)} jobs inserted successfully.",
            "requested_count": len(bulk_request.jobs),
            "inserted_count": inserted_count,
            "data": jobs_to_insert[:5]  # Return first 5 for preview
        }
        
    except Exception as e:
        logger.error(f"Error in bulk job insertion: {e}")
        return {
            "status": "error",
            "message": f"Failed to insert bulk jobs: {str(e)}",
            "data": None
        }


@router.get("/")
def get_jobs(
    limit: int = Query(50, description="Maximum number of jobs to return"),
    source: Optional[str] = Query(None, description="Filter by job source (ai, manual, gemini_api)")
):
    """
    Fetch jobs from the jobs table for frontend job listings.
    
    This endpoint retrieves jobs with optional filtering and pagination.
    Results are ordered by posted_date descending for most recent jobs first.
    
    Query parameters:
    - limit: Maximum number of jobs to return (default: 50)
    - source: Optional filter by job source (ai, manual, gemini_api)
    
    Returns consistent JSON format:
    {
        "status": "success",
        "count": <number>,
        "data": [ ...job objects... ]
    }
    """
    try:
        logger.info(f"Fetching jobs - Limit: {limit}, Source filter: {source}")
        
        # Get jobs from database using existing helper method with source filtering
        if source:
            jobs = postgresql_client.get_jobs_by_source(limit=limit, source=source)
        else:
            jobs = postgresql_client.get_all_jobs(limit=limit)
        
        logger.info(f"Retrieved {len(jobs)} jobs from database")
        
        return {
            "status": "success",
            "count": len(jobs),
            "data": jobs
        }
        
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        return {
            "status": "error",
            "count": 0,
            "data": [],
            "message": f"Failed to fetch jobs: {str(e)}"
        }


@router.get("/{job_id}")
def get_job_by_id(job_id: str):
    """
    Get a specific job by its job_id
    
    Path parameter:
    - job_id: The unique job identifier (jobname_company_dateofposting format)
    
    Returns job details with all fields including eligibility criteria and required documents.
    """
    try:
        logger.info(f"Fetching job with ID: {job_id}")
        
        job = postgresql_client.get_job_by_id(job_id)
        
        if job:
            logger.info(f"Successfully retrieved job: {job['title']}")
            return {
                "status": "success",
                "data": job
            }
        else:
            logger.warning(f"Job not found with ID: {job_id}")
            return {
                "status": "error",
                "message": f"Job not found with ID: {job_id}",
                "data": None
            }
            
    except Exception as e:
        logger.error(f"Error fetching job {job_id}: {e}")
        return {
            "status": "error",
            "message": f"Failed to fetch job: {str(e)}",
            "data": None
        }


@router.put("/{job_id}")
def update_job(job_id: str, job_update: JobUpdateRequest):
    """
    Update a job by its job_id
    
    Path parameter:
    - job_id: The unique job identifier (jobname_company_dateofposting format)
    
    Request body: JobUpdateRequest with any fields to update
    Only provided fields will be updated, others remain unchanged.
    """
    try:
        logger.info(f"Updating job with ID: {job_id}")
        
        # Convert Pydantic model to dict, excluding None values
        update_data = {}
        for field, value in job_update.dict(exclude_unset=True).items():
            if value is not None:
                if field == 'eligibility_criteria' and isinstance(value, dict):
                    update_data[field] = value
                else:
                    update_data[field] = value
        
        if not update_data:
            return {
                "status": "error",
                "message": "No fields provided for update",
                "data": None
            }
        
        success = postgresql_client.update_job(job_id, update_data)
        
        if success:
            # Fetch updated job to return
            updated_job = postgresql_client.get_job_by_id(job_id)
            logger.info(f"Successfully updated job: {job_id}")
            return {
                "status": "success",
                "message": "Job updated successfully",
                "data": updated_job
            }
        else:
            logger.warning(f"Job not found for update with ID: {job_id}")
            return {
                "status": "error",
                "message": f"Job not found with ID: {job_id}",
                "data": None
            }
            
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        return {
            "status": "error",
            "message": f"Failed to update job: {str(e)}",
            "data": None
        }


@router.delete("/{job_id}")
def delete_job(job_id: str):
    """
    Delete a job by its job_id
    
    Path parameter:
    - job_id: The unique job identifier (jobname_company_dateofposting format)
    
    Permanently removes the job from the database.
    """
    try:
        logger.info(f"Deleting job with ID: {job_id}")
        
        success = postgresql_client.delete_job(job_id)
        
        if success:
            logger.info(f"Successfully deleted job: {job_id}")
            return {
                "status": "success",
                "message": f"Job {job_id} deleted successfully"
            }
        else:
            logger.warning(f"Job not found for deletion with ID: {job_id}")
            return {
                "status": "error",
                "message": f"Job not found with ID: {job_id}"
            }
            
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        return {
            "status": "error",
            "message": f"Failed to delete job: {str(e)}"
        }


@router.get("/search/advanced")
def search_jobs_advanced(
    limit: int = Query(50, description="Maximum number of jobs to return"),
    location: Optional[str] = Query(None, description="Filter by location (partial match)"),
    company: Optional[str] = Query(None, description="Filter by company name (partial match)"),
    source: Optional[str] = Query(None, description="Filter by job source (ai, manual, gemini_api)"),
    min_vacancies: Optional[int] = Query(None, description="Minimum number of vacancies"),
    max_fee: Optional[float] = Query(None, description="Maximum application fee"),
    posted_after: Optional[str] = Query(None, description="Posted after date (YYYY-MM-DD)"),
    search_term: Optional[str] = Query(None, description="Search in title and description")
):
    """
    Advanced job search with multiple filters
    
    Query parameters support various filtering options:
    - location: Partial match on job location
    - company: Partial match on company name
    - source: Exact match on job source
    - min_vacancies: Jobs with at least this many vacancies
    - max_fee: Jobs with application fee less than or equal to this amount
    - posted_after: Jobs posted after this date
    - search_term: Search in job title and description
    
    Returns filtered job results with all job details.
    """
    try:
        logger.info(f"Advanced job search with filters: location={location}, company={company}, "
                   f"source={source}, min_vacancies={min_vacancies}, max_fee={max_fee}, "
                   f"posted_after={posted_after}, search_term={search_term}")
        
        # Prepare filter parameters
        filters = {}
        if location:
            filters['location'] = location
        if company:
            filters['company'] = company
        if source:
            filters['source'] = source
        if min_vacancies is not None:
            filters['min_vacancies'] = min_vacancies
        if max_fee is not None:
            filters['max_fee'] = max_fee
        if posted_after:
            filters['posted_after'] = posted_after
        if search_term:
            filters['search_term'] = search_term
        
        # Get filtered jobs from database
        jobs = postgresql_client.get_jobs_with_filters(limit=limit, **filters)
        
        logger.info(f"Advanced search retrieved {len(jobs)} jobs")
        
        return {
            "status": "success",
            "count": len(jobs),
            "data": jobs,
            "filters_applied": filters
        }
        
    except Exception as e:
        logger.error(f"Error in advanced job search: {e}")
        return {
            "status": "error",
            "count": 0,
            "data": [],
            "message": f"Advanced search failed: {str(e)}"
        }
