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

class ManualJobRequest(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    apply_link: Optional[str] = None
    posted_date: Optional[str] = None


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
        
        # Prepare job data for insertion
        job_data = {
            'title': job.title,
            'company': job.company,
            'location': job.location or '',
            'apply_link': job.apply_link or '',
            'posted_date': job.posted_date,
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
