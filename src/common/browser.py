"""
Browser factory — creates a DrissionPage ChromiumPage instance.
Handles: ChromiumOptions setup, persistent user data profile for anti-bot evasion,
random user-agent, headless mode, page-load timeout, and window size.
"""

import random
import time
from pathlib import Path

from DrissionPage import ChromiumPage, ChromiumOptions
from src.common.logger import get_logger

logger = get_logger("browser")

# Base paths for profile storage
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = PROJECT_ROOT / "data" / "profiles"


def create_browser(
    headless: bool = False,
    chrome_version: int = 146,
    page_load_timeout: int = 30,
    proxy: str = "",
    user_agent: str = "",
    profile_name: str = "default",
) -> ChromiumPage:
    """
    Create and return a stealthed Chrome browser instance using DrissionPage.

    Args:
        headless: Run in headless mode (not recommended for LinkedIn).
        chrome_version: Major Chrome version (mostly unused in DP, but kept for signature).
        page_load_timeout: Max seconds to wait for page loads.
        proxy: Proxy URL (format: http://ip:port).
        user_agent: Custom user-agent string (optional).
        profile_name: Name of the local profile to persist cookies and history.

    Returns:
        ChromiumPage instance ready to use.
    """
    logger.info("Launching DrissionPage browser (headless=%s, profile=%s)", headless, profile_name)

    options = ChromiumOptions()

    # --- Profile Persistence ---
    # Store user data (cookies, cache, etc) locally. This is crucial for anti-bot bypass.
    profile_path = PROFILES_DIR / profile_name
    profile_path.mkdir(parents=True, exist_ok=True)
    options.set_user_data_path(str(profile_path))

    # --- Window size ---
    options.set_argument("--window-size=1920,1080")
    if not headless:
        options.set_argument("--start-maximized")

    # --- Stealth enhancements ---
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--no-first-run")
    options.set_argument("--no-service-autorun")
    options.set_argument("--no-default-browser-check")
    options.set_argument("--disable-infobars")
    options.set_argument("--disable-popup-blocking")
    options.set_argument("--disable-notifications")
    options.set_argument("--disable-geolocation")

    # Additional stealth (based on research)
    options.set_argument("--disable-dev-shm-usage")

    # Block permissions
    options.set_pref("profile.default_content_setting_values.geolocation", 2)
    options.set_pref("profile.default_content_setting_values.notifications", 2)
    options.set_pref("profile.default_content_setting_values.media_stream_mic", 2)
    options.set_pref("profile.default_content_setting_values.media_stream_camera", 2)
    options.set_pref("credentials_enable_service", False)
    options.set_pref("profile.password_manager_enabled", False)

    # --- Headless ---
    if headless:
        options.headless(True)

    # --- User-agent ---
    if user_agent:
        logger.info("Using custom User-Agent: %s", user_agent[:80])
        options.set_user_agent(user_agent)

    # --- Proxy ---
    if proxy:
        logger.info("Using Proxy: %s", proxy)
        options.set_proxy(proxy)

    # Disable generic webdriver marks
    options.auto_port(True)

    # --- Create driver ---
    try:
        page = ChromiumPage(addr_or_opts=options)
    except Exception as e:
        logger.error("Failed to launch DrissionPage browser: %s", e)
        raise e

    page.set.timeouts(base=page_load_timeout, page_load=page_load_timeout)

    logger.info("Browser launched successfully (DrissionPage)")
    return page


def human_delay(min_sec: float = 2.0, max_sec: float = 6.0):
    """Sleep for a random duration to mimic human behavior."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def random_scroll(page: ChromiumPage, scroll_count: int = 3, pause: float = 2.0):
    """Scroll the page randomly to mimic human browsing."""
    for _ in range(scroll_count):
        scroll_amount = random.randint(300, 800)
        page.scroll.down(scroll_amount)
        time.sleep(random.uniform(pause * 0.5, pause * 1.5))


def scroll_to_bottom(page: ChromiumPage, max_scrolls: int = 20, pause: float = 2.0):
    """Scroll to the very bottom of the page to trigger lazy loading."""
    for _ in range(max_scrolls):
        old_height = page.run_js("return document.body.scrollHeight")
        page.scroll.to_bottom()
        time.sleep(random.uniform(pause * 0.8, pause * 1.2))
        new_height = page.run_js("return document.body.scrollHeight")
        if new_height == old_height:
            break


def slow_type(element, text: str, min_delay: float = 0.05, max_delay: float = 0.15):
    """Type text character by character with random delays in DrissionPage."""
    for char in text:
        element.input(char)
        time.sleep(random.uniform(min_delay, max_delay))
