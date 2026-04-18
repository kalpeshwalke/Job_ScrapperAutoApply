"""
main.py — Job Scraper Orchestrator with AI Auto-Apply

Entry point that coordinates the entire scraping pipeline with two modes:
1. Scraping Mode: Scrape jobs from platforms, validate career pages
2. Auto-Apply Mode: Apply to validated jobs using AI

Scraping Mode Pipeline:
1. Load config
2. Initialize logger
3. Load existing data (for dedup / fresh-only)
4. Run enabled scrapers (Naukri → LinkedIn)
5. Apply filters
6. Cross-platform deduplication (DeduplicationEngine)
7. Validate career page URLs
8. Save to Excel with validation results
9. Log summary

Auto-Apply Mode Pipeline:
1. Load config and Excel data
2. Filter jobs where Career_Page_Valid = "Yes" AND Applied = "No"
3. Initialize AI provider
4. Apply to each job using FSM orchestrator
5. Update Excel with application results
6. Log performance metrics
"""

import sys
import time
import traceback
import pandas as pd
from datetime import datetime
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Config
from src.common.logger import get_logger
from src.common.filters import filter_jobs
from src.common.cache_layer import CacheLayer
from src.common.deduplication_engine import DeduplicationEngine
from src.common.scraper_manager import ScraperManager
from src.common.browser_pool_manager import BrowserPoolManager
from src.common.rate_limiter import RateLimiter as ScraperRateLimiter
from src.common.excel_writer import (
    load_existing_data,
    get_known_links,
    deduplicate,
    save_to_excel,
    save_to_excel_with_validation,
)
from src.scrapers.naukri_scraper import NaukriScraper
from src.scrapers.linkedin_scraper import LinkedInScraper
from src.scrapers.indeed_scraper import IndeedScraper
from src.scrapers.foundit_scraper import FounditScraper

# AI Auto-Apply imports
# AI Auto-Apply imports from new src/ai_auto_apply structure
from src.ai_auto_apply.ui.cli_menu import CLIMenu
from src.ai_auto_apply.core.career_page_validator import CareerPageValidator
from src.ai_auto_apply.providers.ai_provider import AIProviderFactory
from src.ai_auto_apply.core.orchestrator_v2 import FSMOrchestratorV2
from src.ai_auto_apply.config.rate_limiter_ai import RateLimiter as AIRateLimiter
from src.ai_auto_apply.core.structured_logger import StructuredLogger

logger = get_logger("main")


def execute_apply_mode(config):
    """Execute auto-apply mode: apply to validated jobs using AI."""
    start_time = time.time()
    orchestrator = None
    structured_logger = None
    
    # Performance metrics tracking
    performance_metrics = {
        'total_jobs_processed': 0,
        'successful_applications': 0,
        'failed_applications': 0,
        'average_time_per_job': 0.0,
        'total_execution_time': 0.0
    }

    print("\n" + "=" * 60)
    print("[*] AUTO-APPLY MODE -- Starting")
    print("=" * 60 + "\n")

    try:
        # ------------------------------------------------------------------
        # 1. Check if auto_apply is configured and enabled
        # ------------------------------------------------------------------
        if not hasattr(config, 'auto_apply_config'):
            print("[!] Auto-apply configuration not found in config.yaml")
            print("    Please add 'auto_apply' section to your config.yaml")
            return
        
        auto_apply_config = config.auto_apply_config
        
        if not auto_apply_config.get('enabled', False):
            print("[!] Auto-apply is disabled in config.yaml")
            print("    Set 'auto_apply.enabled: true' to enable")
            return
        
        # ------------------------------------------------------------------
        # 2. Load master Excel file
        # ------------------------------------------------------------------
        try:
            logger.info("Loading master Excel file: %s", config.master_file_path)
            df = pd.read_excel(config.master_file_path)
            
            # Ensure required columns exist
            required_columns = ['Career_Page_Valid', 'Applied']
            for col in required_columns:
                if col not in df.columns:
                    logger.error("Required column '%s' not found in Excel file", col)
                    print(f"[!] Required column '{col}' not found in Excel file")
                    print("    Please run Scraping Mode first to populate this column")
                    return

            # Map Excel column names to internal canonical names if necessary
            column_mapping = {
                'Job Title': 'title',
                'Job_Title': 'title',
                'Company Career Page': 'career_page_url',
                'Careers_URL': 'career_page_url',
                'company': 'company',          # typically lowercase already or 'Company'
                'Company': 'company',
            }
            df.rename(columns=column_mapping, inplace=True)
            
            logger.info("Loaded %d jobs from Excel", len(df))
        except Exception as e:
            logger.error("Failed to load Excel file: %s", e)
            print(f"[!] Failed to load Excel file: {e}")
            return

        # ------------------------------------------------------------------
        # 3. Filter jobs for auto-apply
        # ------------------------------------------------------------------
        # Filter jobs where Career_Page_Valid = "Yes" AND Applied = "No"
        filtered_df = df[
            (df['Career_Page_Valid'] == 'Yes') & 
            (df['Applied'] == 'No')
        ].copy()
        
        if len(filtered_df) == 0:
            print("[!] No jobs available for auto-apply")
            print("    Check that:")
            print("    1. Career_Page_Valid = 'Yes' for some jobs")
            print("    2. Applied = 'No' for those jobs")
            print("    3. You have run Scraping Mode recently")
            return
        
        logger.info("Found %d jobs for auto-apply (Career_Page_Valid='Yes', Applied='No')", len(filtered_df))
        print(f"[*] Found {len(filtered_df)} jobs ready for auto-apply")

        # ------------------------------------------------------------------
        # 4. Initialize AI provider
        # ------------------------------------------------------------------
        try:
            ai_provider_name = auto_apply_config.get('ai_provider', 'gemini')
            ai_model = auto_apply_config.get('ai_model', 'gemini-2.0-flash-exp')
            
            logger.info("Initializing AI provider: %s (%s)", ai_provider_name, ai_model)
            print(f"[*] Using AI provider: {ai_provider_name} ({ai_model})")
            
            # Initialize structured logger for provider selection
            structured_logger = StructuredLogger("main", auto_apply_config.get('logging', {}))
            structured_logger.log_provider_selection(
                provider=ai_provider_name,
                model=ai_model,
                reason="User configuration"
            )
            
            provider = AIProviderFactory.create_provider(
                config=auto_apply_config
            )
            
            # Validate provider availability
            if not provider.validate_availability():
                logger.error("AI provider validation failed")
                print("[!] AI provider validation failed")
                print("    Check your API key and internet connection")
                return
            
            logger.info("AI provider initialized successfully")
        except ValueError as e:
            logger.error("AI provider initialization error: %s", e)
            print(f"[!] AI provider error: {e}")
            print("    Check your .env file for API keys")
            return
        except Exception as e:
            logger.error("Failed to initialize AI provider: %s", e)
            print(f"[!] Failed to initialize AI provider: {e}")
            return

        # ------------------------------------------------------------------
        # 5. Initialize FSM orchestrator
        # ------------------------------------------------------------------
        try:
            orchestrator = FSMOrchestratorV2(
                provider=provider,
                config=auto_apply_config,
                excel_path=config.master_file_path
            )
            logger.info("FSMOrchestratorV2 initialized")
        except Exception as e:
            logger.error("Failed to initialize FSM orchestrator: %s", e)
            print(f"[!] Failed to initialize FSM orchestrator: {e}")
            return

        # ------------------------------------------------------------------
        # 6. Initialize rate limiter for AI API
        # ------------------------------------------------------------------
        rate_limiter = None
        if auto_apply_config.get('rate_limiting', {}).get('enabled', False):
            try:
                rate_limiter = AIRateLimiter(
                    requests_per_minute=auto_apply_config['rate_limiting'].get('requests_per_minute', 15),
                    requests_per_day=auto_apply_config['rate_limiting'].get('requests_per_day', 1500)
                )
                logger.info("AI rate limiter initialized")
            except Exception as e:
                logger.warning("Failed to initialize AI rate limiter: %s", e)
                rate_limiter = None

        # ------------------------------------------------------------------
        # 7. Process each job
        # ------------------------------------------------------------------
        print(f"\n[*] Starting auto-apply for {len(filtered_df)} jobs...")
        print("=" * 60)
        
        try:
            for idx, row in filtered_df.iterrows():
                job_start_time = time.time()
                job_index = idx  # Excel row index
                
                logger.info("Processing job %d/%d: %s at %s", 
                        idx + 1, len(filtered_df), row.get('title', 'Unknown'), row.get('company', 'Unknown'))
                
                print(f"\n[{idx + 1}/{len(filtered_df)}] {row.get('title', 'Unknown')} at {row.get('company', 'Unknown')}")
                
                # Apply rate limiting if enabled
                if rate_limiter:
                    try:
                        rate_limiter.acquire()
                    except Exception as e:
                        logger.warning("Rate limit exceeded: %s", e)
                        print(f"[!] Rate limit exceeded: {e}")
                        break
                
                # Prepare job data for FSM
                job_data = {
                    'title': row.get('title', ''),
                    'company': row.get('company', ''),
                    'career_url': row.get('career_page_url', ''),
                    'excel_index': job_index,
                    'user_details': auto_apply_config.get('user_details', {})
                }
                
                # Add resume path if configured
                resume_path = auto_apply_config.get('resume_path', '')
                if resume_path:
                    job_data['resume_path'] = resume_path
                
                # Execute FSM for this job
                try:
                    result = orchestrator.apply_to_job(job_data)
                    
                    # Track performance metrics
                    performance_metrics['total_jobs_processed'] += 1
                    if result['status'] == 'success':
                        performance_metrics['successful_applications'] += 1
                        print(f"   [OK] Success: {result.get('reason', 'Applied successfully')}")
                    else:
                        performance_metrics['failed_applications'] += 1
                        print(f"   [FAIL] Failed: {result.get('reason', 'Unknown error')}")
                    
                    # Calculate job processing time
                    job_time = time.time() - job_start_time
                    logger.info("Job processed in %.2f seconds (status: %s)", job_time, result['status'])
                    
                except Exception as e:
                    logger.error("FSM error for job at %s: %s", row.get('company', 'Unknown'), e, exc_info=True)
                    performance_metrics['failed_applications'] += 1
                    print(f"   [ERROR] Error: {str(e)[:100]}")
                
                # Small delay between jobs (not artificial, just for logging)
                time.sleep(0.5)

        except KeyboardInterrupt:
            logger.warning("Batch interrupted by user (Ctrl+C)")
            print("\n\n[!] Interrupted by user. Cleaning up...")

        finally:
            # ALWAYS close browser — even on Ctrl+C, even on exception
            try:
                orchestrator.close_browser()
            except Exception:
                pass

        # ------------------------------------------------------------------
        # 9. Calculate performance metrics
        # ------------------------------------------------------------------
        performance_metrics['total_execution_time'] = time.time() - start_time
        
        if performance_metrics['total_jobs_processed'] > 0:
            performance_metrics['average_time_per_job'] = (
                performance_metrics['total_execution_time'] / performance_metrics['total_jobs_processed']
            )
        
        # ------------------------------------------------------------------
        # 9. Print summary
        # ------------------------------------------------------------------
        print("\n" + "=" * 60)
        print("  AUTO-APPLY MODE -- Summary")
        print("=" * 60)
        print(f"  Total jobs processed:      {performance_metrics['total_jobs_processed']}")
        print(f"  Successful applications:   {performance_metrics['successful_applications']}")
        print(f"  Failed applications:       {performance_metrics['failed_applications']}")
        print(f"  Success rate:              {(performance_metrics['successful_applications'] / performance_metrics['total_jobs_processed'] * 100):.1f}%")
        print(f"  Average time per job:      {performance_metrics['average_time_per_job']:.2f}s")
        print(f"  Total execution time:      {performance_metrics['total_execution_time']:.2f}s")
        print("=" * 60)
        
        logger.info(
            "Auto-apply summary: processed=%d, success=%d, failed=%d, total_time=%.2fs",
            performance_metrics['total_jobs_processed'],
            performance_metrics['successful_applications'],
            performance_metrics['failed_applications'],
            performance_metrics['total_execution_time']
        )
    
        # Log performance metrics with structured logger
        if structured_logger:
            structured_logger.log_performance_metrics(
                metrics_type="auto_apply_summary",
                metrics=performance_metrics
            )
    except Exception as e:
        logger.error("Auto-apply mode failed with a fatal error: %s", e, exc_info=True)
        print(f"\n[!] Fatal Error: {e}")
    finally:
        # Grand resource cleanup
        if orchestrator:
            try:
                orchestrator.close()
                logger.info("FSM Orchestrator closed")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Helper function to store jobs in cache
# ---------------------------------------------------------------------------
def _store_jobs_in_cache(cache: CacheLayer, jobs: list, ttl: int):
    """Store scraped jobs in cache."""
    stored_count = 0
    for job in jobs:
        try:
            cache.store(job, ttl=ttl)
            stored_count += 1
        except Exception as e:
            logger.warning("Failed to store job in cache: %s", e)
    
    if stored_count > 0:
        logger.info("Stored %d jobs in cache (TTL: %d seconds)", stored_count, ttl)


def execute_scraping_mode(config):
    """Execute scraping mode: scrape jobs, validate career pages, save to Excel."""
    start_time = time.time()
    
    # Performance metrics tracking
    performance_metrics = {
        'cache_hits': 0,
        'cache_misses': 0,
        'jobs_per_platform': {},
        'execution_times_per_platform': {},
        'duplicates_removed': 0,
        'total_execution_time': 0.0,
        'career_pages_validated': 0,
        'career_pages_valid': 0,
        'career_pages_invalid': 0
    }

    print("\n" + "=" * 60)
    print("[*] SCRAPING MODE -- Starting")
    print("=" * 60 + "\n")

    try:
        # ------------------------------------------------------------------
        # 1. Initialize cache layer
        # ------------------------------------------------------------------
        cache = None
        if config.cache_enabled:
            try:
                cache = CacheLayer(db_path=config.cache_db_path)
                logger.info("Cache layer initialized: %s", config.cache_db_path)
                
                # Clear expired entries
                expired_count = cache.clear_expired()
                if expired_count > 0:
                    logger.info("Cleared %d expired cache entries", expired_count)
                
                # Log cache stats
                stats = cache.get_stats()
                logger.info("Cache stats: %d total, %d active, %d expired", 
                        stats["total_entries"], stats["active_entries"], stats["expired_entries"])
                
                # Track initial cache stats for hit/miss calculation
                initial_cache_entries = stats["active_entries"]
            except Exception as e:
                logger.warning("Failed to initialize cache layer: %s", e)
                cache = None
                initial_cache_entries = 0
        else:
            logger.info("Cache layer is disabled in config")
            initial_cache_entries = 0

        # ------------------------------------------------------------------
        # 2. Load existing data for dedup / fresh-only mode
        # ------------------------------------------------------------------
        known_links = set()
        if config.only_new_since_last_run:
            # Load known links from master file
            known_links = get_known_links(config.master_file_path)
            
            # If cache is enabled, also load known links from cache
            if cache:
                try:
                    # Query all non-expired URLs from cache
                    # Note: This is a simplified approach. In production, you might want
                    # to add a method to CacheLayer to get all non-expired URLs
                    cache_stats = cache.get_stats()
                    logger.info("Fresh-only mode: %d known links from master file, cache has %d active entries",
                            len(known_links), cache_stats["active_entries"])
                except Exception as e:
                    logger.warning("Failed to load cache entries for fresh-only mode: %s", e)
            
            if known_links:
                logger.info("Fresh-only mode: %d known links loaded — will skip these", len(known_links))
            else:
                logger.info("Fresh-only mode: no existing data — will scrape everything")

        existing_df = load_existing_data(config.master_file_path)

        # ------------------------------------------------------------------
        # 3. Run scrapers
        # ------------------------------------------------------------------
        all_raw_jobs = []
        naukri_driver = None
        is_partial = False  # Track if any scrapers failed
        successful_platforms = []
        failed_platforms = []
        
        # Check if parallel execution is enabled
        if config.parallelization_enabled:
            logger.info("Using parallel execution mode")
            
            # Initialize BrowserPoolManager
            browser_pool = BrowserPoolManager(
                base_port=9222,
                max_browsers=config.max_workers
            )
            
            # Initialize RateLimiter for scraping delays
            rate_limiter = ScraperRateLimiter(
                default_min_delay=config.random_delay_min,
                default_max_delay=config.random_delay_max
            )
            
            # Configure per-platform rate limits
            rate_limiter.configure_platform("Naukri", config.random_delay_min, config.random_delay_max)
            rate_limiter.configure_platform("LinkedIn", config.random_delay_min, config.random_delay_max)
            rate_limiter.configure_platform("Indeed", config.random_delay_min, config.random_delay_max)
            rate_limiter.configure_platform("Foundit", config.random_delay_min, config.random_delay_max)
            
            # Build list of scraper classes
            scraper_classes = [
                NaukriScraper,
                LinkedInScraper,
                IndeedScraper,
                FounditScraper
            ]
            
            # Initialize ScraperManager
            scraper_manager = ScraperManager(
                config=config,
                max_workers=config.max_workers,
                per_scraper_timeout=config.per_scraper_timeout
            )
            
            try:
                # Execute all scrapers in parallel
                results = scraper_manager.scrape_all_platforms(
                    scraper_classes=scraper_classes,
                    known_links=known_links,
                    browser_pool_manager=browser_pool
                )
                
                # Extract results
                all_raw_jobs = results['all_jobs']
                is_partial = results['is_partial']
                successful_platforms = results['successful_platforms']
                failed_platforms = results['failed_platforms']
                
                # Track performance metrics: per-platform execution times and jobs collected
                performance_metrics['execution_times_per_platform'] = results['execution_times']
                for platform, jobs in results['results_by_platform'].items():
                    performance_metrics['jobs_per_platform'][platform] = len(jobs)
                
                # Store jobs in cache if enabled
                if cache and all_raw_jobs:
                    _store_jobs_in_cache(cache, all_raw_jobs, config.cache_ttl)
                
                # Log results by platform
                for platform, jobs in results['results_by_platform'].items():
                    logger.info("%s: %d jobs scraped", platform, len(jobs))
                
                # Log platform success/failure summary
                if successful_platforms:
                    logger.info("[OK] Successful platforms: %s", ", ".join(successful_platforms))
                if failed_platforms:
                    logger.warning("[FAIL] Failed platforms: %s", ", ".join(failed_platforms))
                
                # Log errors if any
                if results['errors']:
                    for platform, error in results['errors'].items():
                        logger.error("%s scraper failed: %s", platform, error)
            
            finally:
                # Cleanup browser pool
                browser_pool.close_all_browsers()
        
        else:
            logger.info("Using sequential execution mode (parallel disabled)")
            
            # --- Naukri ---
            if config.naukri_enabled:
                platform_start = time.time()
                try:
                    naukri = NaukriScraper(config=config, known_links=known_links)
                    naukri_jobs = naukri.scrape()
                    all_raw_jobs.extend(naukri_jobs)
                    platform_time = time.time() - platform_start
                    
                    logger.info("Naukri: %d jobs scraped", len(naukri_jobs))
                    successful_platforms.append("Naukri")
                    
                    # Track performance metrics
                    performance_metrics['jobs_per_platform']['Naukri'] = len(naukri_jobs)
                    performance_metrics['execution_times_per_platform']['Naukri'] = platform_time
                    
                    # Store jobs in cache if enabled
                    if cache and naukri_jobs:
                        _store_jobs_in_cache(cache, naukri_jobs, config.cache_ttl)
                    
                    # Keep browser open for career page search
                    naukri_driver = naukri.driver
                except Exception as e:
                    logger.error("Naukri scraper crashed: %s", e)
                    logger.debug(traceback.format_exc())
                    failed_platforms.append("Naukri")
                    is_partial = True
            else:
                logger.info("Naukri scraper is disabled in config")

            # --- LinkedIn ---
            if config.linkedin_enabled:
                platform_start = time.time()
                try:
                    linkedin = LinkedInScraper(config=config, known_links=known_links)
                    linkedin_jobs = linkedin.scrape()
                    all_raw_jobs.extend(linkedin_jobs)
                    platform_time = time.time() - platform_start
                    
                    logger.info("LinkedIn: %d jobs scraped", len(linkedin_jobs))
                    successful_platforms.append("LinkedIn")
                    
                    # Track performance metrics
                    performance_metrics['jobs_per_platform']['LinkedIn'] = len(linkedin_jobs)
                    performance_metrics['execution_times_per_platform']['LinkedIn'] = platform_time
                    
                    # Store jobs in cache if enabled
                    if cache and linkedin_jobs:
                        _store_jobs_in_cache(cache, linkedin_jobs, config.cache_ttl)
                except Exception as e:
                    logger.error("LinkedIn scraper crashed: %s", e)
                    logger.debug(traceback.format_exc())
                    failed_platforms.append("LinkedIn")
                    is_partial = True
                finally:
                    try:
                        linkedin.close()
                    except Exception:
                        pass
            else:
                logger.info("LinkedIn scraper is disabled in config")
            
            # --- Indeed ---
            if config.indeed_enabled:
                platform_start = time.time()
                try:
                    indeed = IndeedScraper(config=config, known_links=known_links)
                    indeed_jobs = indeed.scrape()
                    all_raw_jobs.extend(indeed_jobs)
                    platform_time = time.time() - platform_start
                    
                    logger.info("Indeed: %d jobs scraped", len(indeed_jobs))
                    successful_platforms.append("Indeed")
                    
                    # Track performance metrics
                    performance_metrics['jobs_per_platform']['Indeed'] = len(indeed_jobs)
                    performance_metrics['execution_times_per_platform']['Indeed'] = platform_time
                    
                    # Store jobs in cache if enabled
                    if cache and indeed_jobs:
                        _store_jobs_in_cache(cache, indeed_jobs, config.cache_ttl)
                except Exception as e:
                    logger.error("Indeed scraper crashed: %s", e)
                    logger.debug(traceback.format_exc())
                    failed_platforms.append("Indeed")
                    is_partial = True
                finally:
                    try:
                        indeed.close()
                    except Exception:
                        pass
            else:
                logger.info("Indeed scraper is disabled in config")
            
            # --- Foundit ---
            if config.foundit_enabled:
                platform_start = time.time()
                try:
                    foundit = FounditScraper(config=config, known_links=known_links)
                    foundit_jobs = foundit.scrape()
                    all_raw_jobs.extend(foundit_jobs)
                    platform_time = time.time() - platform_start
                    
                    logger.info("Foundit: %d jobs scraped", len(foundit_jobs))
                    successful_platforms.append("Foundit")
                    
                    # Track performance metrics
                    performance_metrics['jobs_per_platform']['Foundit'] = len(foundit_jobs)
                    performance_metrics['execution_times_per_platform']['Foundit'] = platform_time
                    
                    # Store jobs in cache if enabled
                    if cache and foundit_jobs:
                        _store_jobs_in_cache(cache, foundit_jobs, config.cache_ttl)
                except Exception as e:
                    logger.error("Foundit scraper crashed: %s", e)
                    logger.debug(traceback.format_exc())
                    failed_platforms.append("Foundit")
                    is_partial = True
                finally:
                    try:
                        foundit.close()
                    except Exception:
                        pass
            else:
                logger.info("Foundit scraper is disabled in config")
            
            # Log platform success/failure summary
            if successful_platforms:
                logger.info("[OK] Successful platforms: %s", ", ".join(successful_platforms))
            if failed_platforms:
                logger.warning("[FAIL] Failed platforms: %s", ", ".join(failed_platforms))

        # ------------------------------------------------------------------
        # 4. Apply filters
        # ------------------------------------------------------------------
        if not all_raw_jobs:
            logger.warning("No jobs collected from any platform — exiting")
            _print_summary(0, 0, 0, 0, start_time, performance_metrics)
            return

        logger.info("Applying filters to %d raw jobs...", len(all_raw_jobs))
        filtered_jobs = filter_jobs(
            jobs=all_raw_jobs,
            required_skills_any=config.required_skills_any,
            exclude_title_keywords=config.exclude_title_keywords,
            exclude_role_keywords=config.exclude_role_keywords,
            experience_range=config.experience_range,
            max_experience_years=config.max_experience_years,
        )
        logger.info("After filtering: %d jobs remain (rejected %d)",
                    len(filtered_jobs), len(all_raw_jobs) - len(filtered_jobs))

        # ------------------------------------------------------------------
        # 5. Cross-platform deduplication using DeduplicationEngine
        # ------------------------------------------------------------------
        logger.info("Applying cross-platform deduplication to %d filtered jobs...", len(filtered_jobs))
        dedup_engine = DeduplicationEngine()
        deduplicated_jobs = dedup_engine.deduplicate(filtered_jobs)
        duplicates_removed = len(filtered_jobs) - len(deduplicated_jobs)
        
        # Track performance metrics: duplicates removed
        performance_metrics['duplicates_removed'] = duplicates_removed
        
        logger.info("After cross-platform dedup: %d unique jobs (removed %d duplicates)",
                    len(deduplicated_jobs), duplicates_removed)

        # ------------------------------------------------------------------
        # 6. Deduplicate against existing data in master file
        # ------------------------------------------------------------------
        new_jobs = deduplicate(deduplicated_jobs, existing_df)
        logger.info("After dedup against master file: %d new unique jobs", len(new_jobs))

        # ------------------------------------------------------------------
        # 7. Validate career page URLs (Task 18)
        # ------------------------------------------------------------------
        validation_results = {}
        if new_jobs and hasattr(config, 'auto_apply_config') and config.auto_apply_config.get('validation', {}).get('enabled', False):
            logger.info("Validating career page URLs for %d new jobs...", len(new_jobs))
            
            # Initialize career page validator
            validator = CareerPageValidator(config.auto_apply_config.get('validation', {}))
            
            # Validate each job's career page URL
            for job in new_jobs:
                career_url = job.get('career_page_url', '')
                company_name = job.get('company', '')
                
                if career_url:
                    status, reason = validator.validate(career_url, company_name)
                    validation_results[career_url] = (status, reason)
                    
                    # Track validation metrics
                    performance_metrics['career_pages_validated'] += 1
                    if status == "Yes":
                        performance_metrics['career_pages_valid'] += 1
                    elif status == "No":
                        performance_metrics['career_pages_invalid'] += 1
            
            logger.info("Career page validation complete: %d valid, %d invalid, %d unchecked",
                    performance_metrics['career_pages_valid'],
                    performance_metrics['career_pages_invalid'],
                    performance_metrics['career_pages_validated'] - 
                    (performance_metrics['career_pages_valid'] + performance_metrics['career_pages_invalid']))
        else:
            logger.info("Career page validation disabled or no new jobs")

        # ------------------------------------------------------------------
        # 8. Save to Excel with validation results (Task 18)
        # ------------------------------------------------------------------
        if new_jobs:
            # Determine if we should save partial results
            should_save = True
            if is_partial and not config.save_partial_on_crash:
                logger.warning("Partial results detected but save_partial_on_crash is disabled")
                should_save = False
            
            if should_save:
                # Determine run status
                run_status = "Partial" if is_partial else "Complete"
                
                # Save with validation results if available
                if validation_results:
                    save_to_excel_with_validation(
                        new_jobs=new_jobs,
                        file_path=config.master_file_path,
                        description_preview_chars=config.description_preview_chars,
                        include_full_description=config.include_full_description,
                        find_career_pages=config.find_company_career_pages,
                        driver=naukri_driver,  # Pass browser for Google search
                        is_partial=is_partial,
                        run_status=run_status,
                        validation_results=validation_results
                    )
                    logger.info("[OK] Saved %d new jobs with validation results to %s (Status: %s)", 
                            len(new_jobs), config.master_file_path, run_status)
                else:
                    save_to_excel(
                        new_jobs=new_jobs,
                        file_path=config.master_file_path,
                        description_preview_chars=config.description_preview_chars,
                        include_full_description=config.include_full_description,
                        find_career_pages=config.find_company_career_pages,
                        driver=naukri_driver,  # Pass browser for Google search
                        is_partial=is_partial,
                        run_status=run_status,
                    )
                    logger.info("[OK] Saved %d new jobs to %s (Status: %s)", 
                            len(new_jobs), config.master_file_path, run_status)
                
                # Log which platforms succeeded/failed
                if is_partial:
                    logger.info("Partial results saved:")
                    logger.info("  [OK] Successful: %s", ", ".join(successful_platforms) if successful_platforms else "None")
                    logger.info("  [FAIL] Failed: %s", ", ".join(failed_platforms) if failed_platforms else "None")
            else:
                logger.info("Skipping save due to partial results and save_partial_on_crash=False")
        else:
            logger.info("No new jobs to save — master file unchanged")
        
        # Close browser after saving
        if naukri_driver:
            try:
                naukri_driver.quit()
                logger.info("[Naukri] Browser closed")
                naukri_driver = None
            except Exception:
                pass

        # ------------------------------------------------------------------
        # 9. Email notification (if enabled)
        # ------------------------------------------------------------------
        if config.email_enabled and new_jobs:
            _send_email_notification(config, len(new_jobs))

        # ------------------------------------------------------------------
        # 10. Calculate cache hit/miss rates
        # ------------------------------------------------------------------
        if cache:
            try:
                final_stats = cache.get_stats()
                final_cache_entries = final_stats["active_entries"]
                
                # Calculate cache metrics
                # Cache hits = jobs that were already in cache (known_links from cache)
                # Cache misses = new jobs added to cache
                new_cache_entries = final_cache_entries - initial_cache_entries
                
                # Estimate cache hits based on known_links that came from cache
                # and new entries added
                if len(all_raw_jobs) > 0:
                    cache_hit_rate = (len(known_links) / (len(all_raw_jobs) + len(known_links))) * 100 if (len(all_raw_jobs) + len(known_links)) > 0 else 0
                    cache_miss_rate = 100 - cache_hit_rate
                else:
                    cache_hit_rate = 0
                    cache_miss_rate = 0
                
                performance_metrics['cache_hits'] = len(known_links)
                performance_metrics['cache_misses'] = len(all_raw_jobs)
                performance_metrics['cache_hit_rate'] = cache_hit_rate
                performance_metrics['cache_miss_rate'] = cache_miss_rate
                
                logger.info("Cache performance: %.1f%% hit rate (%d hits, %d misses)",
                        cache_hit_rate, len(known_links), len(all_raw_jobs))
            except Exception as e:
                logger.warning("Failed to calculate cache metrics: %s", e)

        # ------------------------------------------------------------------
        # 11. Calculate total execution time
        # ------------------------------------------------------------------
        performance_metrics['total_execution_time'] = time.time() - start_time

        # ------------------------------------------------------------------
        # 12. Summary with performance metrics
        # ------------------------------------------------------------------
        _print_summary(
            total_scraped=len(all_raw_jobs),
            after_filter=len(filtered_jobs),
            after_dedup=len(new_jobs),
            known_links_count=len(known_links),
            start_time=start_time,
            performance_metrics=performance_metrics,
        )
    except Exception as e:
        logger.error("Scraping mode failed with a fatal error: %s", e, exc_info=True)
        print(f"\n[!] Fatal Error: {e}")
    finally:
        # Final cleanup for any orphaned drivers
        if naukri_driver:
            try:
                naukri_driver.quit()
                logger.info("[Naukri] Browser closed (cleanup)")
            except Exception:
                pass


    # ------------------------------------------------------------------
    # 13. Calculating final metrics and cleanup
    # ------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------
def _print_summary(
    total_scraped: int,
    after_filter: int,
    after_dedup: int,
    known_links_count: int,
    start_time: float,
    performance_metrics: dict,
):
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    # Build performance metrics section
    perf_section = []
    
    # Per-platform execution times
    if performance_metrics.get('execution_times_per_platform'):
        perf_section.append("\n  Per-Platform Execution Times:")
        for platform, exec_time in performance_metrics['execution_times_per_platform'].items():
            jobs_count = performance_metrics['jobs_per_platform'].get(platform, 0)
            perf_section.append(f"    {platform:12s}: {exec_time:6.2f}s ({jobs_count} jobs)")
    
    # Cache metrics
    if 'cache_hit_rate' in performance_metrics:
        cache_hits = performance_metrics.get('cache_hits', 0)
        cache_misses = performance_metrics.get('cache_misses', 0)
        cache_hit_rate = performance_metrics.get('cache_hit_rate', 0)
        perf_section.append(f"\n  Cache Performance:")
        perf_section.append(f"    Hit rate:        {cache_hit_rate:.1f}%")
        perf_section.append(f"    Hits:            {cache_hits}")
        perf_section.append(f"    Misses:          {cache_misses}")
    
    # Deduplication metrics
    duplicates = performance_metrics.get('duplicates_removed', 0)
    if duplicates > 0:
        perf_section.append(f"\n  Deduplication:")
        perf_section.append(f"    Duplicates removed: {duplicates}")

    perf_text = "".join(perf_section) if perf_section else ""

    summary = f"""
{'=' * 60}
 JOB SCRAPER -- Summary
{'=' * 60}
  Total scraped:         {total_scraped}
  After filtering:       {after_filter}
  After dedup:           {after_dedup} (new jobs added)
  Known links skipped:   {known_links_count}
  Time elapsed:          {minutes}m {seconds}s
{perf_text}
{'=' * 60}
"""
    
    # Log performance metrics with structured logger
    try:
        from src.ai_auto_apply.core.structured_logger import StructuredLogger
        structured_logger = StructuredLogger("scraping", {})
        structured_logger.log_performance_metrics(
            metrics_type="scraping_summary",
            metrics={
                "total_scraped": total_scraped,
                "after_filter": after_filter,
                "after_dedup": after_dedup,
                "known_links_count": known_links_count,
                "elapsed_time": elapsed,
                "performance_metrics": performance_metrics
            }
        )
    except Exception as e:
        logger.warning("Failed to log structured metrics: %s", e)
    print(summary)
    logger.info(
        "Summary: scraped=%d, filtered=%d, new=%d, time=%dm%ds, duplicates_removed=%d",
        total_scraped, after_filter, after_dedup, minutes, seconds,
        performance_metrics.get('duplicates_removed', 0),
    )


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------
def _send_email_notification(config, new_job_count: int):
    """Send email notification about new jobs found."""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        email_cfg = config.email_config
        sender = email_cfg.get("sender_email", "")
        password = email_cfg.get("app_password", "")
        recipient = email_cfg.get("recipient_email", "")

        if not all([sender, password, recipient]):
            logger.warning("Email config incomplete — skipping notification")
            return

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = f"Job Scraper: {new_job_count} new jobs found!"

        body = f"""
        <html>
        <body>
        <h2>Job Scraper Report</h2>
        <p><strong>{new_job_count}</strong> new jobs were found and added to your master file.</p>
        <p>Open the Excel file to review and track your applications.</p>
        <hr>
        <p><em>Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        logger.info("Email notification sent to %s", recipient)

    except Exception as e:
        logger.warning("Failed to send email notification: %s", e)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------
def main():
    """Main orchestrator function with mode selection."""
    print("\n" + "=" * 60)
    print("[*] JOB SCRAPER -- Starting")
    print("=" * 60 + "\n")

    # ------------------------------------------------------------------
    # 1. Load configuration
    # ------------------------------------------------------------------
    logger.info("Loading configuration...")
    try:
        config = Config.load()
        logger.info("Config loaded successfully")
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        print(f"[!] Failed to load configuration: {e}")
        print("    Check your config.yaml file")
        return

    # ------------------------------------------------------------------
    # 2. Display CLI menu and get mode selection (Task 21)
    # ------------------------------------------------------------------
    try:
        mode = CLIMenu.display_menu()
    except KeyboardInterrupt:
        print("\n\n[!] Operation cancelled by user")
        return
    except Exception as e:
        logger.error("CLI menu error: %s", e)
        print(f"[!] Menu error: {e}")
        return

    # ------------------------------------------------------------------
    # 3. Execute selected mode
    # ------------------------------------------------------------------
    try:
        if mode == "scraping":
            # Scraping Mode (Tasks 18-19)
            execute_scraping_mode(config)
        
        elif mode == "apply":
            # Auto-Apply Mode (Task 20)
            # Check if auto_apply is configured
            if not hasattr(config, 'auto_apply_config'):
                print("\n[!] Auto-apply configuration not found")
                print("    Please add 'auto_apply' section to config.yaml")
                print("    See README.md for configuration instructions")
                return
            
            auto_apply_config = config.auto_apply_config
            execute_apply_mode(config)
    except KeyboardInterrupt:
        print("\n\n[!] Script stopped by user (Ctrl+C). Cleaning up...")
        logger.warning("Main execution interrupted by user")
    except Exception as e:
        logger.error("Unexpected error in main: %s", e, exc_info=True)
        print(f"\n[!] Unexpected error: {e}")
        
        # Safely check auto_apply_config (might not be defined if error occurred early)
        try:
            if hasattr(config, 'auto_apply_config'):
                auto_apply_config = config.auto_apply_config
                
                if not auto_apply_config.get('enabled', False):
                    print("\n[!] Auto-apply is disabled in config.yaml")
                    print("    Set 'auto_apply.enabled: true' to enable")
                    return
                
                # Check if user details are configured
                user_details = auto_apply_config.get('user_details', {})
                if not user_details.get('name') or not user_details.get('email'):
                    print("\n[!] User details not configured")
                    print("    Please add your details to config.yaml:")
                    print("    auto_apply:")
                    print("      user_details:")
                    print("        name: \"Your Name\"")
                    print("        email: \"your@email.com\"")
                    print("        phone: \"your_phone\"")
                    return
                
                execute_apply_mode(config)
        except Exception as inner_e:
            logger.error("Error in exception handler: %s", inner_e)
            print(f"\n[!] Failed to recover from error: {inner_e}")
    
    else:
        logger.error("Invalid mode selected: %s", mode)
        print(f"[!] Invalid mode: {mode}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Scraping interrupted by user")
        logger.info("Scraping interrupted by user (Ctrl+C)")
    except Exception as e:
        logger.critical("Fatal error: %s", e)
        logger.critical(traceback.format_exc())
        print(f"\n[ERROR] Fatal error: {e}")
        sys.exit(1)
