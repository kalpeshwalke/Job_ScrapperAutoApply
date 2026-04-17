"""
Foundit (Monster India) scraper — dual strategy:
  1. API-first:     Attempt API endpoint first (fast, structured JSON)
  2. Browser-fallback: Selenium scraping (if API is blocked)

API availability status is cached per session to avoid repeated browser initialization.
"""

import json
import re
import time
import urllib.parse
from typing import Optional

import requests

from src.scrapers.base_scraper import BaseScraper
from src.common.browser import create_browser, human_delay
from src.common.logger import get_logger

logger = get_logger("foundit")


class FounditScraper(BaseScraper):
    """Scrapes QA/Testing jobs from Foundit.co.in (formerly Monster India)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cache API availability status for the session
        self._api_available = None  # None = unknown, True = working, False = failed

    @property
    def platform_name(self) -> str:
        return "Foundit"

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def scrape(self) -> list[dict]:
        """Execute Foundit scraping. Tries API first, falls back to browser."""
        logger.info("=" * 60)
        logger.info("Starting Foundit scraper")
        logger.info("=" * 60)

        max_jobs = self.config.foundit_max_jobs if hasattr(self.config, 'foundit_max_jobs') else 50
        all_jobs = []

        for keyword in self.config.search_keywords:
            if len(all_jobs) >= max_jobs:
                logger.info("Reached max_jobs limit (%d) — stopping keyword search", max_jobs)
                break

            for location in self.config.search_locations:
                if len(all_jobs) >= max_jobs:
                    logger.info("Reached max_jobs limit (%d) — stopping location search", max_jobs)
                    break

                logger.info("Searching: '%s' in '%s'", keyword, location)

                # Try API first (if not already known to be unavailable)
                if self._api_available is not False:
                    jobs = self._scrape_via_api(keyword, location, max_jobs - len(all_jobs))
                    
                    if jobs is not None:
                        # API worked - cache this status
                        self._api_available = True
                        all_jobs.extend(jobs)
                        logger.info("Collected %d jobs via API (total: %d)", len(jobs), len(all_jobs))
                        human_delay(1, 3)
                        continue
                    else:
                        # API failed - cache this status and fall back to browser
                        self._api_available = False
                        logger.info("API unavailable — falling back to browser scraping")

                # Fallback to browser if API failed or is known to be unavailable
                jobs = self._scrape_via_browser(keyword, location, max_jobs - len(all_jobs))
                if jobs:
                    all_jobs.extend(jobs)
                    logger.info("Collected %d jobs via browser (total: %d)", len(jobs), len(all_jobs))

                human_delay(1, 3)

        logger.info("Foundit scraping complete: %d jobs collected", len(all_jobs))
        
        # Validate jobs against Job_Schema before returning
        validated_jobs = self.validate_jobs(all_jobs)
        logger.info("Foundit validation: %d/%d jobs passed schema validation", 
                   len(validated_jobs), len(all_jobs))
        
        return validated_jobs

    # ------------------------------------------------------------------
    # Strategy 1: API-based scraping
    # ------------------------------------------------------------------
    def _scrape_via_api(
        self, keyword: str, location: str, remaining: int
    ) -> Optional[list[dict]]:
        """
        Try to scrape via Foundit's internal JSON API.
        Returns list of jobs, or None if blocked/unavailable.
        """
        jobs = []
        page = 1
        per_page = 20

        while len(jobs) < remaining:
            try:
                url = self._build_api_url(keyword, location, page, per_page)
                headers = self._api_headers()

                proxies = {"http": self.config.proxy, "https": self.config.proxy} if self.config.proxy else None
                response = requests.get(url, headers=headers, proxies=proxies, timeout=15)

                if response.status_code == 403:
                    logger.warning("Foundit API returned 403 (blocked)")
                    return None
                if response.status_code == 404:
                    logger.warning("Foundit API endpoint not found (404)")
                    return None
                if response.status_code != 200:
                    logger.warning("Foundit API returned %d", response.status_code)
                    return None

                data = response.json()
                job_results = data.get("jobs", data.get("jobDetails", []))

                if not job_results:
                    logger.debug("No more jobs from API (page %d)", page)
                    break

                for item in job_results:
                    if len(jobs) >= remaining:
                        break

                    job = self._parse_api_job(item)
                    if job and not self._is_already_scraped(job.get("link", "")):
                        jobs.append(job)

                page += 1
                human_delay(1, 2)

            except (requests.RequestException, json.JSONDecodeError) as e:
                logger.warning("API request failed: %s", e)
                return None
            except Exception as e:
                logger.error("Unexpected API error: %s", e)
                return None

        return jobs if jobs else None

    def _build_api_url(
        self, keyword: str, location: str, page: int, per_page: int
    ) -> str:
        """Build Foundit search API URL."""
        # Note: This is a placeholder URL structure
        # Actual Foundit API endpoint may differ
        params = {
            "query": keyword,
            "locations": location,
            "page": page,
            "limit": per_page,
            "sort": "relevance",
        }
        base = "https://www.foundit.in/api/v1/jobs/search"
        return f"{base}?{urllib.parse.urlencode(params)}"

    def _api_headers(self) -> dict:
        """Build realistic headers for API requests."""
        return {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "referer": "https://www.foundit.in/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
        }

    def _parse_api_job(self, item: dict) -> Optional[dict]:
        """Parse a single job from the API response."""
        try:
            title = item.get("title", item.get("jobTitle", "")).strip()
            company = item.get("company", item.get("companyName", "")).strip()

            if not title or not company:
                return None

            # Extract experience
            exp_min = item.get("minExperience", item.get("experienceMin", ""))
            exp_max = item.get("maxExperience", item.get("experienceMax", ""))
            if exp_min and exp_max:
                experience = f"{exp_min}-{exp_max} years"
            elif exp_min:
                experience = f"{exp_min}+ years"
            else:
                experience = item.get("experience", "")

            # Extract skills
            skills_list = item.get("skills", item.get("keySkills", []))
            if isinstance(skills_list, list):
                skills = ", ".join(skills_list)
            else:
                skills = str(skills_list) if skills_list else ""

            # Build job link
            job_id = item.get("jobId", item.get("id", ""))
            job_url = item.get("url", item.get("jobUrl", ""))
            if job_url and not job_url.startswith("http"):
                link = f"https://www.foundit.in{job_url}"
            elif job_url:
                link = job_url
            else:
                link = f"https://www.foundit.in/job/{job_id}" if job_id else ""

            return {
                "title": title,
                "company": company,
                "location": item.get("location", item.get("jobLocation", "")),
                "experience": experience,
                "skills": skills,
                "salary": item.get("salary", item.get("salaryText", "")),
                "description": item.get("description", item.get("jobDescription", "")),
                "posted_date": item.get("postedDate", item.get("createdDate", "")),
                "link": link,
                "platform": "Foundit",
                "easy_apply": "N/A",
            }
        except Exception as e:
            logger.debug("Failed to parse API job: %s", e)
            return None

    # ------------------------------------------------------------------
    # Strategy 2: Browser-based scraping
    # ------------------------------------------------------------------
    def _scrape_via_browser(
        self, keyword: str, location: str, remaining: int
    ) -> list[dict]:
        """Scrape via DrissionPage if API is blocked."""
        jobs = []

        # Create browser if not already available
        if not self.driver:
            self.driver = create_browser(
                headless=self.config.headless,
                chrome_version=self.config.chrome_version_main,
                page_load_timeout=self.config.page_load_timeout,
                proxy=self.config.proxy,
                profile_name="foundit_profile"
            )

        try:
            page = 1
            max_pages = getattr(self.config, 'foundit_max_pages_per_search', 5)
            
            while len(jobs) < remaining and page <= max_pages:
                url = self._build_browser_url(keyword, location, page)
                logger.info("Browser: loading page %d — %s", page, url[:80])

                self.driver.get(url)
                # Foundit is a React SPA — needs extra time for JS rendering
                time.sleep(6)

                # Find job cards using the correct Foundit SPA selectors
                cards = self.driver.eles("css:div.srpResultCardContainer")

                if not cards:
                    logger.warning("No job cards found on page %d", page)
                    break

                logger.info("Found %d job cards on page %d", len(cards), page)

                for card in cards:
                    if len(jobs) >= remaining:
                        break
                    try:
                        job = self._parse_browser_card(card)
                        if job and not self._is_already_scraped(job.get("link", "")):
                            jobs.append(job)
                    except Exception as e:
                        logger.debug("Failed to parse card: %s", e)
                        continue

                page += 1
                self._human_delay(3, 5)

        except Exception as e:
            logger.error("Browser scraping error: %s", e)
        finally:
            if self.config.save_partial_on_crash and jobs:
                logger.info("Partial data preserved: %d jobs", len(jobs))

        return jobs

    def _build_browser_url(self, keyword: str, location: str, page: int) -> str:
        """Build Foundit search page URL for browser."""
        url = f"https://www.foundit.in/srp/results"
        params = {
            "query": keyword,
            "locations": location,
            "page": page,
        }

        return f"{url}?{urllib.parse.urlencode(params)}"

    def _parse_browser_card(self, card) -> Optional[dict]:
        """Parse a single Foundit job card element from DrissionPage.
        
        Verified selectors from live DOM inspection (April 2026):
          - Card container: div.srpResultCardContainer
          - Title: div.jobTitle
          - Company: div.companyName > p
          - Experience: span.details (first child of div.experienceSalary)
          - Location: div.details.location
          - Posted date: p.timeText
          - Job ID: div.cardContainer[id] — used to build job URL
        """
        try:
            # Extract job title
            title_el = card.ele("css:div.jobTitle", timeout=1)
            if not title_el:
                return None
            title = title_el.text.strip()
            if not title:
                return None

            # Extract company name (inside <p> tag within div.companyName)
            company_el = card.ele("css:div.companyName", timeout=0.5)
            company = company_el.text.strip() if company_el else ""

            # Extract experience (first span.details inside experienceSalary section)
            exp_el = card.ele("css:div.experienceSalary span.details", timeout=0.5)
            experience = exp_el.text.strip() if exp_el else ""

            # Extract location
            loc_el = card.ele("css:div.location", timeout=0.5)
            location = loc_el.text.strip() if loc_el else ""

            # Extract posted date
            date_el = card.ele("css:p.timeText", timeout=0.5)
            posted_date = date_el.text.strip() if date_el else ""
            # Clean up "Posted X ago" format
            if posted_date.lower().startswith("posted"):
                posted_date = posted_date[6:].strip()

            # Build job link from the card container's ID attribute
            card_container = card.ele("css:div.cardContainer", timeout=0.5)
            job_id = card_container.attr("id") if card_container else ""
            link = f"https://www.foundit.in/job/{job_id}" if job_id else ""

            # Extract salary if present (sometimes shown in experienceSalary)
            salary = ""
            salary_el = card.ele("css:div.salarySection span.details", timeout=0.3)
            if salary_el:
                salary = salary_el.text.strip()

            return {
                "title": title,
                "company": company,
                "location": location,
                "experience": experience,
                "skills": "",
                "salary": salary,
                "description": "",
                "posted_date": posted_date,
                "link": link,
                "platform": "Foundit",
                "easy_apply": "N/A",
            }

        except Exception as e:
            logger.debug("Failed to parse browser card: %s", e)
            return None
