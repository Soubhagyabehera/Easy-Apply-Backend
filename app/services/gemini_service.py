"""
Gemini API service for fetching government job listings
"""
import json
import logging
import os
from typing import List, Dict, Any
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)

class GeminiJobService:
    """Service for fetching government jobs using Google Gemini API"""
    
    def __init__(self):
        self.client = None
    
    def _get_gemini_client(self):
        """Get Gemini client with lazy initialization"""
        if self.client is None:
            try:
                if not settings.GEMINI_API_KEY:
                    raise ValueError("GEMINI_API_KEY environment variable is required")
                
                logger.info("Initializing Gemini client...")
                # The client gets the API key from the environment variable `GEMINI_API_KEY`
                self.client = genai.Client()
                logger.info("Gemini client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                raise ValueError(f"Gemini client initialization failed: {e}")
        return self.client
    
    async def fetch_government_jobs(self) -> List[Dict[str, Any]]:
        """
        Use Google Gemini API to get current government job listings
        """
        try:
            prompt = """You are a job search assistant for India. Search the internet for the 50 most recent and currently active job openings in:
- Indian central government departments
- State government jobs
- Public sector undertakings (PSUs)

For each job, return the following details in valid JSON array format:
[
  {
    "title": "Job title",
    "organization": "Recruiting organization name",
    "location": "City/State or 'Multiple'",
    "category": "Central Govt / State Govt / PSU",
    "apply_last_date": "YYYY-MM-DD",
    "apply_link": "Direct application link OR career portal link"
  }
]

Guidelines:
- Ensure the jobs are currently active (application last date has not passed).
- Include a mix of central govt, PSU, and multiple state govt jobs.
- Use only reliable sources like official govt recruitment websites, public sector career pages, or authorized job boards.
- Do not include duplicate or expired jobs.
- Make sure the output is strictly valid JSON — no comments, no extra text."""
            
            logger.info("Calling Gemini API to get government jobs")
            
            client = self._get_gemini_client()
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            content = response.text
            logger.info(f"Gemini API response received: {len(content)} characters")
            
            # Parse JSON response
            try:
                jobs = json.loads(content)
                logger.info(f"Successfully parsed {len(jobs)} jobs from Gemini API")
                return jobs
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini response as JSON: {e}")
                logger.error(f"Raw response: {content[:500]}...")  # Log first 500 chars for debugging
                # Return fallback data if API response is malformed
                return self._get_fallback_jobs()
                
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            # Return fallback list if API fails
            return self._get_fallback_jobs()
    
    def _get_fallback_jobs(self) -> List[Dict[str, Any]]:
        """Fallback list of government jobs if Gemini API fails"""
        return [
            {
                "title": "Assistant Manager - Finance",
                "organization": "State Bank of India",
                "location": "Multiple",
                "category": "PSU",
                "apply_last_date": "2025-09-15",
                "apply_link": "https://sbi.co.in/careers"
            },
            {
                "title": "Junior Engineer - Civil",
                "organization": "Indian Railways",
                "location": "Multiple",
                "category": "Central Govt",
                "apply_last_date": "2025-09-20",
                "apply_link": "https://www.indianrailways.gov.in/"
            },
            {
                "title": "Scientist/Engineer - SC",
                "organization": "ISRO",
                "location": "Bangalore",
                "category": "Central Govt",
                "apply_last_date": "2025-09-25",
                "apply_link": "https://www.isro.gov.in/Careers.html"
            },
            {
                "title": "Management Trainee",
                "organization": "ONGC",
                "location": "Multiple",
                "category": "PSU",
                "apply_last_date": "2025-09-30",
                "apply_link": "https://www.ongcindia.com/careers"
            },
            {
                "title": "Assistant Section Officer",
                "organization": "SSC",
                "location": "Delhi",
                "category": "Central Govt",
                "apply_last_date": "2025-10-05",
                "apply_link": "https://ssc.nic.in/"
            }
        ]

# Global service instance
gemini_job_service = GeminiJobService()
