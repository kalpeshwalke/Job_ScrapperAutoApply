"""
Rate Limiter for AI API Requests

Token bucket rate limiter for AI API requests.
"""

import time
from src.common.logger import get_logger

logger = get_logger("rate_limiter_ai")


class RateLimitError(Exception):
    """Raised when daily rate limit is exceeded"""
    pass


class RateLimiter:
    """Token bucket rate limiter for AI API requests"""
    
    def __init__(self, requests_per_minute: int, requests_per_day: int):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute
            requests_per_day: Maximum requests per day
        """
        self.rpm = requests_per_minute
        self.rpd = requests_per_day
        
        self.minute_tokens = requests_per_minute
        self.day_tokens = requests_per_day
        
        self.last_minute_reset = time.time()
        self.last_day_reset = time.time()
        
        logger.info("RateLimiter initialized: %d req/min, %d req/day", 
                   requests_per_minute, requests_per_day)
    
    def acquire(self):
        """
        Acquire a token, blocking if rate limit reached.
        
        Raises:
            RateLimitError: If daily quota is exceeded
        """
        now = time.time()
        
        # Reset minute bucket
        if now - self.last_minute_reset >= 60:
            self.minute_tokens = self.rpm
            self.last_minute_reset = now
        
        # Reset day bucket
        if now - self.last_day_reset >= 86400:
            self.day_tokens = self.rpd
            self.last_day_reset = now
        
        # Wait if no tokens available
        if self.minute_tokens <= 0:
            wait_time = 60 - (now - self.last_minute_reset)
            logger.info("Rate limit reached, waiting %.1fs...", wait_time)
            time.sleep(wait_time)
            self.minute_tokens = self.rpm
            self.last_minute_reset = time.time()
        
        if self.day_tokens <= 0:
            logger.error("Daily rate limit reached")
            raise RateLimitError("Daily API quota exceeded")
        
        # Consume tokens
        self.minute_tokens -= 1
        self.day_tokens -= 1
        
        logger.debug("Token acquired: %d/min remaining, %d/day remaining", 
                    self.minute_tokens, self.day_tokens)
