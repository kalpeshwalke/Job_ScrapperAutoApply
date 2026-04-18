"""
Structured logger for AI Auto-Apply system.

Provides component-specific logging with structured data for:
- AI decisions and reasoning
- DOM interactions and element details
- API usage and rate limiting
- Validation results
- Application success/failure tracking
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

from src.common.logger import get_logger as get_base_logger

# Component-specific loggers
_COMPONENT_LOGGERS = {}


def get_component_logger(component_name: str) -> logging.Logger:
    """Get a component-specific logger with structured logging capabilities."""
    if component_name in _COMPONENT_LOGGERS:
        return _COMPONENT_LOGGERS[component_name]
    
    # Create component-specific logger
    logger = get_base_logger(f"ai_auto_apply.{component_name}")
    _COMPONENT_LOGGERS[component_name] = logger
    return logger


class StructuredLogger:
    """Structured logger for AI Auto-Apply system with component-specific logging."""
    
    def __init__(self, component_name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize structured logger for a component.
        
        Args:
            component_name: Name of the component (e.g., "planner", "browser", "validator")
            config: Configuration dict with logging settings
        """
        self.component_name = component_name
        self.logger = get_component_logger(component_name)
        self.config = config or {}
        
        # Logging flags from config
        self._log_ai_decisions = self.config.get('log_ai_decisions', True)
        self._log_dom_interactions = self.config.get('log_dom_interactions', True)
        self._log_api_usage = self.config.get('log_api_usage', True)
    
    def log_ai_decision(self, decision_type: str, data: Dict[str, Any], reasoning: str = ""):
        """
        Log AI decision with structured data.
        
        Args:
            decision_type: Type of decision (e.g., "planner_next_step", "browser_action")
            data: Structured data about the decision
            reasoning: AI reasoning for the decision
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "decision_type": decision_type,
            "data": data,
            "reasoning": reasoning
        }
        
        self.logger.info(
            "AI Decision: %s - %s",
            decision_type,
            json.dumps(structured_data, default=str)
        )
    
    def log_dom_interaction(self, action_type: str, element_data: Dict[str, Any], 
                           success: bool, error: Optional[str] = None):
        """
        Log DOM interaction with element details.
        
        Args:
            action_type: Type of interaction (e.g., "click", "enter_text", "upload")
            element_data: Details about the element (mmid, tag, attributes)
            success: Whether the interaction succeeded
            error: Error message if failed
        """
        if not self._log_dom_interactions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "action_type": action_type,
            "element": element_data,
            "success": success,
            "error": error
        }
        
        if success:
            self.logger.info(
                "DOM Interaction: %s - %s",
                action_type,
                json.dumps(structured_data, default=str)
            )
        else:
            self.logger.error(
                "DOM Interaction Failed: %s - %s",
                action_type,
                json.dumps(structured_data, default=str)
            )
    
    def log_api_usage(self, provider: str, model: str, endpoint: str, 
                     tokens_used: Optional[int] = None, rate_limit_status: Optional[Dict[str, Any]] = None):
        """
        Log API usage with rate limit status.
        
        Args:
            provider: AI provider name (e.g., "gemini", "openai")
            model: Model name used
            endpoint: API endpoint called
            tokens_used: Number of tokens used (if available)
            rate_limit_status: Current rate limit status
        """
        if not self._log_api_usage:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "tokens_used": tokens_used,
            "rate_limit_status": rate_limit_status
        }
        
        self.logger.info(
            "API Usage: %s/%s - %s",
            provider,
            model,
            json.dumps(structured_data, default=str)
        )
    
    def log_validation_result(self, url: str, company_name: str, status: str, 
                             reason: str, details: Optional[Dict[str, Any]] = None):
        """
        Log career page validation result.
        
        Args:
            url: Career page URL
            company_name: Company name
            status: Validation status ("Yes", "No", "Unchecked")
            reason: Reason for the status
            details: Additional validation details
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "url": url,
            "company_name": company_name,
            "status": status,
            "reason": reason,
            "details": details or {}
        }
        
        if status == "Yes":
            self.logger.info(
                "Validation Success: %s - %s",
                company_name,
                json.dumps(structured_data, default=str)
            )
        elif status == "No":
            self.logger.warning(
                "Validation Failed: %s - %s",
                company_name,
                json.dumps(structured_data, default=str)
            )
        else:
            self.logger.info(
                "Validation Unchecked: %s - %s",
                company_name,
                json.dumps(structured_data, default=str)
            )
    
    def log_application_result(self, job_title: str, company: str, status: str, 
                              reason: str, metrics: Optional[Dict[str, Any]] = None):
        """
        Log job application result.
        
        Args:
            job_title: Job title
            company: Company name
            status: Application status ("success", "failed")
            reason: Reason for the status
            metrics: Performance metrics (time, iterations, etc.)
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "job_title": job_title,
            "company": company,
            "status": status,
            "reason": reason,
            "metrics": metrics or {}
        }
        
        if status == "success":
            self.logger.info(
                "Application Success: %s at %s - %s",
                job_title,
                company,
                json.dumps(structured_data, default=str)
            )
        else:
            self.logger.error(
                "Application Failed: %s at %s - %s",
                job_title,
                company,
                json.dumps(structured_data, default=str)
            )
    
    def log_provider_selection(self, provider: str, model: str, reason: str = ""):
        """
        Log AI provider and model selection at startup.
        
        Args:
            provider: Selected AI provider
            model: Selected model
            reason: Reason for selection
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "provider": provider,
            "model": model,
            "reason": reason
        }
        
        self.logger.info(
            "Provider Selected: %s/%s - %s",
            provider,
            model,
            json.dumps(structured_data, default=str)
        )
    
    def log_performance_metrics(self, metrics_type: str, metrics: Dict[str, Any]):
        """
        Log performance metrics.
        
        Args:
            metrics_type: Type of metrics (e.g., "scraping", "application", "validation")
            metrics: Performance metrics data
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "metrics_type": metrics_type,
            "metrics": metrics
        }
        
        self.logger.info(
            "Performance Metrics: %s - %s",
            metrics_type,
            json.dumps(structured_data, default=str)
        )
    
    def log_screenshot(self, file_path: str, reason: str, context: Optional[Dict[str, Any]] = None):
        """
        Log screenshot capture event.
        
        Args:
            file_path: Path to the saved screenshot file
            reason: Reason for capturing screenshot (e.g., "application_failed", "unexpected_structure")
            context: Additional context (job_id, timestamp, url, etc.)
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "file_path": file_path,
            "reason": reason,
            "context": context or {}
        }
        
        self.logger.info(
            "Screenshot Captured: %s - %s",
            reason,
            json.dumps(structured_data, default=str)
        )
    
    def log_network_request(self, method: str, url: str, status_code: int, 
                           response_time_ms: Optional[float] = None, 
                           resource_type: Optional[str] = None):
        """
        Log network request event.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            status_code: HTTP status code
            response_time_ms: Response time in milliseconds
            resource_type: Resource type (xhr, fetch, document, etc.)
        
        Requirements: 14.6
        """
        if not self._log_api_usage:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "method": method,
            "url": url,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "resource_type": resource_type
        }
        
        self.logger.info(
            "Network Request: %s %s -> %s - %s",
            method,
            url,
            status_code,
            json.dumps(structured_data, default=str)
        )
    
    def log_wait_operation(self, wait_type: str, duration_ms: int, 
                          outcome: str, context: Optional[Dict[str, Any]] = None):
        """
        Log wait operation event.
        
        Args:
            wait_type: Type of wait operation (e.g., "page_ready", "element", "loading_indicator", "adaptive")
            duration_ms: Duration of wait in milliseconds
            outcome: Outcome of wait operation (e.g., "success", "timeout", "not_found")
            context: Additional context (selector, element_count, etc.)
        
        Requirements: 15.6
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "wait_type": wait_type,
            "duration_ms": duration_ms,
            "outcome": outcome,
            "context": context or {}
        }
        
        self.logger.info(
            "Wait Operation: %s (%dms) -> %s - %s",
            wait_type,
            duration_ms,
            outcome,
            json.dumps(structured_data, default=str)
        )

    def log_mcp_operation(self, tool_name: str, arguments: Dict[str, Any], 
                         result: Any, duration_ms: float, success: bool, 
                         error: Optional[str] = None):
        """
        Log MCP operation event.
        
        Args:
            tool_name: Name of the MCP tool called
            arguments: Arguments passed to the tool
            result: Result returned by the tool
            duration_ms: Duration of operation in milliseconds
            success: Whether the operation succeeded
            error: Error message if failed
        
        Requirements: 8.1, 8.2, 8.3, 8.4, 8.6
        """
        if not self._log_api_usage:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "duration_ms": duration_ms,
            "success": success,
            "error": error
        }
        
        if success:
            self.logger.info(
                "MCP Operation: %s (%.2fms) -> SUCCESS - %s",
                tool_name,
                duration_ms,
                json.dumps(structured_data, default=str)
            )
        else:
            self.logger.error(
                "MCP Operation: %s (%.2fms) -> FAILED - %s",
                tool_name,
                duration_ms,
                json.dumps(structured_data, default=str)
            )
    
    def log_homepage_navigation(self, original_url: str, careers_url: Optional[str], 
                               success: bool, attempts: int, 
                               context: Optional[Dict[str, Any]] = None):
        """
        Log homepage navigation event.
        
        Args:
            original_url: Original career page URL that redirected to homepage
            careers_url: Final careers page URL (if navigation succeeded)
            success: Whether navigation to careers page succeeded
            attempts: Number of attempts made
            context: Additional context (error, final_url, etc.)
        
        Requirements: 1.8, 16.9
        """
        if not self._log_ai_decisions:
            return
        
        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "original_url": original_url,
            "careers_url": careers_url,
            "success": success,
            "attempts": attempts,
            "context": context or {}
        }
        
        if success:
            self.logger.info(
                "Homepage Navigation: SUCCESS (%d attempts) - %s -> %s - %s",
                attempts,
                original_url,
                careers_url,
                json.dumps(structured_data, default=str)
            )
        else:
            self.logger.warning(
                "Homepage Navigation: FAILED (%d attempts) - %s - %s",
                attempts,
                original_url,
                json.dumps(structured_data, default=str)
            )




# Convenience functions for direct usage
def log_ai_decision(component: str, decision_type: str, data: Dict[str, Any], 
                   reasoning: str = "", config: Optional[Dict[str, Any]] = None):
    """Convenience function to log AI decision."""
    logger = StructuredLogger(component, config)
    logger.log_ai_decision(decision_type, data, reasoning)


def log_dom_interaction(component: str, action_type: str, element_data: Dict[str, Any],
                       success: bool, error: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
    """Convenience function to log DOM interaction."""
    logger = StructuredLogger(component, config)
    logger.log_dom_interaction(action_type, element_data, success, error)


def log_api_usage(component: str, provider: str, model: str, endpoint: str,
                 tokens_used: Optional[int] = None, rate_limit_status: Optional[Dict[str, Any]] = None,
                 config: Optional[Dict[str, Any]] = None):
    """Convenience function to log API usage."""
    logger = StructuredLogger(component, config)
    logger.log_api_usage(provider, model, endpoint, tokens_used, rate_limit_status)


def log_validation_result(component: str, url: str, company_name: str, status: str,
                         reason: str, details: Optional[Dict[str, Any]] = None,
                         config: Optional[Dict[str, Any]] = None):
    """Convenience function to log validation result."""
    logger = StructuredLogger(component, config)
    logger.log_validation_result(url, company_name, status, reason, details)


def log_application_result(component: str, job_title: str, company: str, status: str,
                          reason: str, metrics: Optional[Dict[str, Any]] = None,
                          config: Optional[Dict[str, Any]] = None):
    """Convenience function to log application result."""
    logger = StructuredLogger(component, config)
    logger.log_application_result(job_title, company, status, reason, metrics)


def log_network_request(component: str, method: str, url: str, status_code: int,
                       response_time_ms: Optional[float] = None, resource_type: Optional[str] = None,
                       config: Optional[Dict[str, Any]] = None):
    """Convenience function to log network request."""
    logger = StructuredLogger(component, config)
    logger.log_network_request(method, url, status_code, response_time_ms, resource_type)
