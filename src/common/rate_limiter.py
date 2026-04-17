"""
Rate limiter with per-platform request tracking.

This module implements rate limiting to avoid triggering anti-bot protections
when scraping multiple platforms concurrently. Each platform has independent
rate tracking with configurable delays.

Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5
"""

import time
import random
from typing import Dict, Optional
from threading import Lock


class RateLimiter:
    """
    Rate limiter that enforces per-platform request delays.
    
    Tracks request timestamps independently for each platform and enforces
    configurable delays with human-like randomization.
    """
    
    def __init__(self, default_min_delay: float = 1.0, default_max_delay: float = 3.0):
        """
        Initialize the rate limiter.
        
        Args:
            default_min_delay: Default minimum delay in seconds between requests
            default_max_delay: Default maximum delay in seconds between requests
        """
        self._platform_timestamps: Dict[str, float] = {}
        self._platform_configs: Dict[str, Dict[str, float]] = {}
        self._default_min_delay = default_min_delay
        self._default_max_delay = default_max_delay
        self._lock = Lock()
    
    def configure_platform(self, platform: str, min_delay: float, max_delay: float) -> None:
        """
        Configure rate limiting for a specific platform.
        
        Args:
            platform: Platform name (e.g., "naukri", "linkedin", "indeed")
            min_delay: Minimum delay in seconds between requests
            max_delay: Maximum delay in seconds between requests
        """
        with self._lock:
            self._platform_configs[platform] = {
                "min_delay": min_delay,
                "max_delay": max_delay
            }
    
    def wait_if_needed(self, platform: str) -> float:
        """
        Wait if necessary to enforce rate limit for the platform.
        
        This method checks the last request timestamp for the platform and
        sleeps if insufficient time has passed since the last request.
        
        Args:
            platform: Platform name
            
        Returns:
            The actual delay applied in seconds (0 if no delay was needed)
        """
        with self._lock:
            current_time = time.time()
            
            # Get platform-specific config or use defaults
            config = self._platform_configs.get(platform, {
                "min_delay": self._default_min_delay,
                "max_delay": self._default_max_delay
            })
            
            min_delay = config["min_delay"]
            max_delay = config["max_delay"]
            
            # Generate random delay within configured range
            required_delay = random.uniform(min_delay, max_delay)
            
            # Check if we need to wait
            if platform in self._platform_timestamps:
                last_request_time = self._platform_timestamps[platform]
                time_since_last = current_time - last_request_time
                
                if time_since_last < required_delay:
                    sleep_time = required_delay - time_since_last
                    time.sleep(sleep_time)
                    actual_delay = sleep_time
                else:
                    actual_delay = 0.0
            else:
                # First request for this platform, no delay needed
                actual_delay = 0.0
            
            # Update timestamp
            self._platform_timestamps[platform] = time.time()
            
            return actual_delay
    
    def get_last_request_time(self, platform: str) -> Optional[float]:
        """
        Get the timestamp of the last request for a platform.
        
        Args:
            platform: Platform name
            
        Returns:
            Timestamp of last request, or None if no requests have been made
        """
        with self._lock:
            return self._platform_timestamps.get(platform)
    
    def reset_platform(self, platform: str) -> None:
        """
        Reset the rate limit tracking for a platform.
        
        Args:
            platform: Platform name
        """
        with self._lock:
            if platform in self._platform_timestamps:
                del self._platform_timestamps[platform]
    
    def reset_all(self) -> None:
        """Reset rate limit tracking for all platforms."""
        with self._lock:
            self._platform_timestamps.clear()
    
    def get_random_delay(self, platform: str) -> float:
        """
        Generate a random delay within the configured range for a platform.
        
        Args:
            platform: Platform name
            
        Returns:
            Random delay in seconds within the configured range
        """
        with self._lock:
            config = self._platform_configs.get(platform, {
                "min_delay": self._default_min_delay,
                "max_delay": self._default_max_delay
            })
            
            return random.uniform(config["min_delay"], config["max_delay"])
