"""
Retry Configuration and Logic

Provides retry configuration and exponential backoff calculation for browser operations.
"""

import time
import logging
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional
from src.ai_auto_apply.config.browser_errors import BrowserError, ErrorType, classify_error


logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """
    Configuration for retry logic with exponential backoff.
    
    Attributes:
        max_retries: Maximum number of retry attempts
        initial_delay_seconds: Initial delay before first retry
        backoff_multiplier: Multiplier for exponential backoff
        max_delay_seconds: Maximum delay cap
    """
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given retry attempt using exponential backoff.
        
        Args:
            attempt: The retry attempt number (0-indexed)
            
        Returns:
            Delay in seconds, capped at max_delay_seconds
        """
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_seconds)


def calculate_retry_delay(config: RetryConfig, attempt: int) -> float:
    """
    Calculate retry delay for a given attempt using exponential backoff.
    
    Standalone function for testing and external use.
    
    Args:
        config: RetryConfig instance
        attempt: The retry attempt number (1-indexed for user-facing, converted to 0-indexed internally)
        
    Returns:
        Delay in seconds, capped at max_delay_seconds
    """
    # Convert 1-indexed attempt to 0-indexed for calculation
    return config.calculate_delay(attempt - 1)


def execute_with_retry(
    operation: Callable[[], Dict[str, Any]],
    retry_config: RetryConfig,
    operation_name: str = "operation"
) -> Dict[str, Any]:
    """
    Execute an operation with retry logic and exponential backoff.
    
    Distinguishes between recoverable and permanent errors:
    - Recoverable errors: Retry with exponential backoff
    - Permanent errors: Fail immediately without retry
    - Rate limit errors: Retry with backoff
    - CAPTCHA errors: Fail immediately (manual intervention needed)
    
    Args:
        operation: Callable that performs the operation and returns result dict
        retry_config: Retry configuration
        operation_name: Name of the operation for logging
        
    Returns:
        Dictionary with execution results:
        {
            "success": bool,
            "result": Any,
            "error": Optional[str],
            "attempts": int,
            "permanent": bool  # True if error is permanent
        }
    """
    last_error: Optional[Exception] = None
    
    for attempt in range(retry_config.max_retries):
        try:
            logger.debug(f"Executing {operation_name} (attempt {attempt + 1}/{retry_config.max_retries})")
            
            # Execute the operation
            result = operation()
            
            # If operation returns a dict with success indicator, check it
            if isinstance(result, dict):
                if result.get("success", True):
                    logger.info(f"{operation_name} succeeded on attempt {attempt + 1}")
                    return {
                        "success": True,
                        "result": result,
                        "error": None,
                        "attempts": attempt + 1,
                        "permanent": False
                    }
                else:
                    # Operation returned failure - treat as error
                    error_msg = result.get("error", "Operation returned success=False")
                    raise RuntimeError(error_msg)
            else:
                # Operation succeeded (returned non-dict result)
                logger.info(f"{operation_name} succeeded on attempt {attempt + 1}")
                return {
                    "success": True,
                    "result": result,
                    "error": None,
                    "attempts": attempt + 1,
                    "permanent": False
                }
                
        except Exception as e:
            last_error = e
            
            # Classify the error
            if isinstance(e, BrowserError):
                browser_error = e
            else:
                browser_error = classify_error(e)
            
            logger.warning(
                f"{operation_name} failed on attempt {attempt + 1}: "
                f"[{browser_error.error_type.value}] {browser_error.message}"
            )
            
            # Handle based on error type
            if browser_error.error_type == ErrorType.PERMANENT:
                # Permanent error - don't retry
                logger.error(f"{operation_name} failed with permanent error: {browser_error.message}")
                return {
                    "success": False,
                    "result": None,
                    "error": browser_error.message,
                    "attempts": attempt + 1,
                    "permanent": True
                }
            
            elif browser_error.error_type == ErrorType.CAPTCHA:
                # CAPTCHA - manual intervention needed, don't retry
                logger.error(f"{operation_name} failed with CAPTCHA: {browser_error.message}")
                return {
                    "success": False,
                    "result": None,
                    "error": browser_error.message,
                    "attempts": attempt + 1,
                    "permanent": True,
                    "captcha": True
                }
            
            elif browser_error.error_type in (ErrorType.RECOVERABLE, ErrorType.RATE_LIMIT):
                # Recoverable or rate limit - retry with backoff
                if attempt < retry_config.max_retries - 1:
                    delay = retry_config.calculate_delay(attempt)
                    logger.info(
                        f"{operation_name} will retry in {delay:.2f}s "
                        f"(attempt {attempt + 2}/{retry_config.max_retries})"
                    )
                    time.sleep(delay)
                else:
                    # Max retries reached
                    logger.error(
                        f"{operation_name} failed after {retry_config.max_retries} attempts: "
                        f"{browser_error.message}"
                    )
                    return {
                        "success": False,
                        "result": None,
                        "error": browser_error.message,
                        "attempts": attempt + 1,
                        "permanent": False
                    }
    
    # Should not reach here, but handle it
    return {
        "success": False,
        "result": None,
        "error": str(last_error) if last_error else "Unknown error",
        "attempts": retry_config.max_retries,
        "permanent": False
    }
