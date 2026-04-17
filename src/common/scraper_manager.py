"""
Scraper Manager with parallel executor for multi-platform scraping.

Orchestrates multiple platform scrapers with parallel execution, dynamic platform
detection, timeout enforcement, error isolation, and result aggregation.

Validates: Requirements 1.1, 1.2, 1.3, 7.1, 7.3, 7.4, 7.5, 11.2, 11.3, 12.2
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed, wait, FIRST_COMPLETED
from typing import List, Dict, Any, Optional, Type
from pathlib import Path

from src.scrapers.base_scraper import BaseScraper
from src.common.logger import get_logger

logger = get_logger("scraper_manager")


class ScraperManager:
    """
    Manages parallel execution of multiple platform scrapers.
    
    Features:
    - Parallel execution using ThreadPoolExecutor
    - Dynamic platform detection (scan for enabled scrapers)
    - Per-scraper timeout enforcement
    - Result aggregation from all scrapers
    - Error isolation (continue on individual scraper failure)
    - Partial results logging
    
    Validates: Requirements 1.1, 1.2, 1.3, 7.1, 7.3, 7.4, 7.5, 11.2, 11.3, 12.2
    """
    
    def __init__(
        self,
        config,
        max_workers: Optional[int] = None,
        per_scraper_timeout: Optional[int] = None
    ):
        """
        Initialize the scraper manager.
        
        Args:
            config: Config singleton from settings.py
            max_workers: Maximum number of concurrent scrapers (default: from config)
            per_scraper_timeout: Timeout per scraper in seconds (default: from config)
        """
        self.config = config
        self.max_workers = max_workers or getattr(config, 'max_workers', 4)
        self.per_scraper_timeout = per_scraper_timeout or getattr(config, 'per_scraper_timeout', 600)
        
        # Track execution results
        self._results: Dict[str, List[dict]] = {}
        self._errors: Dict[str, Exception] = {}
        self._execution_times: Dict[str, float] = {}
        self._lock = threading.Lock()
        
        logger.info(
            "ScraperManager initialized (max_workers=%d, timeout=%ds)",
            self.max_workers, self.per_scraper_timeout
        )
    
    def scrape_all_platforms(
        self,
        scraper_classes: List[Type[BaseScraper]],
        known_links: Optional[set] = None,
        browser_pool_manager=None
    ) -> Dict[str, Any]:
        """
        Execute all enabled scrapers in parallel.
        
        Args:
            scraper_classes: List of scraper classes to execute
            known_links: Set of known job links (for fresh-only mode)
            browser_pool_manager: Optional BrowserPoolManager instance
        
        Returns:
            Dictionary with:
                - all_jobs: Aggregated list of all jobs from all scrapers
                - results_by_platform: Dict mapping platform name to job list
                - errors: Dict mapping platform name to error (if any)
                - execution_times: Dict mapping platform name to execution time
                - successful_platforms: List of platform names that succeeded
                - failed_platforms: List of platform names that failed
        
        Validates: Requirements 1.1, 1.3, 7.1, 7.3, 7.5
        """
        logger.info("=" * 60)
        logger.info("Starting parallel scraper execution")
        logger.info("Enabled scrapers: %d", len(scraper_classes))
        logger.info("Max workers: %d", self.max_workers)
        logger.info("Per-scraper timeout: %ds", self.per_scraper_timeout)
        logger.info("=" * 60)
        
        # Detect enabled platforms dynamically
        enabled_scrapers = self._detect_enabled_scrapers(scraper_classes)
        
        if not enabled_scrapers:
            logger.warning("No enabled scrapers found")
            return self._empty_result()
        
        logger.info("Detected %d enabled platforms: %s",
                   len(enabled_scrapers),
                   ", ".join([s.__name__ for s in enabled_scrapers]))
        
        # Execute scrapers in parallel
        start_time = time.time()
        future_to_start_time = {}
        
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            # Submit all scraper tasks
            future_to_scraper = {}
            
            for scraper_class in enabled_scrapers:
                future = executor.submit(
                    self._execute_scraper,
                    scraper_class,
                    known_links,
                    browser_pool_manager
                )
                future_to_scraper[future] = scraper_class
                future_to_start_time[future] = time.time()
            
            # Monitor futures with timeout enforcement
            pending = set(future_to_scraper.keys())
            
            while pending:
                # Wait for any future to complete (short timeout for checking)
                done, still_pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                
                # Process completed futures
                for future in done:
                    scraper_class = future_to_scraper[future]
                    platform_name = self._get_platform_name(scraper_class)
                    
                    try:
                        result = future.result(timeout=0.01)  # Should be immediate
                        
                        with self._lock:
                            self._results[platform_name] = result['jobs']
                            self._execution_times[platform_name] = result['execution_time']
                        
                        logger.info(
                            "[%s] Completed successfully: %d jobs in %.2fs",
                            platform_name, len(result['jobs']), result['execution_time']
                        )
                    
                    except Exception as e:
                        with self._lock:
                            self._errors[platform_name] = e
                        logger.error("[%s] Failed with error: %s", platform_name, e)
                
                # Check for timeouts in still-pending futures
                for future in list(still_pending):
                    scraper_class = future_to_scraper[future]
                    platform_name = self._get_platform_name(scraper_class)
                    scraper_start_time = future_to_start_time[future]
                    elapsed = time.time() - scraper_start_time
                    
                    if elapsed >= self.per_scraper_timeout:
                        # Timeout exceeded - abandon this future
                        error = TimeoutError(f"Scraper exceeded timeout of {self.per_scraper_timeout}s")
                        with self._lock:
                            self._errors[platform_name] = error
                        logger.error("[%s] Timeout after %ds", platform_name, self.per_scraper_timeout)
                        future.cancel()  # Try to cancel (may not work if already running)
                        still_pending.remove(future)
                
                # Update pending set
                pending = still_pending
        finally:
            # Shutdown without waiting for timed-out threads
            executor.shutdown(wait=False)
        
        total_time = time.time() - start_time
        
        # Aggregate results
        return self._aggregate_results(total_time)
    
    def _detect_enabled_scrapers(
        self,
        scraper_classes: List[Type[BaseScraper]]
    ) -> List[Type[BaseScraper]]:
        """
        Dynamically detect which scrapers are enabled in configuration.
        
        Args:
            scraper_classes: List of all available scraper classes
        
        Returns:
            List of enabled scraper classes
        
        Validates: Requirements 11.2, 11.3, 12.2
        """
        enabled = []
        
        for scraper_class in scraper_classes:
            platform_name = self._get_platform_name(scraper_class)
            config_key = f"{platform_name.lower()}_enabled"
            
            # Check if platform is enabled in config
            is_enabled = getattr(self.config, config_key, False)
            
            if is_enabled:
                enabled.append(scraper_class)
                logger.debug("[%s] Enabled", platform_name)
            else:
                logger.debug("[%s] Disabled in configuration", platform_name)
        
        return enabled
    
    def _execute_scraper(
        self,
        scraper_class: Type[BaseScraper],
        known_links: Optional[set],
        browser_pool_manager
    ) -> Dict[str, Any]:
        """
        Execute a single scraper and measure execution time.
        
        Args:
            scraper_class: Scraper class to instantiate and execute
            known_links: Set of known job links
            browser_pool_manager: Optional BrowserPoolManager instance
        
        Returns:
            Dictionary with jobs list and execution_time
        
        Validates: Requirements 1.1, 7.1
        """
        platform_name = self._get_platform_name(scraper_class)
        logger.info("[%s] Starting scraper execution", platform_name)
        
        start_time = time.time()
        
        try:
            # Get browser from pool if available
            driver = None
            if browser_pool_manager:
                try:
                    # Get platform-specific browser config
                    browser_config = self._get_browser_config(platform_name)
                    driver = browser_pool_manager.get_browser(
                        headless=browser_config.get('headless', False),
                        page_load_timeout=self.config.page_load_timeout,
                        proxy=getattr(self.config, 'proxy', ''),
                        profile_name=f"{platform_name.lower()}_profile"
                    )
                except Exception as e:
                    logger.warning("[%s] Failed to get browser from pool: %s", platform_name, e)
            
            # Instantiate scraper
            scraper = scraper_class(
                config=self.config,
                known_links=known_links,
                driver=driver
            )
            
            # Execute scraping
            jobs = scraper.scrape()
            
            # Validate jobs against schema
            validated_jobs = scraper.validate_jobs(jobs)
            
            execution_time = time.time() - start_time
            
            return {
                'jobs': validated_jobs,
                'execution_time': execution_time
            }
        
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error("[%s] Scraper execution failed: %s", platform_name, e)
            raise
        
        finally:
            # Close browser if we own it (not from pool)
            if driver and not browser_pool_manager:
                try:
                    driver.quit()
                except Exception:
                    pass
    
    def _get_browser_config(self, platform_name: str) -> Dict[str, Any]:
        """
        Get platform-specific browser configuration.
        
        Args:
            platform_name: Name of the platform
        
        Returns:
            Dictionary with browser configuration
        """
        config_method = f"{platform_name.lower()}_browser_config"
        
        if hasattr(self.config, config_method):
            return getattr(self.config, config_method)
        
        # Default browser config
        return {
            'headless': getattr(self.config, 'headless', False),
            'profile_path': ''
        }
    
    def _get_platform_name(self, scraper_class: Type[BaseScraper]) -> str:
        """
        Get platform name from scraper class.
        
        Args:
            scraper_class: Scraper class
        
        Returns:
            Platform name string
        """
        # Try to get platform_name from class property
        try:
            # Create a temporary instance to access the property
            temp_instance = scraper_class.__new__(scraper_class)
            return temp_instance.platform_name
        except Exception:
            # Fallback: extract from class name (e.g., NaukriScraper -> Naukri)
            class_name = scraper_class.__name__
            return class_name.replace('Scraper', '')
    
    def _aggregate_results(self, total_time: float) -> Dict[str, Any]:
        """
        Aggregate results from all scrapers.
        
        Args:
            total_time: Total execution time in seconds
        
        Returns:
            Dictionary with aggregated results and metadata
        
        Validates: Requirements 1.3, 7.5
        """
        all_jobs = []
        results_by_platform = {}
        successful_platforms = []
        failed_platforms = []
        
        # Aggregate successful results
        for platform, jobs in self._results.items():
            results_by_platform[platform] = jobs
            all_jobs.extend(jobs)
            successful_platforms.append(platform)
        
        # Track failed platforms
        for platform in self._errors.keys():
            failed_platforms.append(platform)
            results_by_platform[platform] = []
        
        # Log summary
        logger.info("=" * 60)
        logger.info("Parallel scraping complete")
        logger.info("Total execution time: %.2fs", total_time)
        logger.info("Successful platforms: %d/%d",
                   len(successful_platforms),
                   len(successful_platforms) + len(failed_platforms))
        
        if successful_platforms:
            logger.info("  [OK] Succeeded: %s", ", ".join(successful_platforms))
            for platform in successful_platforms:
                jobs_count = len(self._results[platform])
                exec_time = self._execution_times.get(platform, 0)
                logger.info("    - %s: %d jobs in %.2fs", platform, jobs_count, exec_time)
        
        if failed_platforms:
            logger.warning("  [FAIL] Failed: %s", ", ".join(failed_platforms))
            for platform in failed_platforms:
                error = self._errors.get(platform, "Unknown error")
                logger.warning("    - %s: %s", platform, error)
        
        logger.info("Total jobs collected: %d", len(all_jobs))
        logger.info("=" * 60)
        
        return {
            'all_jobs': all_jobs,
            'results_by_platform': results_by_platform,
            'errors': self._errors.copy(),
            'execution_times': self._execution_times.copy(),
            'successful_platforms': successful_platforms,
            'failed_platforms': failed_platforms,
            'total_execution_time': total_time,
            'is_partial': len(failed_platforms) > 0
        }
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            'all_jobs': [],
            'results_by_platform': {},
            'errors': {},
            'execution_times': {},
            'successful_platforms': [],
            'failed_platforms': [],
            'total_execution_time': 0.0,
            'is_partial': False
        }
    
    def get_results(self) -> Dict[str, List[dict]]:
        """Get results by platform."""
        with self._lock:
            return self._results.copy()
    
    def get_errors(self) -> Dict[str, Exception]:
        """Get errors by platform."""
        with self._lock:
            return self._errors.copy()
    
    def get_execution_times(self) -> Dict[str, float]:
        """Get execution times by platform."""
        with self._lock:
            return self._execution_times.copy()
