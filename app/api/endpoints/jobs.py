from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.schemas.job import Job, JobCreate, JobUpdate
from app.scraper import scrape_jobs
from app.services.job_discovery import job_discovery_service
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter()

# Mock data for fallback (kept for backward compatibility)
mock_jobs = [
    {
        "id": 1,
        "title": "Software Engineer",
        "company": "Tech Corp",
        "location": "San Francisco, CA",
        "description": "Looking for a skilled software engineer...",
        "requirements": ["Python", "FastAPI", "React"],
        "salary_range": "$100k - $150k",
        "apply_url": "https://example.com/apply/1",
        "posted_date": "2 days ago",
        "is_active": True
    },
    {
        "id": 2,
        "title": "Frontend Developer",
        "company": "StartupXYZ",
        "location": "Remote",
        "description": "Join our frontend team...",
        "requirements": ["React", "TypeScript", "Tailwind"],
        "salary_range": "$80k - $120k",
        "apply_url": "https://example.com/apply/2",
        "posted_date": "1 day ago",
        "is_active": True
    }
]

@router.get("/", response_model=List[Job])
async def get_jobs(
    q: Optional[str] = Query(None, description="Job search keyword"),
    page: int = Query(1, ge=1, description="Page number for pagination")
):
    """
    Get jobs - either scraped from Naukri.com or mock data
    
    Args:
        q: Job search keyword (if provided, scrapes from Naukri)
        page: Page number for pagination
    
    Returns:
        List of Job objects
    """
    try:
        # If query parameter is provided, scrape jobs from Naukri
        if q:
            logger.info(f"Scraping jobs for keyword: {q}, page: {page}")
            scraped_jobs = await scrape_jobs(q, page)
            logger.info(f"Successfully scraped {len(scraped_jobs)} jobs")
            return scraped_jobs
        else:
            # Return mock data if no query provided
            logger.info("Returning mock job data")
            return [Job(**job) for job in mock_jobs if job["is_active"]]
            
    except Exception as e:
        logger.error(f"Failed to fetch jobs: {str(e)}")
        # Log the full traceback for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Return 500 error with more detailed information in development
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scrape jobs: {str(e)}"
        )

@router.get("/debug/playwright")
async def debug_playwright():
    """Debug endpoint to test Playwright installation"""
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.google.com")
            title = await page.title()
            await browser.close()
            
        return {
            "status": "success",
            "message": "Playwright is working correctly",
            "test_page_title": title
        }
    except Exception as e:
        logger.error(f"Playwright debug failed: {e}")
        return {
            "status": "error",
            "message": f"Playwright error: {str(e)}"
        }

@router.get("/discover")
async def discover_government_jobs():
    """
    Discover government jobs using OpenAI API and Playwright scraping.
    
    This endpoint:
    1. Uses OpenAI ChatGPT API to get Indian government organizations and PSUs
    2. Scrapes their career pages using Playwright to extract active job postings
    3. Returns aggregated job data with organization info, career URLs, and job details
    
    Requires OPENAI_API_KEY environment variable to be set.
    """
    try:
        # Check if OpenAI API key is available
        if not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY environment variable is not set. Please configure your OpenAI API key."
            )
        
        logger.info("Starting government job discovery process")
        
        # Use the job discovery service to get all jobs
        results = await job_discovery_service.discover_all_jobs()
        
        # Calculate summary statistics
        total_organizations = len(results)
        total_jobs = sum(len(result['jobs']) for result in results)
        organizations_with_jobs = len([r for r in results if r['jobs']])
        
        logger.info(f"Job discovery completed: {total_organizations} orgs, {total_jobs} jobs")
        
        return {
            "status": "success",
            "summary": {
                "total_organizations": total_organizations,
                "organizations_with_jobs": organizations_with_jobs,
                "total_jobs_found": total_jobs
            },
            "data": results
        }
        
    except ValueError as e:
        logger.error(f"Configuration error in job discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in job discovery: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to discover government jobs: {str(e)}"
        )

@router.get("/government", response_model=List[Job])
async def get_government_jobs(
    location: Optional[str] = Query(None, description="Filter by location"),
    organization: Optional[str] = Query(None, description="Filter by organization"),
    department: Optional[str] = Query(None, description="Filter by department")
):
    """
    Get government jobs from OpenAI discovery in frontend-compatible format.
    
    This endpoint:
    1. Calls the job discovery service to get government jobs
    2. Transforms the data into Job schema format for the frontend
    3. Applies filters if provided
    4. Returns jobs ready for dashboard display
    """
    try:
        logger.info("Fetching government jobs for frontend dashboard")
        
        # Get discovered jobs from the service
        discovery_results = await job_discovery_service.discover_all_jobs()
        
        # Transform discovered jobs into Job schema format
        jobs = []
        job_id = 1
        
        for org_result in discovery_results:
            org_name = org_result['organization']
            career_url = org_result['career_url']
            
            for job_data in org_result['jobs']:
                # Create Job object from discovered data
                job = {
                    "id": job_id,
                    "title": job_data['title'],
                    "company": org_name,
                    "organization": org_name,
                    "location": "India",  # Default location
                    "description": f"Government job at {org_name}",
                    "requirements": ["As per official notification"],
                    "salary_range": "As per government norms",
                    "apply_url": job_data['apply_url'],
                    "posted_date": job_data.get('posted_date', 'Recently'),
                    "last_date": job_data.get('last_date', 'Check notification'),
                    "career_url": career_url,
                    "job_type": "Government",
                    "department": org_name,  # Use organization as department
                    "experience_required": "As per notification",
                    "is_active": True
                }
                
                # Apply filters
                if location and location.lower() not in job['location'].lower():
                    continue
                if organization and organization.lower() not in job['organization'].lower():
                    continue
                if department and department.lower() not in job['department'].lower():
                    continue
                
                jobs.append(job)
                job_id += 1
        
        logger.info(f"Returning {len(jobs)} government jobs for frontend")
        return jobs
        
    except Exception as e:
        logger.error(f"Error fetching government jobs for frontend: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch government jobs: {str(e)}"
        )

@router.get("/test-openai")
async def test_openai():
    """
    Test OpenAI API integration to debug job discovery issues
    """
    try:
        logger.info("Testing OpenAI API integration")
        
        # Test OpenAI API directly
        organizations = await job_discovery_service.get_government_organizations()
        
        return {
            "status": "success",
            "message": f"OpenAI API working - got {len(organizations)} organizations",
            "organizations": organizations[:5]  # Show first 5 for testing
        }
        
    except Exception as e:
        logger.error(f"OpenAI test failed: {e}")
        import traceback
        return {
            "status": "error",
            "message": f"OpenAI API error: {str(e)}",
            "traceback": traceback.format_exc()
        }

@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: int):
    """Get a specific job by ID"""
    job = next((job for job in mock_jobs if job["id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/", response_model=Job)
async def create_job(job: JobCreate):
    """Create a new job posting"""
    new_job = {
        "id": len(mock_jobs) + 1,
        **job.dict(),
        "is_active": True
    }
    mock_jobs.append(new_job)
    return new_job

@router.put("/{job_id}", response_model=Job)
async def update_job(job_id: int, job_update: JobUpdate):
    """Update an existing job"""
    job_index = next((i for i, job in enumerate(mock_jobs) if job["id"] == job_id), None)
    if job_index is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    updated_job = {**mock_jobs[job_index], **job_update.dict(exclude_unset=True)}
    mock_jobs[job_index] = updated_job
    return updated_job

@router.delete("/{job_id}")
async def delete_job(job_id: int):
    """Delete a job posting"""
    job_index = next((i for i, job in enumerate(mock_jobs) if job["id"] == job_id), None)
    if job_index is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    mock_jobs.pop(job_index)
    return {"message": "Job deleted successfully"}
