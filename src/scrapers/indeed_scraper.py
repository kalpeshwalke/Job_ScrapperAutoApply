"""
Indeed scraper — browser-based scraping with DrissionPage.

Indeed requires browser automation for job search scraping.
Implements CAPTCHA detection and partial results handling.

Integration:
    To enable Indeed scraper in main.py:
    1. Import: from scraper.indeed_scraper import IndeedScraper
    2. Check config: if Config.indeed_enabled:
    3. Instantiate: scraper = IndeedScraper(config=Config, known_links=known_links)
    4. Execute: jobs = scraper.scrape()
    5. Validate: validated_jobs = scraper.validate_jobs(jobs)
"""

import time
from typing import Optional

from src.scrapers.base_scraper import BaseScraper
from src.common.browser import create_browser
from src.common.logger import get_logger

logger = get_logger("indeed")


class IndeedScraper(BaseScraper):
    """Scrapes jobs from Indeed.com using browser automation."""

    @property
    def platform_name(self) -> str:
        return "Indeed"

    def scrape(self) -> list[dict]:
        """Execute Indeed scraping using browser automation."""
        logger.info("=" * 60)
        logger.info("Starting Indeed scraper")
        logger.info("=" * 60)

        max_jobs = self.config.indeed_max_jobs
        all_jobs = []

        # Create browser if not already available
        if not self.driver:
            self.driver = create_browser(
                headless=self.config.headless,
                chrome_version=self.config.chrome_version_main,
                page_load_timeout=self.config.page_load_timeout,
                proxy=self.config.proxy,
                profile_name="indeed_profile"
            )

        try:
            for keyword in self.config.search_keywords:
                if len(all_jobs) >= max_jobs:
                    logger.info("Reached max_jobs limit (%d) — stopping keyword search", max_jobs)
                    break

                for location in self.config.search_locations:
                    if len(all_jobs) >= max_jobs:
                        logger.info("Reached max_jobs limit (%d) — stopping location search", max_jobs)
                        break

                    logger.info("Searching: '%s' in '%s'", keyword, location)

                    jobs = self._scrape_search_results(keyword, location, max_jobs - len(all_jobs))
                    
                    if jobs:
                        all_jobs.extend(jobs)
                        logger.info("Collected %d jobs so far (total: %d)", len(jobs), len(all_jobs))

                    self._human_delay(2, 4)

        except Exception as e:
            logger.error("Indeed scraping error: %s", e)
            if self.config.save_partial_on_crash and all_jobs:
                logger.info("Partial data preserved: %d jobs", len(all_jobs))
        
        logger.info("Indeed scraping complete: %d jobs collected", len(all_jobs))
        
        # Validate jobs against Job_Schema before returning
        validated_jobs = self.validate_jobs(all_jobs)
        logger.info("Indeed validation: %d/%d jobs passed schema validation", 
                   len(validated_jobs), len(all_jobs))
        
        return validated_jobs

    def _scrape_search_results(self, keyword: str, location: str, remaining: int) -> list[dict]:
        """Scrape job listings from Indeed search results."""
        jobs = []
        page = 0  # Indeed uses 0-based pagination (0, 10, 20, ...)

        while len(jobs) < remaining:
            url = self._build_search_url(keyword, location, page)
            logger.info("Loading page %d — %s", page // 10 + 1, url[:80])

            try:
                self.driver.get(url)
                self._human_delay(2, 4)

                # Check for CAPTCHA
                if self._detect_captcha():
                    logger.error("CAPTCHA detected on Indeed — returning partial results")
                    break

                # Find job cards
                cards = self._find_job_cards()
                
                if not cards:
                    logger.info("No more job cards found on page %d", page // 10 + 1)
                    break

                logger.info("Found %d job cards on page %d", len(cards), page // 10 + 1)

                # Parse each card
                for card in cards:
                    if len(jobs) >= remaining:
                        break
                    
                    try:
                        job = self._parse_job_card(card)
                        if job and not self._is_already_scraped(job.get("link", "")):
                            jobs.append(job)
                    except Exception as e:
                        logger.debug("Failed to parse card: %s", e)
                        continue

                # Check for next page
                page += 10
                
                # Limit pagination to avoid detection
                max_pages = getattr(self.config, 'indeed_max_pages_per_search', 5)
                if page // 10 >= max_pages:
                    logger.info("Reached page limit (%d pages) — stopping", max_pages)
                    break

                self._human_delay(3, 6)

            except Exception as e:
                logger.error("Error scraping page %d: %s", page // 10 + 1, e)
                break

        return jobs

    def _build_search_url(self, keyword: str, location: str, start: int) -> str:
        """Build Indeed search URL."""
        import urllib.parse
        
        params = {
            "q": keyword,
            "l": location,
            "fromage": getattr(self.config, 'date_posted_days', 7),  # Days since posted
        }
        
        if start > 0:
            params["start"] = start
        
        base_url = "https://in.indeed.com/jobs"
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    def _detect_captcha(self) -> bool:
        """Detect if Indeed is showing a CAPTCHA."""
        try:
            # Check for common CAPTCHA indicators
            captcha_indicators = [
                "css:iframe[title*='recaptcha']",
                "css:div#recaptcha",
                "css:div.cf-browser-verification",
                "text:verify you are human",
                "text:security check"
            ]
            
            for indicator in captcha_indicators:
                if self.driver.ele(indicator, timeout=1):
                    return True
            
            return False
        except Exception:
            return False

    def _find_job_cards(self) -> list:
        """Find job card elements on the page."""
        try:
            # Indeed uses various selectors for job cards
            selectors = [
                "css:div.job_seen_beacon",
                "css:div.jobsearch-SerpJobCard",
                "css:div[data-jk]",
                "css:td.resultContent"
            ]
            
            for selector in selectors:
                cards = self.driver.eles(selector, timeout=2)
                if cards:
                    return cards
            
            return []
        except Exception as e:
            logger.debug("Error finding job cards: %s", e)
            return []

    def _parse_job_card(self, card) -> Optional[dict]:
        """Parse a single job card element."""
        try:
            # Extract job title and link
            title_el = card.ele("css:a.jcs-JobTitle, h2.jobTitle a", timeout=1)
            if not title_el:
                return None
            
            title = title_el.text.strip()
            link = title_el.attr("href") or ""
            
            # Make link absolute
            if link and not link.startswith("http"):
                link = f"https://in.indeed.com{link}"
            
            # Extract company name
            company_el = card.ele("css:span[data-testid='company-name'], css:span.companyName", timeout=0.5)
            company = company_el.text.strip() if company_el else ""
            
            # Extract location
            location_el = card.ele("css:div[data-testid='text-location'], css:div.companyLocation", timeout=0.5)
            location = location_el.text.strip() if location_el else ""
            
            # Extract salary
            salary_el = card.ele("css:div[data-testid='attribute_snippet_testid'], css:div.salary-snippet", timeout=0.5)
            salary = salary_el.text.strip() if salary_el else ""
            
            # Extract job snippet/description
            desc_el = card.ele("css:div.job-snippet, css:div[data-testid='job-snippet']", timeout=0.5)
            description = desc_el.text.strip() if desc_el else ""
            
            # Extract posted date
            date_el = card.ele("css:span.date, css:span[data-testid='myJobsStateDate']", timeout=0.5)
            posted_date = date_el.text.strip() if date_el else ""
            
            # Check for easy apply
            easy_apply = "N/A"
            try:
                if "easily apply" in card.text.lower():
                    easy_apply = "Yes"
            except Exception:
                pass

            return {
                "title": title,
                "company": company,
                "location": location,
                "experience": "",  # Indeed doesn't always show experience in cards
                "skills": "",
                "salary": salary,
                "description": description,
                "posted_date": posted_date,
                "link": link,
                "platform": "Indeed",
                "easy_apply": easy_apply,
            }

        except Exception as e:
            logger.debug("Failed to parse job card: %s", e)
            return None
