"""
Browser Pool Manager for parallel scraping.

Manages browser instances across multiple threads to prevent port collisions
and session conflicts. Assigns unique debug ports and user data paths per thread.

Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import threading
from pathlib import Path
from typing import Dict, Optional, Set
from DrissionPage import ChromiumPage, ChromiumOptions
from src.common.logger import get_logger

logger = get_logger("browser_pool_manager")

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = PROJECT_ROOT / "data" / "profiles"


class BrowserPoolManager:
    """
    Manages browser instances for parallel scraping.
    
    Features:
    - Unique port assignment (9222, 9223, 9224, etc.)
    - Unique user_data_path per thread
    - Browser instance tracking and reuse
    - Cleanup methods to close browsers and release ports
    """
    
    def __init__(self, base_port: int = 9222, max_browsers: int = 4):
        """
        Initialize the browser pool manager.
        
        Args:
            base_port: Starting port for debug listening (default: 9222)
            max_browsers: Maximum number of concurrent browser instances
        """
        self.base_port = base_port
        self.max_browsers = max_browsers
        
        # Thread-safe data structures
        self._lock = threading.Lock()
        self._available_ports: Set[int] = set(range(base_port, base_port + max_browsers))
        self._assigned_ports: Dict[int, int] = {}  # thread_id -> port
        self._browsers: Dict[int, ChromiumPage] = {}  # thread_id -> browser
        self._user_data_paths: Dict[int, Path] = {}  # thread_id -> path
        
        logger.info(
            "BrowserPoolManager initialized (base_port=%d, max_browsers=%d)",
            base_port, max_browsers
        )
    
    def get_browser(
        self,
        headless: bool = False,
        page_load_timeout: int = 30,
        proxy: str = "",
        user_agent: str = "",
        profile_name: str = "default",
        reuse: bool = True
    ) -> ChromiumPage:
        """
        Get a browser instance for the current thread.
        
        Args:
            headless: Run in headless mode
            page_load_timeout: Max seconds to wait for page loads
            proxy: Proxy URL (format: http://ip:port)
            user_agent: Custom user-agent string
            profile_name: Base name for the profile
            reuse: Whether to reuse existing browser for this thread
        
        Returns:
            ChromiumPage instance ready to use
        
        Raises:
            RuntimeError: If no ports are available (max browsers reached)
        """
        thread_id = threading.get_ident()
        
        with self._lock:
            # Check if browser already exists for this thread and reuse is enabled
            if reuse and thread_id in self._browsers:
                logger.info("Reusing existing browser for thread %d", thread_id)
                return self._browsers[thread_id]
            
            # Assign a port
            if thread_id not in self._assigned_ports:
                if not self._available_ports:
                    raise RuntimeError(
                        f"No available ports. Maximum {self.max_browsers} browsers reached."
                    )
                
                port = min(self._available_ports)
                self._available_ports.remove(port)
                self._assigned_ports[thread_id] = port
                logger.info("Assigned port %d to thread %d", port, thread_id)
            else:
                port = self._assigned_ports[thread_id]
            
            # Generate persistent user_data_path based only on profile_name
            user_data_path = PROFILES_DIR / profile_name
            user_data_path.mkdir(parents=True, exist_ok=True)
            self._user_data_paths[thread_id] = user_data_path
            
            logger.info(
                "Creating browser for thread %d (port=%d, headless=%s, profile=%s)",
                thread_id, port, headless, user_data_path.name
            )
        
        # Create browser outside the lock to avoid blocking other threads
        browser = self._create_browser(
            port=port,
            user_data_path=user_data_path,
            headless=headless,
            page_load_timeout=page_load_timeout,
            proxy=proxy,
            user_agent=user_agent
        )
        
        with self._lock:
            self._browsers[thread_id] = browser
        
        return browser
    
    def _create_browser(
        self,
        port: int,
        user_data_path: Path,
        headless: bool,
        page_load_timeout: int,
        proxy: str,
        user_agent: str
    ) -> ChromiumPage:
        """
        Create a browser instance with the specified configuration.
        
        Args:
            port: Debug listening port
            user_data_path: Path for user data storage
            headless: Run in headless mode
            page_load_timeout: Max seconds to wait for page loads
            proxy: Proxy URL
            user_agent: Custom user-agent string
        
        Returns:
            ChromiumPage instance
        """
        options = ChromiumOptions()
        
        # Set user data path
        options.set_user_data_path(str(user_data_path))
        
        # Set debug port
        options.set_argument(f"--remote-debugging-port={port}")
        
        # Window size
        options.set_argument("--window-size=1920,1080")
        if not headless:
            options.set_argument("--start-maximized")
        
        # Stealth enhancements
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--no-first-run")
        options.set_argument("--no-service-autorun")
        options.set_argument("--no-default-browser-check")
        options.set_argument("--disable-infobars")
        options.set_argument("--disable-popup-blocking")
        options.set_argument("--disable-notifications")
        options.set_argument("--disable-geolocation")
        options.set_argument("--disable-dev-shm-usage")
        
        # Block permissions
        options.set_pref("profile.default_content_setting_values.geolocation", 2)
        options.set_pref("profile.default_content_setting_values.notifications", 2)
        options.set_pref("profile.default_content_setting_values.media_stream_mic", 2)
        options.set_pref("profile.default_content_setting_values.media_stream_camera", 2)
        options.set_pref("credentials_enable_service", False)
        options.set_pref("profile.password_manager_enabled", False)
        
        # Headless mode
        if headless:
            options.headless(True)
        
        # User-agent
        if user_agent:
            options.set_user_agent(user_agent)
        
        # Proxy
        if proxy:
            options.set_proxy(proxy)
        
        # Disable auto port (we're managing ports manually)
        options.auto_port(False)
        
        # Set the address explicitly
        options.set_address(f"127.0.0.1:{port}")
        
        # Create browser
        try:
            page = ChromiumPage(addr_or_opts=options)
            page.set.timeouts(base=page_load_timeout, page_load=page_load_timeout)
            logger.info("Browser created successfully on port %d", port)
            return page
        except Exception as e:
            logger.error("Failed to create browser on port %d: %s", port, e)
            raise
    
    def close_browser(self, thread_id: Optional[int] = None) -> None:
        """
        Close browser for the specified thread and release its port.
        
        Args:
            thread_id: Thread ID (defaults to current thread)
        """
        if thread_id is None:
            thread_id = threading.get_ident()
        
        with self._lock:
            if thread_id in self._browsers:
                try:
                    self._browsers[thread_id].quit()
                    logger.info("Closed browser for thread %d", thread_id)
                except Exception as e:
                    logger.warning("Error closing browser for thread %d: %s", thread_id, e)
                finally:
                    del self._browsers[thread_id]
            
            if thread_id in self._assigned_ports:
                port = self._assigned_ports[thread_id]
                self._available_ports.add(port)
                del self._assigned_ports[thread_id]
                logger.info("Released port %d from thread %d", port, thread_id)
            
            if thread_id in self._user_data_paths:
                del self._user_data_paths[thread_id]
    
    def close_all_browsers(self) -> None:
        """Close all browser instances and release all ports."""
        with self._lock:
            thread_ids = list(self._browsers.keys())
        
        for thread_id in thread_ids:
            self.close_browser(thread_id)
        
        logger.info("All browsers closed")
    
    def get_assigned_port(self, thread_id: Optional[int] = None) -> Optional[int]:
        """
        Get the port assigned to a thread.
        
        Args:
            thread_id: Thread ID (defaults to current thread)
        
        Returns:
            Port number or None if no port assigned
        """
        if thread_id is None:
            thread_id = threading.get_ident()
        
        with self._lock:
            return self._assigned_ports.get(thread_id)
    
    def get_user_data_path(self, thread_id: Optional[int] = None) -> Optional[Path]:
        """
        Get the user data path assigned to a thread.
        
        Args:
            thread_id: Thread ID (defaults to current thread)
        
        Returns:
            Path object or None if no path assigned
        """
        if thread_id is None:
            thread_id = threading.get_ident()
        
        with self._lock:
            return self._user_data_paths.get(thread_id)
    
    def get_available_ports(self) -> Set[int]:
        """Get the set of currently available ports."""
        with self._lock:
            return self._available_ports.copy()
    
    def get_active_browser_count(self) -> int:
        """Get the number of currently active browsers."""
        with self._lock:
            return len(self._browsers)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup all browsers."""
        self.close_all_browsers()
