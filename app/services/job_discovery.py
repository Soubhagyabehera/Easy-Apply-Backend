"""
Job discovery service using OpenAI API and Playwright scraping
"""
import asyncio
import json
import logging
import os
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright
from openai import AsyncOpenAI
import nest_asyncio

# Fix for Windows asyncio issues
nest_asyncio.apply()

logger = logging.getLogger(__name__)

class JobDiscoveryService:
    """Service for discovering government jobs using OpenAI and Playwright"""
    
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or "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"
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        # Use lazy initialization to avoid startup errors
        self.client = None
    
    def _get_openai_client(self):
        """Get OpenAI client with lazy initialization"""
        if self.client is None:
            try:
                logger.info(f"Initializing OpenAI client with API key: {self.openai_api_key[:20]}...")
                self.client = AsyncOpenAI(api_key=self.openai_api_key)
                logger.info("OpenAI client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                logger.error(f"API key length: {len(self.openai_api_key) if self.openai_api_key else 'None'}")
                raise ValueError(f"OpenAI client initialization failed: {e}")
        return self.client
    
    async def get_government_organizations(self) -> List[Dict[str, str]]:
        """
        Use OpenAI ChatGPT API to get list of Indian government organizations and PSUs
        with their career page URLs
        """
        try:
            prompt = """Give me a list of at least 30 Indian government organizations and PSUs along with the direct links to their official career or recruitment pages. Return in JSON format as: [{ 'organization': '', 'career_url': '' }]
            
            Include major organizations like:
            - ISRO, DRDO, BARC
            - SBI, IBPS, RBI
            - Indian Railways, ONGC, NTPC
            - UPSC, SSC, IBPS
            - State government departments
            - PSUs like BHEL, SAIL, Coal India
            - Defense organizations
            - Educational institutions like IITs, IIMs
            
            Make sure the URLs are accurate and point to career/recruitment sections."""
            
            logger.info("Calling OpenAI API to get government organizations")
            
            client = self._get_openai_client()
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a helpful assistant that provides accurate information about Indian government organizations and their career pages. Always return valid JSON format."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            content = response.choices[0].message.content
            logger.info(f"OpenAI API response received: {len(content)} characters")
            
            # Parse JSON response
            try:
                organizations = json.loads(content)
                logger.info(f"Successfully parsed {len(organizations)} organizations")
                return organizations
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI response as JSON: {e}")
                # Fallback to hardcoded list if API response is malformed
                return self._get_fallback_organizations()
                
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            # Return fallback list if API fails
            return self._get_fallback_organizations()
    
    def _get_fallback_organizations(self) -> List[Dict[str, str]]:
        """Fallback list of government organizations if OpenAI API fails"""
        return [
            {"organization": "ISRO", "career_url": "https://www.isro.gov.in/Careers.html"},
            {"organization": "DRDO", "career_url": "https://www.drdo.gov.in/career"},
            {"organization": "BARC", "career_url": "https://www.barc.gov.in/careers/"},
            {"organization": "State Bank of India", "career_url": "https://sbi.co.in/careers"},
            {"organization": "IBPS", "career_url": "https://www.ibps.in/"},
            {"organization": "RBI", "career_url": "https://www.rbi.org.in/Scripts/Careers.aspx"},
            {"organization": "Indian Railways", "career_url": "https://www.indianrailways.gov.in/"},
            {"organization": "ONGC", "career_url": "https://www.ongcindia.com/careers"},
            {"organization": "NTPC", "career_url": "https://www.ntpc.co.in/careers"},
            {"organization": "UPSC", "career_url": "https://www.upsc.gov.in/"},
            {"organization": "SSC", "career_url": "https://ssc.nic.in/"},
            {"organization": "BHEL", "career_url": "https://www.bhel.com/careers"},
            {"organization": "SAIL", "career_url": "https://www.sail.co.in/careers"},
            {"organization": "Coal India", "career_url": "https://www.coalindia.in/careers/"},
            {"organization": "GAIL", "career_url": "https://www.gailonline.com/careers/"},
            {"organization": "IOCL", "career_url": "https://iocl.com/careers"},
            {"organization": "BPCL", "career_url": "https://www.bharatpetroleum.in/careers/"},
            {"organization": "HPCL", "career_url": "https://www.hindustanpetroleum.com/careers"},
            {"organization": "Power Grid Corporation", "career_url": "https://www.powergridindia.com/careers"},
            {"organization": "NHPC", "career_url": "https://www.nhpcindia.com/careers/"},
            {"organization": "SJVN", "career_url": "https://www.sjvn.nic.in/careers"},
            {"organization": "IRCON", "career_url": "https://www.ircon.org/careers"},
            {"organization": "RITES", "career_url": "https://www.rites.com/careers"},
            {"organization": "CONCOR", "career_url": "https://www.concorindia.com/careers"},
            {"organization": "FCI", "career_url": "https://fci.gov.in/careers.php"},
            {"organization": "NABARD", "career_url": "https://www.nabard.org/careers.aspx"},
            {"organization": "LIC", "career_url": "https://licindia.in/careers"},
            {"organization": "ESIC", "career_url": "https://www.esic.nic.in/careers"},
            {"organization": "EPFO", "career_url": "https://www.epfindia.gov.in/site_en/careers.php"},
            {"organization": "Delhi Metro", "career_url": "https://www.delhimetrorail.com/careers"}
        ]
    
    async def scrape_organization_jobs(self, organization: str, career_url: str) -> List[Dict[str, Any]]:
        """Scrape job postings from a government organization's career page"""
        try:
            logger.info(f"Starting Playwright scraping for {organization}")

            def _sync_scrape():
                scraped_jobs = []
                with sync_playwright() as p:
                    logger.info("Launching Chromium browser...")
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-gpu',
                            '--disable-web-security',
                            '--disable-features=VizDisplayCompositor'
                        ]
                    )
                    page = browser.new_page()
                    page.set_extra_http_headers({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    })
                    try:
                        logger.info(f"Scraping jobs from {organization}: {career_url}")
                        page.goto(career_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(3000)
                        job_selectors = [
                            'a[href*="job"]',
                            'a[href*="career"]',
                            'a[href*="recruitment"]',
                            'a[href*="vacancy"]',
                            'a[href*="notification"]',
                            '.job-listing',
                            '.career-item',
                            '.recruitment-item',
                            '.vacancy-item',
                            'tr td a',
                            'li a',
                        ]
                        job_links = []
                        for selector in job_selectors:
                            try:
                                elements = page.query_selector_all(selector)
                                if elements:
                                    logger.info(f"Found {len(elements)} potential job links with selector: {selector}")
                                    job_links.extend(elements)
                                    break
                            except Exception:
                                continue
                        for i, link in enumerate(job_links[:10]):
                            try:
                                title = link.inner_text()
                                href = link.get_attribute('href')
                                if not title or not href or len(title.strip()) < 3:
                                    continue
                                scraped_jobs.append({
                                    "title": title.strip(),
                                    "apply_url": href,
                                    "posted_date": "Recently",
                                    "last_date": "Check notification"
                                })
                            except Exception:
                                continue
                    except Exception as e:
                        logger.error(f"Error scraping {organization}: {e}")
                    finally:
                        browser.close()
                return scraped_jobs

            jobs = await asyncio.to_thread(_sync_scrape)
            return jobs

        except Exception as e:
            logger.error(f"Error scraping {organization}: {e}")
            return []


            if parent:
                parent_text = await parent.inner_text()
                # Look for date patterns like "Last Date: 31-12-2024" or "31/12/2024"
                import re
                date_patterns = [
                    r'last\s+date[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
                    r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
                    r'deadline[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
                ]
                
                for pattern in date_patterns:
                    match = re.search(pattern, parent_text.lower())
                    if match:
                        return match.group(1)
        except Exception:
            pass
        

    
    async def discover_all_jobs(self) -> List[Dict[str, Any]]:
        """Discover government jobs by fetching organizations and scraping their career pages"""
        try:
            organizations = await self.get_government_organizations()
            logger.info(f"OpenAI returned {len(organizations)} organizations: {organizations[:3]}")
            results = []
            for org in organizations:
                org_name = org.get('organization')
                career_url = org.get('career_url')
                logger.info(f"Scraping org: {org_name} | URL: {career_url}")
                if not org_name or not career_url:
                    logger.warning(f"Skipping org with missing data: {org}")
                    continue
                try:
                    jobs = await self.scrape_organization_jobs(org_name, career_url)
                    logger.info(f"Scraped {len(jobs)} jobs for {org_name}")
                except Exception as scrape_exc:
                    logger.error(f"Error scraping {org_name}: {scrape_exc}")
                    import traceback
                    logger.error(traceback.format_exc())
                    jobs = []
                results.append({
                    'organization': org_name,
                    'career_url': career_url,
                    'jobs': jobs
                })
            logger.info(f"Returning discovery results for {len(results)} organizations.")
            return results
        except Exception as e:
            logger.error(f"Unexpected error in job discovery: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

# Global service instance
job_discovery_service = JobDiscoveryService()
