"""
Base scraper — abstract base class providing the scraper contract
and common anti-bot behaviors (delays, scrolling, cookie management).
All platform-specific scrapers inherit from this.
"""

import random
import time
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from DrissionPage import ChromiumPage

from pydantic import ValidationError
from src.models.job_schema import JobSchema
from src.common.logger import get_logger

logger = get_logger("base_scraper")


class BaseScraper(ABC):
    """
    Abstract base class for all platform scrapers.

    Subclasses must implement:
        - scrape() → list[dict]
        - platform_name (property)
    """

    def __init__(
        self,
        config,
        known_links: Optional[set] = None,
        driver: Optional["ChromiumPage"] = None,
    ):
        """
        Args:
            config: Config singleton from settings.py.
            known_links: Set of job links already in master file (for fresh-only mode).
            driver: Optional pre-created DrissionPage browser driver.
        """
        self.config = config
        self.known_links = known_links or set()
        self.driver = driver
        self.jobs_collected: list[dict] = []

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'Naukri', 'LinkedIn')."""
        ...

    @abstractmethod
    def scrape(self) -> list[dict]:
        """
        Execute the scraping logic.

        Returns:
            List of raw job dicts with keys:
                title, company, location, experience, skills, salary,
                description, posted_date, link, platform, easy_apply
        """
        ...

    def validate_job(self, job_data: dict) -> Optional[JobSchema]:
        """
        Validate a single job dict against the JobSchema.
        
        Args:
            job_data: Raw job dictionary from scraper
            
        Returns:
            JobSchema instance if valid, None if validation fails
            
        Validates: Requirements 4.3, 4.4, 4.5
        """
        try:
            job_schema = JobSchema.from_dict(job_data)
            return job_schema
        except ValidationError as e:
            logger.warning(
                "[%s] Job validation failed for '%s' at '%s': %s",
                self.platform_name,
                job_data.get("title", "Unknown"),
                job_data.get("company", "Unknown"),
                e
            )
            return None
        except Exception as e:
            logger.error(
                "[%s] Unexpected validation error: %s",
                self.platform_name,
                e
            )
            return None
    
    def validate_jobs(self, jobs: list[dict]) -> list[dict]:
        """
        Validate a list of job dicts against the JobSchema.
        
        Args:
            jobs: List of raw job dictionaries from scraper
            
        Returns:
            List of validated job dicts (invalid jobs are filtered out)
            
        Validates: Requirements 4.3, 4.4, 4.5
        """
        validated_jobs = []
        invalid_count = 0
        
        for job_data in jobs:
            job_schema = self.validate_job(job_data)
            if job_schema:
                validated_jobs.append(job_schema.to_dict())
            else:
                invalid_count += 1
        
        if invalid_count > 0:
            logger.warning(
                "[%s] Filtered out %d invalid jobs (validation failures)",
                self.platform_name,
                invalid_count
            )
        
        logger.info(
            "[%s] Schema validation: %d/%d jobs passed",
            self.platform_name,
            len(validated_jobs),
            len(jobs)
        )
        
        return validated_jobs

    # ------------------------------------------------------------------
    # Fresh-only check
    # ------------------------------------------------------------------
    def _is_already_scraped(self, link: str) -> bool:
        """Check if a job link is already known (for fresh-only mode)."""
        if not self.config.only_new_since_last_run:
            return False
        if not link:
            return False
        is_known = link.strip() in self.known_links
        if is_known:
            logger.debug("Skipping known job: %s", link[:80])
        return is_known

    # ------------------------------------------------------------------
    # Human-like behavior
    # ------------------------------------------------------------------
    def _human_delay(self, min_sec: float = None, max_sec: float = None):
        """Sleep for a random duration to mimic human behavior."""
        mn = min_sec or self.config.delay_range[0]
        mx = max_sec or self.config.delay_range[1]
        delay = random.uniform(mn, mx)
        time.sleep(delay)

    def _random_scroll(self, count: int = None):
        """Scroll the page randomly to mimic human browsing."""
        if not self.driver:
            return
        scroll_count = count or random.randint(2, 5)
        pause = self.config.scroll_pause

        for _ in range(scroll_count):
            scroll_amount = random.randint(300, 800)
            self.driver.scroll.down(scroll_amount)
            time.sleep(random.uniform(pause * 0.5, pause * 1.5))

    def _scroll_to_bottom(self):
        """Scroll to the bottom of the page incrementally."""
        if not self.driver:
            return
        pause = self.config.scroll_pause

        for i in range(self.config.max_scrolls):
            old_height = self.driver.run_js("return document.body.scrollHeight")
            self.driver.scroll.to_bottom()
            time.sleep(random.uniform(pause, pause * 2))

            new_height = self.driver.run_js("return document.body.scrollHeight")
            if new_height == old_height:
                logger.debug("Reached bottom of page after %d scrolls", i + 1)
                break

    # ------------------------------------------------------------------
    # Cookie management
    # ------------------------------------------------------------------
    def _save_cookies(self):
        """Save browser cookies (Handled natively by DrissionPage profiles)."""
        logger.debug("Cookies are persisted natively via DrissionPage user profile")

    def _load_cookies(self) -> bool:
        """Load cookies (Handled natively by DrissionPage profiles)."""
        logger.debug("Cookies are loaded natively via DrissionPage user profile")
        return True

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------
    def _retry(self, func, *args, **kwargs):
        """
        Retry a function up to max_retries times.
        Returns the result or raises the last exception.
        """
        last_exc = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                logger.warning(
                    "[%s] Attempt %d/%d failed: %s",
                    self.platform_name, attempt, self.config.max_retries, e,
                )
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay)
        raise last_exc

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def close(self):
        """Close the browser driver if we own it."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("[%s] Browser closed", self.platform_name)
            except Exception:
                pass
