"""
Job scraper module using Playwright to scrape job listings from Naukri.com
"""
import asyncio
from typing import List, Optional
from playwright.async_api import async_playwright, Page, Browser
from app.schemas.job import Job
import logging

logger = logging.getLogger(__name__)

class JobScraper:
    """Job scraper class for Naukri.com"""
    
    def __init__(self):
        self.base_url = "https://www.naukri.com"
    
    async def scrape_jobs(self, keyword: str, page: int = 1) -> List[Job]:
        """
        Scrape job listings from Naukri.com
        
        Args:
            keyword: Job search keyword
            page: Page number for pagination
            
        Returns:
            List of Job objects scraped from the website
        """
        jobs = []
        browser = None
        
        try:
            async with async_playwright() as p:
                logger.info(f"Starting Playwright for keyword: {keyword}, page: {page}")
                
                # Launch headless Chromium browser
                browser = await p.chromium.launch(headless=True)
                page_obj = await browser.new_page()
                
                # Set user agent to avoid blocking
                await page_obj.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })
                
                try:
                    # Construct search URL
                    search_url = f"{self.base_url}/{keyword}-jobs-{page}"
                    logger.info(f"Navigating to: {search_url}")
                    
                    # Navigate to the search URL with longer timeout
                    response = await page_obj.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    logger.info(f"Page loaded with status: {response.status}")
                    
                    # Wait a bit for dynamic content
                    await page_obj.wait_for_timeout(3000)
                    
                    # Check if we can find job cards
                    job_cards = await page_obj.query_selector_all("article.jobTuple")
                    logger.info(f"Found {len(job_cards)} job cards with selector 'article.jobTuple'")
                    
                    # If no job cards found, try alternative selectors
                    if len(job_cards) == 0:
                        logger.warning("No job cards found with primary selector, trying alternatives...")
                        
                        # Try alternative selectors
                        alternative_selectors = [
                            ".jobTuple",
                            "[data-job-id]",
                            ".srp-jobtuple-wrapper",
                            ".job-tuple"
                        ]
                        
                        for selector in alternative_selectors:
                            job_cards = await page_obj.query_selector_all(selector)
                            logger.info(f"Trying selector '{selector}': found {len(job_cards)} cards")
                            if len(job_cards) > 0:
                                break
                    
                    # If still no cards, log page content for debugging
                    if len(job_cards) == 0:
                        page_title = await page_obj.title()
                        page_url = page_obj.url
                        logger.error(f"No job cards found. Page title: '{page_title}', URL: '{page_url}'")
                        
                        # Take a screenshot for debugging (optional)
                        # await page_obj.screenshot(path=f"debug_screenshot_{keyword}_{page}.png")
                        
                        # Return empty list instead of raising error
                        return jobs
                    
                    # Extract job data from cards
                    for index, card in enumerate(job_cards):
                        try:
                            job_data = await self._extract_job_data(card, index + 1)
                            if job_data:
                                jobs.append(job_data)
                        except Exception as e:
                            logger.warning(f"Failed to extract job data from card {index + 1}: {str(e)}")
                            continue
                    
                except Exception as e:
                    logger.error(f"Error during page navigation or scraping: {str(e)}")
                    raise
                finally:
                    if browser:
                        await browser.close()
                        
        except Exception as e:
            logger.error(f"Failed to scrape jobs - outer exception: {str(e)}")
            # Log the full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
        
        logger.info(f"Successfully scraped {len(jobs)} jobs")
        return jobs
    
    async def _extract_job_data(self, card, job_id: int) -> Optional[Job]:
        """
        Extract job data from a single job card
        
        Args:
            card: Playwright element representing a job card
            job_id: Unique identifier for the job
            
        Returns:
            Job object with extracted data or None if extraction fails
        """
        try:
            # Extract title and apply URL
            title_element = await card.query_selector("a.title")
            title = await title_element.inner_text() if title_element else "Not specified"
            apply_url = await title_element.get_attribute("href") if title_element else ""
            
            # Make apply URL absolute if it's relative
            if apply_url and apply_url.startswith("/"):
                apply_url = f"{self.base_url}{apply_url}"
            
            # Extract company name
            company_element = await card.query_selector("a.subTitle")
            company = await company_element.inner_text() if company_element else "Not specified"
            
            # Extract location
            location_element = await card.query_selector("li.location span")
            location = await location_element.inner_text() if location_element else "Not specified"
            
            # Extract posted date
            date_element = await card.query_selector("span.date")
            posted_date = await date_element.inner_text() if date_element else "Not specified"
            
            # Extract job description (if available)
            desc_element = await card.query_selector(".job-description")
            description = await desc_element.inner_text() if desc_element else f"Job opportunity for {title} at {company}"
            
            # Create Job object
            job = Job(
                id=job_id,
                title=title.strip(),
                company=company.strip(),
                location=location.strip(),
                description=description.strip()[:500],  # Limit description length
                requirements=[title.strip()],  # Use title as a basic requirement
                salary_range=None,  # Naukri doesn't always show salary
                is_active=True,
                apply_url=apply_url,
                posted_date=posted_date.strip()
            )
            
            return job
            
        except Exception as e:
            logger.warning(f"Failed to extract job data: {str(e)}")
            return None

# Global scraper instance
scraper = JobScraper()

async def scrape_jobs(keyword: str, page: int = 1) -> List[Job]:
    """
    Main function to scrape jobs - used by the API endpoint
    
    Args:
        keyword: Job search keyword
        page: Page number for pagination
        
    Returns:
        List of Job objects
    """
    return await scraper.scrape_jobs(keyword, page)
