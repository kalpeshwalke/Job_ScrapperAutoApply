"""
LinkedIn scraper — auto-login, 2-pass optimized approach.

Pass 1 (Collect):   Scroll search results, extract card metadata (fast, low risk)
Pass 2 (Detail):    Open only top N job links for full details (configurable)

Authentication:     Auto-login via credentials in .env, with persistent profile cookies.
"""

import re
import time
import urllib.parse
from typing import Optional

from src.scrapers.base_scraper import BaseScraper
from src.common.browser import create_browser
from src.common.logger import get_logger

logger = get_logger("linkedin")


class LinkedInScraper(BaseScraper):
    """Scrapes QA/Testing jobs from LinkedIn using cookie-based browser automation."""

    @property
    def platform_name(self) -> str:
        return "LinkedIn"

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def scrape(self) -> list[dict]:
        """Execute LinkedIn scraping with 2-pass optimization."""
        logger.info("=" * 60)
        logger.info("Starting LinkedIn scraper (2-pass)")
        logger.info("=" * 60)

        # Create browser
        if not self.driver:
            self.driver = create_browser(
                headless=False,  # LinkedIn needs visible browser
                chrome_version=self.config.chrome_version_main,
                page_load_timeout=self.config.page_load_timeout,
                proxy=self.config.proxy,
                profile_name="linkedin_profile"
            )

        try:
            # Authenticate
            if not self._ensure_logged_in():
                logger.error("LinkedIn login failed — skipping")
                return []

            max_jobs = self.config.linkedin_max_jobs
            max_details = self.config.linkedin_max_detail_fetches
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

                    # Pass 1: Collect job cards
                    cards = self._collect_job_cards(
                        keyword, location, max_jobs - len(all_jobs)
                    )
                    logger.info("Pass 1: Collected %d job cards", len(cards))

                    if not cards:
                        continue

                    # Pass 2: Fetch details for top N
                    jobs = self._fetch_job_details(cards, max_details - len(all_jobs))
                    all_jobs.extend(jobs)

                    logger.info("Collected %d jobs so far (total: %d)", len(jobs), len(all_jobs))
                    self._human_delay(2, 4)

            # Save cookies for next run
            self._save_cookies()

            logger.info("LinkedIn scraping complete: %d jobs collected", len(all_jobs))
            
            # Validate jobs against Job_Schema before returning
            validated_jobs = self.validate_jobs(all_jobs)
            logger.info("LinkedIn validation: %d/%d jobs passed schema validation", 
                       len(validated_jobs), len(all_jobs))
            
            return validated_jobs

        except Exception as e:
            logger.error("LinkedIn scraping failed: %s", e)
            if self.config.save_partial_on_crash:
                logger.info("Returning partial data: %d jobs", len(self.jobs_collected))
                return self.jobs_collected
            return []

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def _ensure_logged_in(self) -> bool:
        """Ensure we have a valid LinkedIn session.
        
        Strategy:
          1. Load persistent profile (cookies auto-loaded by DrissionPage)
          2. Check if session is still valid
          3. If expired, auto-login with credentials from .env
          4. If no credentials, fall back to manual login (last resort)
        """
        self.driver.get("https://www.linkedin.com")
        self._human_delay(3, 5)

        # Check if persistent profile already has a valid session
        if self._is_logged_in():
            logger.info("LinkedIn session restored from persistent profile")
            return True

        logger.info("Session expired or first run — attempting auto-login")

        # Try auto-login with credentials
        email = getattr(self.config, 'linkedin_email', '')
        password = getattr(self.config, 'linkedin_password', '')

        if email and password:
            return self._auto_login(email, password)
        else:
            logger.warning("No LinkedIn credentials configured in .env — falling back to manual login")
            return self._manual_login()

    def _is_logged_in(self) -> bool:
        """Check if currently logged into LinkedIn."""
        current_url = self.driver.url
        if "login" in current_url or "authwall" in current_url:
            return False

        if self.driver.ele("css:nav.global-nav, div.feed-identity-module", timeout=2):
            return True

        if self.driver.ele("css:img.global-nav__me-photo, div.nav-item__profile-member-photo", timeout=1):
            return True

        return False

    def _auto_login(self, email: str, password: str) -> bool:
        """Automatically login to LinkedIn using credentials.
        
        Uses human-like typing delays and handles common challenges
        (verification prompts, security checks).
        """
        logger.info("Starting automated LinkedIn login...")

        self.driver.get("https://www.linkedin.com/login")
        self._human_delay(2, 4)

        try:
            # Find and fill email field
            email_field = self.driver.ele("css:input#username, input[name='session_key']", timeout=10)
            if not email_field:
                logger.error("Could not find email input field")
                return False

            email_field.clear()
            self._human_delay(0.5, 1)
            # Type email character by character (human-like)
            email_field.input(email, clear=True)
            self._human_delay(0.5, 1.5)

            # Find and fill password field
            pass_field = self.driver.ele("css:input#password, input[name='session_password']", timeout=5)
            if not pass_field:
                logger.error("Could not find password input field")
                return False

            pass_field.clear()
            self._human_delay(0.3, 0.8)
            pass_field.input(password, clear=True)
            self._human_delay(0.5, 1)

            # Click sign in button
            sign_in_btn = self.driver.ele(
                "css:button[type='submit'], button[data-litms-control-urn='login-submit']",
                timeout=5
            )
            if sign_in_btn:
                self._human_delay(0.5, 1)
                sign_in_btn.click()
            else:
                logger.warning("Sign-in button not found — trying Enter key")
                pass_field.input('\n')

            # Wait for login to process
            self._human_delay(4, 6)

            # Check for security challenge / verification
            if self._handle_security_challenge():
                logger.info("Security challenge handled")

            # Verify login success
            if self._is_logged_in():
                logger.info("LinkedIn auto-login successful!")
                self._save_cookies()
                return True

            # Check if we're on a challenge page
            current_url = self.driver.url
            if "challenge" in current_url or "checkpoint" in current_url:
                logger.warning("LinkedIn security challenge detected — waiting 60s for manual resolution")
                print("\n[!] LinkedIn security challenge detected.")
                print("    Please complete the verification in the browser window.")
                print("    Waiting 60 seconds...\n")
                
                for i in range(20):
                    time.sleep(3)
                    if self._is_logged_in():
                        logger.info("Login successful after security challenge!")
                        self._save_cookies()
                        return True
                
                logger.error("Security challenge not resolved in time")
                return False

            # Check for wrong credentials
            error_el = self.driver.ele(
                "css:div#error-for-username, div#error-for-password, div.form__label--error",
                timeout=2
            )
            if error_el:
                logger.error("LinkedIn login failed — invalid credentials: %s", error_el.text.strip()[:100])
                return False

            logger.error("LinkedIn login failed — unknown reason (URL: %s)", current_url[:80])
            return False

        except Exception as e:
            logger.error("LinkedIn auto-login error: %s", e)
            return False

    def _handle_security_challenge(self) -> bool:
        """Handle common LinkedIn security challenges after login."""
        try:
            # Check for "Remember this device" or "Verify email" prompts
            skip_btn = self.driver.ele(
                "css:button[data-litms-control-urn='login-remember-me-skip'], "
                "button.secondary-action, "
                "a.secondary-action",
                timeout=3
            )
            if skip_btn:
                skip_btn.click()
                self._human_delay(1, 2)
                return True

            # Check for "Got it" or "Dismiss" buttons
            dismiss_btn = self.driver.ele(
                "css:button.artdeco-modal__dismiss, "
                "button[data-test-modal-close-btn], "
                "button.msg-overlay-bubble-header__control--new-convo-btn",
                timeout=2
            )
            if dismiss_btn:
                dismiss_btn.click()
                self._human_delay(0.5, 1)
                return True

        except Exception:
            pass
        return False

    def _manual_login(self) -> bool:
        """Fall back to manual login if no credentials available."""
        logger.info("MANUAL LOGIN REQUIRED — No credentials in .env file")
        
        self.driver.get("https://www.linkedin.com/login")
        self._human_delay(2, 3)

        print("\n" + "=" * 50)
        print("[!] LINKEDIN MANUAL LOGIN REQUIRED")
        print("=" * 50)
        print("No credentials found in .env file.")
        print("Please log into LinkedIn in the browser window.")
        print("Waiting up to 90 seconds...")
        print("=" * 50 + "\n")

        for i in range(30):
            time.sleep(3)
            if self._is_logged_in():
                logger.info("Manual login successful!")
                self._save_cookies()
                return True
            if i % 10 == 9:
                remaining = 90 - (i + 1) * 3
                print(f"[..] Still waiting... ({remaining}s remaining)")

        logger.error("Manual login timeout — 90 seconds elapsed")
        return False

    # ------------------------------------------------------------------
    # Pass 1: Collect job cards (fast, low risk)
    # ------------------------------------------------------------------
    def _collect_job_cards(
        self, keyword: str, location: str, remaining: int
    ) -> list[dict]:
        """
        Scroll through search results and collect card metadata using DrissionPage.
        """
        url = self._build_search_url(keyword, location)
        logger.info("Loading search URL: %s", url[:100])

        self.driver.get(url)
        self._human_delay(3, 5)

        cards = []

        for scroll_round in range(self.config.max_scrolls):
            if len(cards) >= remaining:
                break

            card_elements = self.driver.eles(
                "css:div.job-card-container, li.jobs-search-results__list-item, "
                "div.job-card-list, li.ember-view.occludable-update, "
                "div.base-search-card, li > div.base-card"
            )

            for el in card_elements:
                if len(cards) >= remaining:
                    break

                card_data = self._parse_job_card(el)
                if card_data:
                    link = card_data.get("link", "")
                    if self._is_already_scraped(link):
                        continue
                    if any(c.get("link") == link for c in cards):
                        continue
                    cards.append(card_data)

            self.driver.scroll.to_bottom()
            self._human_delay(1.5, 3)

            see_more = self.driver.ele("css:button.infinite-scroller__show-more-button", timeout=0.1)
            if see_more:
                try:
                    see_more.click()
                    self._human_delay(2, 4)
                except Exception:
                    pass

        return cards

    def _parse_job_card(self, card_element) -> Optional[dict]:
        """Extract metadata from a DrissionPage element."""
        try:
            title_el = card_element.ele(
                "css:a.base-card__full-link, span.sr-only, "
                "a.job-card-list__title, a.job-card-container__link, "
                "a.disabled.ember-view.job-card-container__link", timeout=0.1
            )
            if not title_el:
                return None
            title = title_el.text.strip().split("\n")[0]
            link = title_el.attr("href") or ""
            if "?" in link:
                link = link.split("?")[0]

            if not title:
                return None

            company_el = card_element.ele(
                "css:a.hidden-nested-link, span.job-card-container__primary-description, "
                "a.job-card-container__company-name, "
                "span.job-card-container__company-name", timeout=0.1
            )
            company = company_el.text.strip() if company_el else ""

            loc_el = card_element.ele(
                "css:span.job-search-card__location, "
                "css:li.job-card-container__metadata-item, "
                "span.job-card-container__metadata-wrapper", timeout=0.1
            )
            location = loc_el.text.strip() if loc_el else ""

            easy_apply = "No"
            apply_badge = card_element.ele(
                "css:li.job-card-container__apply-method, "
                "span.job-card-container__easy-apply-icon", timeout=0.1
            )
            if apply_badge or ("easy apply" in card_element.text.lower()):
                easy_apply = "Yes"

            return {
                "title": title,
                "company": company,
                "location": location,
                "link": link,
                "easy_apply": easy_apply,
                "platform": "LinkedIn",
                "experience": "",
                "skills": "",
                "salary": "",
                "description": "",
                "posted_date": "",
            }

        except Exception as e:
            logger.debug("Failed to parse LinkedIn card: %s", e)
            return None

    # ------------------------------------------------------------------
    # Pass 2: Fetch full details (selective, heavier)
    # ------------------------------------------------------------------
    def _fetch_job_details(
        self, cards: list[dict], max_fetches: int
    ) -> list[dict]:
        """
        Open top N job links and extract full details.
        Cards beyond max_fetches are returned with partial data.
        """
        detailed_jobs = []
        detail_count = 0

        for i, card in enumerate(cards):
            if detail_count >= max_fetches:
                # Return remaining cards with partial data
                detailed_jobs.append(card)
                continue

            link = card.get("link", "")
            if not link:
                detailed_jobs.append(card)
                continue

            logger.info(
                "Pass 2: Fetching details %d/%d — %s",
                detail_count + 1, min(max_fetches, len(cards)),
                card.get("title", "")[:50],
            )

            try:
                details = self._retry(self._extract_job_details, link)
                if details:
                    # Merge card data with details
                    card.update(details)
                detail_count += 1
            except Exception as e:
                logger.warning("Failed to get details for %s: %s", link[:60], e)

            detailed_jobs.append(card)
            self.jobs_collected = detailed_jobs  # Update for crash recovery
            self._human_delay()

        return detailed_jobs

    def _extract_job_details(self, job_url: str) -> Optional[dict]:
        """Navigate to a job page and extract full details."""
        self.driver.get(job_url)
        self._human_delay(2, 4)

        details = {}

        wrapper = self.driver.ele(
            "css:div.jobs-description, div.show-more-less-html, div.jobs-box__html-content", timeout=10
        )
        if not wrapper:
            logger.debug("Job detail page timeout: %s", job_url[:60])
            return None

        desc_el = self.driver.ele(
            "css:div.jobs-description__content, div.show-more-less-html__markup, div.jobs-box__html-content", timeout=1
        )
        if desc_el:
            show_more = self.driver.ele(
                "css:button.show-more-less-html__button--more, button[aria-label='Show more']", timeout=0.1
            )
            if show_more:
                try:
                    show_more.click()
                    self._human_delay(0.5, 1)
                except Exception:
                    pass

            details["description"] = desc_el.text.strip()

        criteria_els = self.driver.eles(
            "css:li.jobs-unified-top-card__job-insight, span.jobs-unified-top-card__workplace-type"
        )
        for el in criteria_els:
            text = el.text.strip().lower()
            if "year" in text or "experience" in text or "yr" in text:
                details["experience"] = el.text.strip()
                break

        if not details.get("experience") and details.get("description"):
            exp_match = re.search(
                r"(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\s*(?:years?|yrs?)",
                details["description"],
                re.IGNORECASE,
            )
            if exp_match:
                details["experience"] = exp_match.group(0)
            else:
                exp_match = re.search(
                    r"(\d+\.?\d*)\+?\s*(?:years?|yrs?)",
                    details["description"],
                    re.IGNORECASE,
                )
                if exp_match:
                    details["experience"] = exp_match.group(0)

        if details.get("description"):
            desc_lower = details["description"].lower()
            found_skills = []
            for skill in self.config.profile_skills + self.config.required_skills_any:
                if skill.lower() in desc_lower:
                    found_skills.append(skill)
            details["skills"] = ", ".join(list(dict.fromkeys(found_skills)))

        salary_el = self.driver.ele(
            "css:span.jobs-unified-top-card__salary, div.salary-main-rail__data-body", timeout=0.1
        )
        if salary_el:
            details["salary"] = salary_el.text.strip()

        date_el = self.driver.ele(
            "css:span.jobs-unified-top-card__posted-date, span.posted-time-ago__text", timeout=0.1
        )
        if date_el:
            details["posted_date"] = date_el.text.strip()

        return details if details else None

    # ------------------------------------------------------------------
    # URL builders
    # ------------------------------------------------------------------
    def _build_search_url(self, keyword: str, location: str) -> str:
        """Build LinkedIn job search URL with filters."""
        # Map experience range to LinkedIn experience level codes
        # LinkedIn f_E codes: 1=Internship, 2=Entry, 3=Associate, 4=Mid-Senior, 5=Director, 6=Executive
        experience_levels = self._map_experience_to_linkedin_levels()
        
        params = {
            "keywords": keyword,
            "location": location,
            "f_TPR": f"r{self.config.date_posted_days * 86400}",  # Time period in seconds
            "sortBy": "R",  # Relevance
        }
        
        # Add experience level filter if mapped
        if experience_levels:
            params["f_E"] = ",".join(experience_levels)
        
        base = "https://www.linkedin.com/jobs/search/"
        return f"{base}?{urllib.parse.urlencode(params)}"
    
    def _map_experience_to_linkedin_levels(self) -> list:
        """
        Map config experience_range to LinkedIn experience level codes.
        
        LinkedIn codes:
        - 1: Internship (0 years)
        - 2: Entry level (0-2 years)
        - 3: Associate (2-5 years)
        - 4: Mid-Senior level (5-10 years)
        - 5: Director (10+ years)
        - 6: Executive (15+ years)
        """
        min_exp = self.config.experience_range.get('min', 0)
        max_exp = self.config.experience_range.get('max', 10)
        
        levels = []
        
        # Internship (0 years)
        if min_exp == 0:
            levels.append("1")
        
        # Entry level (0-2 years)
        if min_exp <= 2:
            levels.append("2")
        
        # Associate (2-5 years)
        if min_exp <= 5 and max_exp >= 2:
            levels.append("3")
        
        # Mid-Senior (5-10 years)
        if min_exp <= 10 and max_exp >= 5:
            levels.append("4")
        
        # Director (10+ years)
        if max_exp >= 10:
            levels.append("5")
        
        # Executive (15+ years)
        if max_exp >= 15:
            levels.append("6")
        
        return levels
