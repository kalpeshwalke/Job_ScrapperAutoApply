"""
Settings module — loads and validates config.yaml.
Exposes a singleton Config object for use across the project.
"""

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

DATA_DIR = PROJECT_ROOT / "data"
COOKIES_DIR = DATA_DIR / "cookies"
OUTPUT_DIR = DATA_DIR / "output"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure directories exist
for _dir in [COOKIES_DIR, OUTPUT_DIR, LOGS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
class _Config:
    """Singleton configuration container loaded from config.yaml."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def load(self, config_path: str | Path | None = None):
        """Load and validate the YAML configuration file."""
        path = Path(config_path) if config_path else CONFIG_PATH
        if not path.exists():
            print(f"[ERROR] Config file not found: {path}")
            sys.exit(1)

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            print(f"[ERROR] Config file is empty or malformed: {path}")
            sys.exit(1)

        self._data = data
        self._validate()
        self._loaded = True
        return self

    # ------------------------------------------------------------------
    # Accessors (dot-notation style)
    # ------------------------------------------------------------------

    # --- Profile ---
    @property
    def profile_role(self) -> str:
        return self._data["profile"]["role"]

    @property
    def profile_experience(self) -> int:
        return self._data["profile"]["experience_years"]

    @property
    def profile_skills(self) -> list[str]:
        return self._data["profile"]["skills"]

    # --- Search ---
    @property
    def search_keywords(self) -> list[str]:
        return self._data["search"]["keywords"]

    @property
    def search_locations(self) -> list[str]:
        return self._data["search"]["locations"]

    @property
    def experience_range(self) -> dict:
        return self._data["search"]["experience_range"]

    @property
    def date_posted_days(self) -> int:
        return self._data["search"].get("date_posted_days", 7)

    @property
    def only_new_since_last_run(self) -> bool:
        return self._data["search"].get("only_new_since_last_run", True)

    # --- Filters ---
    @property
    def required_skills_any(self) -> list[str]:
        return self._data["filters"]["required_skills_any"]

    @property
    def exclude_title_keywords(self) -> list[str]:
        return self._data["filters"]["exclude_title_keywords"]

    @property
    def exclude_role_keywords(self) -> list[str]:
        return self._data["filters"]["exclude_role_keywords"]

    @property
    def max_experience_years(self) -> int:
        return self._data["filters"]["max_experience_years"]

    # --- Platforms ---
    @property
    def naukri_enabled(self) -> bool:
        return self._data["platforms"]["naukri"]["enabled"]

    @property
    def naukri_email(self) -> str:
        """Get Naukri email from environment variable or config file."""
        # Priority: Environment variable > Config file
        return os.getenv("NAUKRI_EMAIL") or self._data["platforms"]["naukri"].get("email", "")

    @property
    def naukri_password(self) -> str:
        """Get Naukri password from environment variable or config file."""
        # Priority: Environment variable > Config file
        return os.getenv("NAUKRI_PASSWORD") or self._data["platforms"]["naukri"].get("password", "")

    @property
    def naukri_max_jobs(self) -> int:
        return self._data["platforms"]["naukri"]["max_jobs"]

    @property
    def naukri_fetch_full_descriptions(self) -> bool:
        return self._data["platforms"]["naukri"].get("fetch_full_descriptions", False)

    @property
    def naukri_parallel_detail_fetch(self) -> int:
        return self._data["platforms"]["naukri"].get("parallel_detail_fetch", 5)

    @property
    def naukri_max_pages_per_search(self) -> int:
        return self._data["platforms"]["naukri"].get("max_pages_per_search", 3)

    @property
    def naukri_browser_config(self) -> dict:
        """Get Naukri browser configuration with safe defaults."""
        browser_config = self._data["platforms"]["naukri"].get("browser", {})
        return {
            "headless": browser_config.get("headless", False),
            "profile_path": browser_config.get("profile_path", "")
        }

    @property
    def linkedin_enabled(self) -> bool:
        return self._data["platforms"]["linkedin"]["enabled"]

    @property
    def linkedin_email(self) -> str:
        """Get LinkedIn email from environment variable or config file."""
        return os.getenv("LINKEDIN_EMAIL") or self._data["platforms"]["linkedin"].get("email", "")

    @property
    def linkedin_password(self) -> str:
        """Get LinkedIn password from environment variable or config file."""
        return os.getenv("LINKEDIN_PASSWORD") or self._data["platforms"]["linkedin"].get("password", "")

    @property
    def linkedin_max_jobs(self) -> int:
        return self._data["platforms"]["linkedin"]["max_jobs"]

    @property
    def linkedin_max_detail_fetches(self) -> int:
        return self._data["platforms"]["linkedin"].get("max_detail_fetches", 30)

    @property
    def linkedin_browser_config(self) -> dict:
        """Get LinkedIn browser configuration with safe defaults."""
        browser_config = self._data["platforms"]["linkedin"].get("browser", {})
        return {
            "headless": browser_config.get("headless", False),
            "profile_path": browser_config.get("profile_path", "")
        }

    @property
    def indeed_enabled(self) -> bool:
        return self._data["platforms"].get("indeed", {}).get("enabled", False)

    @property
    def indeed_max_jobs(self) -> int:
        return self._data["platforms"].get("indeed", {}).get("max_jobs", 50)

    @property
    def indeed_max_pages_per_search(self) -> int:
        return self._data["platforms"].get("indeed", {}).get("max_pages_per_search", 5)

    @property
    def indeed_browser_config(self) -> dict:
        """Get Indeed browser configuration with safe defaults."""
        browser_config = self._data["platforms"].get("indeed", {}).get("browser", {})
        return {
            "headless": browser_config.get("headless", False),
            "profile_path": browser_config.get("profile_path", "")
        }

    @property
    def foundit_enabled(self) -> bool:
        return self._data["platforms"].get("foundit", {}).get("enabled", False)

    @property
    def foundit_max_jobs(self) -> int:
        return self._data["platforms"].get("foundit", {}).get("max_jobs", 50)

    @property
    def foundit_max_pages_per_search(self) -> int:
        return self._data["platforms"].get("foundit", {}).get("max_pages_per_search", 5)

    @property
    def foundit_api_first(self) -> bool:
        return self._data["platforms"].get("foundit", {}).get("api_first", True)

    @property
    def foundit_browser_config(self) -> dict:
        """Get Foundit browser configuration with safe defaults."""
        browser_config = self._data["platforms"].get("foundit", {}).get("browser", {})
        return {
            "headless": browser_config.get("headless", True),
            "profile_path": browser_config.get("profile_path", "")
        }

    # --- Browser ---
    @property
    def headless(self) -> bool:
        return self._data["browser"]["headless"]

    @property
    def chrome_version_main(self) -> int:
        return self._data["browser"]["chrome_version_main"]

    @property
    def delay_range(self) -> tuple[int, int]:
        d = self._data["browser"]["random_delay"]
        return (d["min_seconds"], d["max_seconds"])
    
    @property
    def random_delay_min(self) -> float:
        """Get minimum random delay in seconds."""
        return float(self._data["browser"]["random_delay"]["min_seconds"])
    
    @property
    def random_delay_max(self) -> float:
        """Get maximum random delay in seconds."""
        return float(self._data["browser"]["random_delay"]["max_seconds"])

    @property
    def page_load_timeout(self) -> int:
        return self._data["browser"]["page_load_timeout"]

    @property
    def scroll_pause(self) -> int:
        return self._data["browser"]["scroll_pause_seconds"]

    @property
    def max_scrolls(self) -> int:
        return self._data["browser"]["max_scrolls"]

    # --- Resilience ---
    @property
    def max_retries(self) -> int:
        return self._data["resilience"]["max_retries"]

    @property
    def retry_delay(self) -> int:
        return self._data["resilience"]["retry_delay_seconds"]

    @property
    def save_partial_on_crash(self) -> bool:
        return self._data["resilience"]["save_partial_on_crash"]

    # --- Parallelization ---
    @property
    def parallelization_enabled(self) -> bool:
        return self._data.get("parallelization", {}).get("enabled", True)

    @property
    def max_workers(self) -> int:
        return self._data.get("parallelization", {}).get("max_workers", 4)

    @property
    def per_scraper_timeout(self) -> int:
        return self._data.get("parallelization", {}).get("per_scraper_timeout", 600)

    # --- Cache ---
    @property
    def cache_enabled(self) -> bool:
        return self._data.get("cache", {}).get("enabled", True)

    @property
    def cache_ttl(self) -> int:
        return self._data.get("cache", {}).get("ttl", 3600)

    @property
    def cache_backend(self) -> str:
        return self._data.get("cache", {}).get("backend", "sqlite")

    @property
    def cache_db_path(self) -> Path:
        db_path = self._data.get("cache", {}).get("db_path", "data/cache.db")
        return PROJECT_ROOT / db_path

    # --- Output ---
    @property
    def master_file_name(self) -> str:
        return self._data["output"]["master_file_name"]

    @property
    def master_file_path(self) -> Path:
        return OUTPUT_DIR / self.master_file_name

    @property
    def description_preview_chars(self) -> int:
        return self._data["output"]["description_preview_chars"]

    @property
    def include_full_description(self) -> bool:
        return self._data["output"]["include_full_description"]

    @property
    def find_company_career_pages(self) -> bool:
        return self._data["output"].get("find_company_career_pages", True)

    # --- Email ---
    @property
    def email_enabled(self) -> bool:
        return self._data["email"]["enabled"]

    @property
    def email_config(self) -> dict:
        """Get email config with credentials from environment variables."""
        config = self._data["email"].copy()
        # Override with environment variables if available
        config["sender_email"] = os.getenv("EMAIL_SENDER") or config.get("sender_email", "")
        config["app_password"] = os.getenv("EMAIL_APP_PASSWORD") or config.get("app_password", "")
        config["recipient_email"] = os.getenv("EMAIL_RECIPIENT") or config.get("recipient_email", "")
        return config

    # --- Scheduling ---
    @property
    def schedule_time(self) -> str:
        return self._data["scheduling"]["daily_time"]

    # --- Network ---
    @property
    def proxy(self) -> str:
        return self._data.get("network", {}).get("proxy", "")

    @property
    def user_agent_rotation(self) -> bool:
        return self._data.get("network", {}).get("user_agent_rotation", True)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate(self):
        """Validate that all required config sections and keys exist."""
        required_sections = [
            "profile", "search", "filters",
            "platforms", "browser", "resilience", "output",
        ]
        for section in required_sections:
            if section not in self._data:
                print(f"[ERROR] Missing required config section: '{section}'")
                sys.exit(1)

        # Validate nested required keys
        required_keys = {
            "profile": ["role", "experience_years", "skills"],
            "search": ["keywords", "locations", "experience_range"],
            "filters": ["required_skills_any", "exclude_title_keywords", "max_experience_years"],
            "platforms": ["naukri", "linkedin"],
            "browser": ["headless", "chrome_version_main", "random_delay"],
            "resilience": ["max_retries", "retry_delay_seconds", "save_partial_on_crash"],
            "output": ["master_file_name"],
        }
        for section, keys in required_keys.items():
            for key in keys:
                if key not in self._data[section]:
                    print(f"[ERROR] Missing config key: '{section}.{key}'")
                    sys.exit(1)

        # Validate optional sections with safe defaults
        self._validate_optional_sections()

    def _validate_optional_sections(self):
        """Validate optional configuration sections and apply safe defaults."""
        # Parallelization validation
        if "parallelization" in self._data:
            parallel_config = self._data["parallelization"]
            if "max_workers" in parallel_config:
                max_workers = parallel_config["max_workers"]
                if not isinstance(max_workers, int) or max_workers < 1:
                    print(f"[WARNING] Invalid parallelization.max_workers: {max_workers}. Using default: 4")
                    parallel_config["max_workers"] = 4
            if "per_scraper_timeout" in parallel_config:
                timeout = parallel_config["per_scraper_timeout"]
                if not isinstance(timeout, int) or timeout < 1:
                    print(f"[WARNING] Invalid parallelization.per_scraper_timeout: {timeout}. Using default: 600")
                    parallel_config["per_scraper_timeout"] = 600

        # Cache validation
        if "cache" in self._data:
            cache_config = self._data["cache"]
            if "ttl" in cache_config:
                ttl = cache_config["ttl"]
                if not isinstance(ttl, int) or ttl < 0:
                    print(f"[WARNING] Invalid cache.ttl: {ttl}. Using default: 3600")
                    cache_config["ttl"] = 3600
            if "backend" in cache_config:
                backend = cache_config["backend"]
                if backend not in ["sqlite", "duckdb"]:
                    print(f"[WARNING] Invalid cache.backend: {backend}. Using default: sqlite")
                    cache_config["backend"] = "sqlite"

        # Platform-specific browser config validation
        for platform in ["naukri", "linkedin", "indeed", "foundit"]:
            if platform in self._data.get("platforms", {}):
                platform_config = self._data["platforms"][platform]
                if "browser" in platform_config:
                    browser_config = platform_config["browser"]
                    if "headless" in browser_config and not isinstance(browser_config["headless"], bool):
                        print(f"[WARNING] Invalid platforms.{platform}.browser.headless. Using default: False")
                        browser_config["headless"] = False
                
                # Validate max_jobs
                if "max_jobs" in platform_config:
                    max_jobs = platform_config["max_jobs"]
                    if not isinstance(max_jobs, int) or max_jobs < 1:
                        print(f"[WARNING] Invalid platforms.{platform}.max_jobs: {max_jobs}. Using default: 50")
                        platform_config["max_jobs"] = 50
                
                # Validate max_pages_per_search
                if "max_pages_per_search" in platform_config:
                    max_pages = platform_config["max_pages_per_search"]
                    if not isinstance(max_pages, int) or max_pages < 1:
                        print(f"[WARNING] Invalid platforms.{platform}.max_pages_per_search: {max_pages}. Using default: 5")
                        platform_config["max_pages_per_search"] = 5

    # --- AI Auto-Apply ---
    @property
    def auto_apply_config(self) -> dict:
        """Get auto-apply configuration with safe defaults."""
        auto_apply = self._data.get("auto_apply", {})
        
        # Apply defaults if section exists but keys are missing
        if auto_apply:
            defaults = {
                "enabled": False,
                "ai_provider": "gemini",
                "ai_model": "gemini-2.0-flash-exp",
                "resume_path": "",
                "user_details": {"name": "", "email": "", "phone": ""},
                "validation": {"enabled": True, "keyword_threshold": 2, "timeout_seconds": 30, "verify_company_name": True},
                "fsm": {"max_iterations": 20, "page_load_timeout": 30},
                "rate_limiting": {"enabled": True, "requests_per_minute": 15, "requests_per_day": 1500},
                "retry": {"max_retries": 3, "backoff_multiplier": 2, "initial_delay_seconds": 1},
                "logging": {"log_ai_decisions": True, "log_dom_interactions": True, "log_api_usage": True},
                "ollama_base_url": "http://localhost:11434"
            }
            
            # Merge with defaults
            for key, default_value in defaults.items():
                if key not in auto_apply:
                    auto_apply[key] = default_value
                elif isinstance(default_value, dict) and isinstance(auto_apply[key], dict):
                    # Recursively merge nested dicts
                    for sub_key, sub_default in default_value.items():
                        if sub_key not in auto_apply[key]:
                            auto_apply[key][sub_key] = sub_default
        
        return auto_apply

    def __repr__(self):
        return f"<Config loaded={self._loaded}>"


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------
Config = _Config()
