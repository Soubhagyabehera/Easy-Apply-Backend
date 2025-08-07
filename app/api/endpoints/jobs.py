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
    Get government jobs - currently returning mock data while OpenAI integration is being fixed.
    
    This endpoint returns default government job listings for testing the frontend dashboard.
    Filters are applied if provided.
    """
    try:
        logger.info("Fetching government jobs for frontend dashboard (using mock data)")
        
        # Mock government jobs data
        mock_government_jobs = [
            {
                "id": 1,
                "title": "Assistant Manager - Finance",
                "company": "State Bank of India",
                "organization": "State Bank of India",
                "location": "Mumbai, Delhi, Bangalore",
                "description": "Recruitment for Assistant Manager position in Finance department. Candidates should have experience in banking and finance.",
                "requirements": ["Graduate degree in Finance/Commerce", "2-3 years banking experience", "Knowledge of banking regulations"],
                "salary_range": "₹8-12 LPA",
                "apply_url": "https://sbi.co.in/careers",
                "posted_date": "2024-01-15",
                "last_date": "2024-02-15",
                "career_url": "https://sbi.co.in/careers",
                "job_type": "Government",
                "department": "Banking",
                "experience_required": "2-3 years",
                "is_active": True
            },
            {
                "id": 2,
                "title": "Junior Engineer - Civil",
                "company": "Indian Railways",
                "organization": "Indian Railways",
                "location": "Pan India",
                "description": "Recruitment for Junior Engineer positions in Civil Engineering department across various railway zones.",
                "requirements": ["Diploma/B.Tech in Civil Engineering", "Fresh graduates welcome", "Knowledge of railway construction"],
                "salary_range": "₹5-8 LPA",
                "apply_url": "https://indianrailways.gov.in/recruitment",
                "posted_date": "2024-01-10",
                "last_date": "2024-02-10",
                "career_url": "https://indianrailways.gov.in/recruitment",
                "job_type": "Government",
                "department": "Engineering",
                "experience_required": "0-2 years",
                "is_active": True
            },
            {
                "id": 3,
                "title": "Tax Assistant",
                "company": "Income Tax Department",
                "organization": "Income Tax Department",
                "location": "Delhi, Mumbai, Chennai",
                "description": "Recruitment for Tax Assistant positions in Income Tax Department. Handle tax assessments and taxpayer services.",
                "requirements": ["Graduate degree", "Knowledge of taxation laws", "Computer proficiency"],
                "salary_range": "₹4-7 LPA",
                "apply_url": "https://incometax.gov.in/careers",
                "posted_date": "2024-01-12",
                "last_date": "2024-02-12",
                "career_url": "https://incometax.gov.in/careers",
                "job_type": "Government",
                "department": "Taxation",
                "experience_required": "0-1 years",
                "is_active": True
            },
            {
                "id": 4,
                "title": "Staff Nurse",
                "company": "AIIMS Delhi",
                "organization": "AIIMS Delhi",
                "location": "New Delhi",
                "description": "Recruitment for Staff Nurse positions at All India Institute of Medical Sciences, Delhi.",
                "requirements": ["B.Sc Nursing degree", "Registered Nurse license", "1-2 years experience preferred"],
                "salary_range": "₹6-9 LPA",
                "apply_url": "https://aiims.edu/careers",
                "posted_date": "2024-01-08",
                "last_date": "2024-02-08",
                "career_url": "https://aiims.edu/careers",
                "job_type": "Government",
                "department": "Healthcare",
                "experience_required": "1-2 years",
                "is_active": True
            },
            {
                "id": 5,
                "title": "Forest Guard",
                "company": "Ministry of Environment",
                "organization": "Ministry of Environment",
                "location": "Uttarakhand, Himachal Pradesh",
                "description": "Recruitment for Forest Guard positions to protect and conserve forest resources.",
                "requirements": ["10+2 qualification", "Physical fitness", "Knowledge of local flora and fauna"],
                "salary_range": "₹3-5 LPA",
                "apply_url": "https://moef.gov.in/careers",
                "posted_date": "2024-01-05",
                "last_date": "2024-02-05",
                "career_url": "https://moef.gov.in/careers",
                "job_type": "Government",
                "department": "Environment",
                "experience_required": "0-1 years",
                "is_active": True
            },
            {
                "id": 6,
                "title": "Assistant Professor - Computer Science",
                "company": "IIT Delhi",
                "organization": "IIT Delhi",
                "location": "New Delhi",
                "description": "Faculty recruitment for Assistant Professor position in Computer Science and Engineering department.",
                "requirements": ["PhD in Computer Science", "Research publications", "Teaching experience preferred"],
                "salary_range": "₹15-25 LPA",
                "apply_url": "https://iitd.ac.in/careers",
                "posted_date": "2024-01-20",
                "last_date": "2024-03-20",
                "career_url": "https://iitd.ac.in/careers",
                "job_type": "Government",
                "department": "Education",
                "experience_required": "3-5 years",
                "is_active": True
            }
        ]
        
        # Apply filters if provided
        filtered_jobs = []
        for job in mock_government_jobs:
            # Apply location filter
            if location and location.lower() not in job['location'].lower():
                continue
            # Apply organization filter
            if organization and organization.lower() not in job['organization'].lower():
                continue
            # Apply department filter
            if department and department.lower() not in job['department'].lower():
                continue
            
            filtered_jobs.append(job)
        
        logger.info(f"Returning {len(filtered_jobs)} government jobs for frontend (mock data)")
        return filtered_jobs
        
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
