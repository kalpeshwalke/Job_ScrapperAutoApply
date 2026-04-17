"""
Naukri scraper — dual strategy:
  1. API-first:     GET /jobapi/v3/search (fast, structured JSON)
  2. Browser-fallback: Selenium scraping (if API is blocked)

No login required — Naukri search is public.
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

logger = get_logger("naukri")


class NaukriScraper(BaseScraper):
    """Scrapes QA/Testing jobs from Naukri.com."""

    @property
    def platform_name(self) -> str:
        return "Naukri"

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def scrape(self) -> list[dict]:
        """Execute Naukri scraping. Tries API first, falls back to browser."""
        logger.info("=" * 60)
        logger.info("Starting Naukri scraper")
        logger.info("=" * 60)

        max_jobs = self.config.naukri_max_jobs
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

                # Try API first
                jobs = self._scrape_via_api(keyword, location, max_jobs - len(all_jobs))

                # Fallback to browser if API fails
                if jobs is None:
                    logger.info("API blocked — falling back to browser scraping")
                    jobs = self._scrape_via_browser(keyword, location, max_jobs - len(all_jobs))

                if jobs:
                    all_jobs.extend(jobs)
                    logger.info("Collected %d jobs so far (total: %d)", len(jobs), len(all_jobs))

                human_delay(1, 3)

        logger.info("Naukri scraping complete: %d jobs collected", len(all_jobs))
        
        # Validate jobs against Job_Schema before returning
        validated_jobs = self.validate_jobs(all_jobs)
        logger.info("Naukri validation: %d/%d jobs passed schema validation", 
                   len(validated_jobs), len(all_jobs))
        
        return validated_jobs

    # ------------------------------------------------------------------
    # Strategy 1: API-based scraping
    # ------------------------------------------------------------------
    def _scrape_via_api(
        self, keyword: str, location: str, remaining: int
    ) -> Optional[list[dict]]:
        """
        Try to scrape via Naukri's internal JSON API.
        Returns list of jobs, or None if blocked.
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
                    logger.warning("Naukri API returned 403 (blocked)")
                    return None
                if response.status_code != 200:
                    logger.warning("Naukri API returned %d", response.status_code)
                    return None

                data = response.json()
                job_results = data.get("jobDetails", [])

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
        """Build Naukri search API URL."""
        params = {
            "noOfResults": per_page,
            "urlType": "search_by_key_loc",
            "searchType": "adv",
            "keyword": keyword,
            "location": location,
            "pageNo": page,
            "k": keyword,
            "l": location,
            "experience": self.config.experience_range.get("min", 2),
            "jobAge": self.config.date_posted_days,
            "sort": "relevance",
            "src": "jobsearchDesk",
            "latLong": "",
        }
        base = "https://www.naukri.com/jobapi/v3/search"
        return f"{base}?{urllib.parse.urlencode(params)}"

    def _api_headers(self) -> dict:
        """Build realistic headers for API requests."""
        return {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "appid": "109",
            "clientid": "d3skt0p",
            "content-type": "application/json",
            "gid": "LOCATION,INDUSTRY,EDUCATION,FAREA_ROLE",
            "referer": "https://www.naukri.com/",
            "systemid": "Naukri",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
        }

    def _parse_api_job(self, item: dict) -> Optional[dict]:
        """Parse a single job from the API response."""
        try:
            title = item.get("title", "").strip()
            company = item.get("companyName", "").strip()

            if not title or not company:
                return None

            # Extract experience range
            exp_min = item.get("minExperience", "")
            exp_max = item.get("maxExperience", "")
            if exp_min and exp_max:
                experience = f"{exp_min}-{exp_max} years"
            elif exp_min:
                experience = f"{exp_min}+ years"
            else:
                experience = item.get("experienceText", "")

            # Extract skills/tags
            tags = item.get("tagsAndSkills", "")
            if isinstance(tags, list):
                skills = ", ".join(tags)
            else:
                skills = str(tags) if tags else ""

            # Build job link
            job_id = item.get("jobId", "")
            seo_url = item.get("jdURL", "")
            if seo_url and not seo_url.startswith("http"):
                link = f"https://www.naukri.com{seo_url}"
            elif seo_url:
                link = seo_url
            else:
                link = f"https://www.naukri.com/job-listings-{job_id}" if job_id else ""

            return {
                "title": title,
                "company": company,
                "location": item.get("placeholders", [{}])[0].get("value", "")
                    if item.get("placeholders") else item.get("cityName", ""),
                "experience": experience,
                "skills": skills,
                "salary": item.get("salaryText", item.get("salary", "")),
                "description": item.get("jobDescription", ""),
                "posted_date": item.get("createdDate", item.get("footerPlaceholderLabel", "")),
                "link": link,
                "platform": "Naukri",
                "easy_apply": "N/A",
            }
        except Exception as e:
            logger.debug("Failed to parse API job: %s", e)
            return None

    def _ensure_logged_in(self) -> bool:
        """Autologin using DrissionPage if not logged in."""
        if not self.config.naukri_email or not self.config.naukri_password:
            logger.info("No Naukri credentials provided in config, proceeding without login.")
            return True

        self.driver.get("https://www.naukri.com/nlogin/login")
        self._human_delay(2, 4)

        if "login" not in self.driver.url.lower():
            logger.info("Already logged into Naukri via profile cache.")
            return True

        logger.info("Logging into Naukri...")
        # Type email
        username_el = self.driver.ele("css:input#usernameField")
        if username_el:
            username_el.input(self.config.naukri_email)
            self._human_delay(0.5, 1)

        # Type password
        password_el = self.driver.ele("css:input#passwordField")
        if password_el:
            password_el.input(self.config.naukri_password)
            self._human_delay(0.5, 1)

        # Click login
        login_btn = self.driver.ele("css:button[data-ga-track='spa-event|login|login|Save||||true']")
        if not login_btn:
             login_btn = self.driver.ele("css:button.loginButton, button[type='submit']")
        
        if login_btn:
            login_btn.click()
            self._human_delay(3, 5)

        if "login" in self.driver.url.lower():
            logger.error("Failed to login to Naukri. Please check credentials or captcha.")
            return False
        
        logger.info("Naukri login successful!")
        return True

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
                profile_name="naukri_profile"
            )
            self._ensure_logged_in()

        try:
            page = 1
            parsed_count = 0  # Initialize counter
            while len(jobs) < remaining:
                url = self._build_browser_url(keyword, location, page)
                logger.info("Browser: loading page %d — %s", page, url[:80])

                self.driver.get(url)
                
                # CRITICAL: Capture cards IMMEDIATELY before page changes
                # Naukri's anti-bot replaces content after ~1 second
                time.sleep(1.5)  # Just enough for initial load
                
                # Try to find cards immediately
                cards = self.driver.eles("css:div.srp-jobtuple-wrapper, article.jobTuple")
                
                # If cards found, extract data
                if cards:
                    logger.info("Found %d job cards on page %d", len(cards), page)
                    parsed_count = 0
                    for card in cards:
                        if len(jobs) >= remaining:
                            break
                        try:
                            job = self._parse_browser_card(card)
                            if job and not self._is_already_scraped(job.get("link", "")):
                                jobs.append(job)
                                parsed_count += 1
                        except Exception as e:
                            logger.debug("Failed to parse card or stale element: %s", e)
                            continue
                    
                    logger.info("Successfully parsed %d jobs from page %d", parsed_count, page)
                    
                    # Check if there's a next page
                    page += 1
                    
                    # IMPORTANT: Longer delay between pages to avoid detection
                    # Pages 2+ are more heavily monitored by anti-bot
                    if page == 2:
                        logger.info("Moving to page 2 - adding extra delay to avoid detection...")
                        self._human_delay(8, 12)  # Extra long delay for page 2
                    else:
                        self._human_delay(5, 8)  # Normal delay for other pages
                    
                    # Stop after reasonable pages
                    # Pages 2+ have higher blocking risk, so limit pagination
                    max_pages = self.config.naukri_max_pages_per_search
                    if page > max_pages:
                        logger.info("Reached page limit (%d pages) - stopping to avoid detection", max_pages)
                        break
                    
                    continue  # Skip the rest of the loop
                
                # If no cards found immediately, page is being blocked
                logger.error("No job cards found - Naukri is blocking the scraper")
                logger.error("Page content is being replaced with homepage/navigation")
                
                # Check what content we're actually seeing
                page_text_ele = self.driver.ele("tag:body")
                page_text = page_text_ele.text.lower() if page_text_ele else ""
                if "popular categories" in page_text or "jobs in demand" in page_text:
                    logger.error("Confirmed: Page showing homepage instead of search results")
                    logger.error("")
                    logger.error("SOLUTIONS:")
                    logger.error("  1. Close the browser and run again (sometimes works)")
                    logger.error("  2. Manually solve any captcha if it appears")
                    logger.error("  3. Try using a VPN or different network")
                    logger.error("  4. Reduce max_jobs to scrape less frequently")
                    logger.error("")
                
                break  # Stop trying this keyword-location combo

            # Pass 2: Fetch full job details (optional - can be slow)
            if jobs and self.config.naukri_fetch_full_descriptions:
                logger.info("Fetching full descriptions for %d jobs (this may take a while)...", len(jobs))
                jobs = self._fetch_job_details(jobs)
            elif jobs:
                logger.info("Skipping full description fetch (using card snippets for speed)")
                logger.info("To enable full descriptions: set naukri.fetch_full_descriptions: true in config")

        except Exception as e:
            logger.error("Browser scraping error: %s", e)
        finally:
            if self.config.save_partial_on_crash and jobs:
                logger.info("Partial data preserved: %d jobs", len(jobs))

        return jobs

    def _fetch_job_details(self, cards: list[dict]) -> list[dict]:
        """Pass 2: Visit job links to extract full description and details.
        
        Uses parallel tab opening via DrissionPage.
        """
        if not cards:
            return []
        
        detailed_jobs = []
        batch_size = self.config.naukri_parallel_detail_fetch
        logger.info("Using parallel tab processing: %d tabs per batch", batch_size)
        
        for batch_start in range(0, len(cards), batch_size):
            batch_end = min(batch_start + batch_size, len(cards))
            batch = cards[batch_start:batch_end]
            logger.info("Pass 2: Fetching details %d-%d/%d", batch_start + 1, batch_end, len(cards))
            
            tab_ptrs = []
            
            for i, card in enumerate(batch):
                link = card.get("link", "")
                if not link:
                    detailed_jobs.append(card)
                    continue
                try:
                    tab = self.driver.new_tab(link)
                    tab_ptrs.append({"tab": tab, "card": card})
                    time.sleep(0.5)
                except Exception as e:
                    logger.debug("Failed to open tab for %s: %s", link[:60], e)
                    detailed_jobs.append(card)
            
            self._human_delay(3, 5)
            
            for ptr in tab_ptrs:
                tab = ptr["tab"]
                card = ptr["card"]
                try:
                    desc_el = tab.ele("css:div.danger-html, section.job-desc", timeout=3)
                    if desc_el:
                        card["description"] = desc_el.text.strip()
                    detailed_jobs.append(card)
                except Exception as e:
                    logger.debug("Failed to extract details from tab: %s", e)
                    detailed_jobs.append(card)
                finally:
                    tab.close()
            
            if batch_end < len(cards):
                self._human_delay(2, 3)
        
        return detailed_jobs

    def _build_browser_url(self, keyword: str, location: str, page: int) -> str:
        """Build Naukri search page URL for browser."""
        kw_slug = keyword.lower().replace(" ", "-")
        loc_slug = location.lower().replace(" ", "-")

        exp_min = self.config.experience_range.get("min", 2)
        exp_max = self.config.experience_range.get("max", 5)

        url = f"https://www.naukri.com/{kw_slug}-jobs-in-{loc_slug}"
        params = {
            "k": keyword,
            "l": location,
            "experience": exp_min,
            "nignbeq_n": exp_max,
            "jobAge": self.config.date_posted_days,
        }
        if page > 1:
            params["pageNo"] = page

        return f"{url}?{urllib.parse.urlencode(params)}"

    def _parse_browser_card(self, card) -> Optional[dict]:
        """Parse a single job card element from DrissionPage element."""
        try:
            title_el = card.ele("css:a.title, a.jobTitle, h2 a", timeout=1)
            if not title_el:
                return None
            title = title_el.text.strip()
            link = title_el.attr("href") or ""

            company_el = card.ele("css:a.comp-name, span.comp-name, a.subTitle", timeout=0.1)
            company = company_el.text.strip() if company_el else ""

            exp_el = card.ele("css:span.expwdth, span.exp, li.experience", timeout=0.1)
            experience = exp_el.text.strip() if exp_el else ""

            salary_el = card.ele("css:span.sal, span.salary, li.salary", timeout=0.1)
            salary = salary_el.text.strip() if salary_el else ""

            loc_el = card.ele("css:span.locWdth, span.loc, li.location", timeout=0.1)
            location = loc_el.text.strip() if loc_el else ""

            skill_els = card.eles("css:ul.tags-gt li, span.tag-li, li.tag-li")
            skills = ", ".join([s.text.strip() for s in skill_els if s.text.strip()])

            desc_el = card.ele("css:span.job-desc, div.job-description", timeout=0.1)
            description = desc_el.text.strip() if desc_el else ""

            date_el = card.ele("css:span.date, span.job-post-day", timeout=0.1)
            posted_date = date_el.text.strip() if date_el else ""

            return {
                "title": title,
                "company": company,
                "location": location,
                "experience": experience,
                "skills": skills,
                "salary": salary,
                "description": description,
                "posted_date": posted_date,
                "link": link,
                "platform": "Naukri",
                "easy_apply": "N/A",
            }

        except Exception as e:
            logger.debug("Failed to parse browser card: %s", e)
            return None
