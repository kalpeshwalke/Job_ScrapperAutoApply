"""
Error Handlers

Error handling utilities for network, AI provider, and DOM errors.
"""

import time
import requests
from typing import Dict, Any, Callable
from src.common.logger import get_logger

logger = get_logger("error_handlers")


class NetworkErrorHandler:
    """Handles network-related errors with retry logic"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize network error handler.
        
        Args:
            config: Retry configuration from config.yaml
        """
        self.max_retries = config.get("retry", {}).get("max_retries", 3)
        self.backoff_multiplier = config.get("retry", {}).get("backoff_multiplier", 2)
        self.initial_delay = config.get("retry", {}).get("initial_delay_seconds", 1)
    
    def retry_with_backoff(self, func: Callable, *args, **kwargs):
        """
        Retry a function with exponential backoff.
        
        Args:
            func: Function to retry
            *args, **kwargs: Arguments to pass to function
            
        Returns:
            Function result
            
        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exception = e
                delay = self.initial_delay * (self.backoff_multiplier ** attempt)
                logger.warning(
                    "Network error (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1, self.max_retries, e, delay
                )
                time.sleep(delay)
        
        # All retries failed
        logger.error("All %d retry attempts failed", self.max_retries)
        raise last_exception


class AIProviderErrorHandler:
    """Handles AI provider-specific errors"""
    
    @staticmethod
    def handle_provider_error(provider_name: str, error: Exception) -> Dict[str, Any]:
        """
        Handle provider-specific errors.
        
        Args:
            provider_name: Name of AI provider
            error: Exception raised
            
        Returns:
            Dictionary with error details and recommended action
        """
        error_str = str(error).lower()
        
        # Rate limit errors
        if "rate limit" in error_str or "quota" in error_str:
            return {
                "error_type": "rate_limit",
                "message": f"{provider_name} rate limit exceeded",
                "action": "throttle",
                "retry_after": 60  # seconds
            }
        
        # Authentication errors
        if "api key" in error_str or "unauthorized" in error_str or "401" in error_str:
            return {
                "error_type": "authentication",
                "message": f"{provider_name} API key invalid or missing",
                "action": "abort",
                "retry_after": None
            }
        
        # Model not found errors
        if "model" in error_str and ("not found" in error_str or "404" in error_str):
            return {
                "error_type": "model_not_found",
                "message": f"{provider_name} model not available",
                "action": "abort",
                "retry_after": None
            }
        
        # Generic errors
        return {
            "error_type": "unknown",
            "message": f"{provider_name} error: {str(error)[:100]}",
            "action": "retry",
            "retry_after": 5
        }


class DOMErrorHandler:
    """Handles DOM interaction errors"""
    
    @staticmethod
    def handle_element_not_found(mmid: str) -> Dict[str, Any]:
        """Handle element not found errors"""
        logger.warning("Element not found: mmid=%s", mmid)
        return {
            "success": False,
            "error": f"Element mmid={mmid} not found",
            "action": "report_to_planner"
        }
    
    @staticmethod
    def handle_interaction_failed(mmid: str, action: str, error: Exception) -> Dict[str, Any]:
        """Handle failed DOM interactions"""
        logger.error("DOM interaction failed: %s on mmid=%s: %s", action, mmid, error)
        return {
            "success": False,
            "error": f"Failed to {action} on mmid={mmid}: {str(error)[:50]}",
            "action": "report_to_planner"
        }
