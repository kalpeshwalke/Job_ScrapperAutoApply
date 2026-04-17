"""
Browser Error Classification

Defines error types and classification logic for browser operations.
"""

from enum import Enum
from typing import Optional


class ErrorType(Enum):
    """Classification of browser operation errors"""
    RECOVERABLE = "recoverable"      # Retry possible (timeouts, temporary failures)
    PERMANENT = "permanent"          # No point retrying (missing elements, broken pages)
    RATE_LIMIT = "rate_limit"        # Wait and retry (API rate limits)
    CAPTCHA = "captcha"              # Manual intervention needed (bot detection)


class BrowserError(Exception):
    """
    Exception class for browser operations with error type classification.
    
    Attributes:
        message: Error description
        error_type: Classification of the error
        original_exception: The original exception that was wrapped
    """
    
    def __init__(
        self,
        message: str,
        error_type: ErrorType,
        original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.error_type = error_type
        self.original_exception = original_exception
        super().__init__(message)
    
    def __str__(self):
        return f"[{self.error_type.value}] {self.message}"


def classify_error(exception: Exception) -> BrowserError:
    """
    Classify an exception into a BrowserError with appropriate error type.
    
    Args:
        exception: The exception to classify
        
    Returns:
        BrowserError with appropriate error_type
    """
    error_message = str(exception).lower()
    exception_type = type(exception).__name__.lower()
    
    # CAPTCHA detection
    captcha_indicators = [
        "captcha",
        "recaptcha",
        "bot detection",
        "security check",
        "verify you are human",
        "cloudflare"
    ]
    if any(indicator in error_message for indicator in captcha_indicators):
        return BrowserError(
            f"CAPTCHA or bot detection encountered: {exception}",
            ErrorType.CAPTCHA,
            exception
        )
    
    # Rate limit detection
    rate_limit_indicators = [
        "rate limit",
        "too many requests",
        "429",
        "quota exceeded",
        "throttled"
    ]
    if any(indicator in error_message for indicator in rate_limit_indicators):
        return BrowserError(
            f"Rate limit exceeded: {exception}",
            ErrorType.RATE_LIMIT,
            exception
        )
    
    # Recoverable errors (timeouts, temporary network issues)
    recoverable_indicators = [
        "timeout",
        "timed out",
        "connection",
        "network",
        "temporary",
        "retry",
        "waiting for",
        "element not found",  # Element might appear after waiting
        "element not visible",
        "stale element"
    ]
    recoverable_types = [
        "timeouterror",
        "connectionerror",
        "networkerror"
    ]
    
    if (any(indicator in error_message for indicator in recoverable_indicators) or
        exception_type in recoverable_types):
        return BrowserError(
            f"Recoverable error: {exception}",
            ErrorType.RECOVERABLE,
            exception
        )
    
    # Permanent errors (everything else - missing elements, broken pages, etc.)
    return BrowserError(
        f"Permanent error: {exception}",
        ErrorType.PERMANENT,
        exception
    )
