"""
Rate Limiter

Token bucket algorithm implementation for rate limiting MCP operations.
"""

import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from src.common.logger import get_logger

logger = get_logger("rate_limiter")


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    calls_per_minute: int = 60
    calls_per_day: int = 10000
    tokens_per_call: int = 1


class TokenBucket:
    """Token bucket implementation for rate limiting"""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill_time = time.time()
    
    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill_time
        tokens_to_add = elapsed * self.refill_rate
        
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill_time = now
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if not enough tokens
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """
        Get time to wait until tokens are available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Wait time in seconds
        """
        self._refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        tokens_needed = tokens - self.tokens
        wait_time = tokens_needed / self.refill_rate
        return wait_time


class RateLimiter:
    """Rate limiter for MCP operations using token bucket algorithm"""
    
    def __init__(self, config: RateLimitConfig):
        """
        Initialize rate limiter.
        
        Args:
            config: Rate limit configuration
        """
        self.config = config
        
        # Per-minute bucket
        self.minute_bucket = TokenBucket(
            capacity=config.calls_per_minute,
            refill_rate=config.calls_per_minute / 60.0  # tokens per second
        )
        
        # Per-day bucket
        self.day_bucket = TokenBucket(
            capacity=config.calls_per_day,
            refill_rate=config.calls_per_day / 86400.0  # tokens per second
        )
        
        # Usage tracking
        self.total_calls = 0
        self.total_tokens = 0
        
        logger.info(
            f"RateLimiter initialized: {config.calls_per_minute} calls/min, "
            f"{config.calls_per_day} calls/day"
        )
    
    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens for an operation.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False if rate limit exceeded
        
        Requirements: 12.1, 12.5
        """
        # Check both buckets
        minute_ok = self.minute_bucket.consume(tokens)
        day_ok = self.day_bucket.consume(tokens)
        
        if minute_ok and day_ok:
            self.total_calls += 1
            self.total_tokens += tokens
            return True
        
        # Restore tokens if one bucket succeeded but other failed
        if minute_ok and not day_ok:
            self.minute_bucket.tokens += tokens
        if day_ok and not minute_ok:
            self.day_bucket.tokens += tokens
        
        return False
    
    def wait_and_acquire(self, tokens: int = 1, max_wait: float = 60.0) -> bool:
        """
        Wait until tokens are available and acquire them.
        
        Args:
            tokens: Number of tokens to acquire
            max_wait: Maximum wait time in seconds
            
        Returns:
            True if tokens acquired, False if max wait exceeded
        
        Requirements: 12.2, 12.4
        """
        # Calculate wait time needed
        minute_wait = self.minute_bucket.get_wait_time(tokens)
        day_wait = self.day_bucket.get_wait_time(tokens)
        wait_time = max(minute_wait, day_wait)
        
        if wait_time > max_wait:
            logger.warning(
                f"Rate limit wait time ({wait_time:.2f}s) exceeds max wait ({max_wait}s)"
            )
            return False
        
        if wait_time > 0:
            logger.info(f"Rate limit reached, waiting {wait_time:.2f}s")
            time.sleep(wait_time)
        
        return self.acquire(tokens)
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics.
        
        Returns:
            Dictionary with usage stats
        
        Requirements: 12.3, 12.6
        """
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "minute_tokens_available": int(self.minute_bucket.tokens),
            "minute_capacity": self.minute_bucket.capacity,
            "day_tokens_available": int(self.day_bucket.tokens),
            "day_capacity": self.day_bucket.capacity,
            "minute_utilization_pct": (
                (1 - self.minute_bucket.tokens / self.minute_bucket.capacity) * 100
            ),
            "day_utilization_pct": (
                (1 - self.day_bucket.tokens / self.day_bucket.capacity) * 100
            )
        }
    
    def is_approaching_limit(self, threshold_pct: float = 80.0) -> bool:
        """
        Check if approaching rate limit.
        
        Args:
            threshold_pct: Threshold percentage (default: 80%)
            
        Returns:
            True if utilization exceeds threshold
        
        Requirements: 12.2
        """
        stats = self.get_usage_stats()
        return (
            stats["minute_utilization_pct"] > threshold_pct or
            stats["day_utilization_pct"] > threshold_pct
        )
