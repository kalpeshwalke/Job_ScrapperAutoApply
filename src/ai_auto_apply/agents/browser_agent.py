"""
Browser Agent

Low-level browser agent that executes DOM interactions based on Planner instructions.
Supports both MCP (Model Context Protocol) and legacy DOM_Toolkit execution modes.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from src.common.logger import get_logger
from src.ai_auto_apply.core.structured_logger import StructuredLogger
from src.ai_auto_apply.config.retry_config import RetryConfig, execute_with_retry
from src.ai_auto_apply.config.browser_errors import BrowserError, ErrorType

logger = get_logger("browser_agent")


class BrowserAgent:
    """Low-level browser agent that executes DOM interactions with MCP and retry support"""
    
    # Allowed tool names for validation
    ALLOWED_TOOLS = {
        'click_element',
        'enter_text',
        'select_option',
        'upload_file',
        'press_key',
        'navigate'
    }
    
    SYSTEM_PROMPT = """You are a browser automation agent. You execute specific actions on web pages using DOM manipulation tools.

AVAILABLE TOOLS (USE ONLY THESE):
1. click_element(mmid) - Click an element
2. enter_text(mmid, text) - Type text into an input field
3. select_option(mmid, value) - Select an option from a dropdown menu
4. upload_file(mmid, file_path) - Upload a file
5. press_key(key) - Press a keyboard key (e.g., "Enter")
6. navigate(url) - Navigate to a URL

CRITICAL RULES:
- NEVER invent tool names. Only use the 6 tools listed above.
- If you cannot complete a step with these tools, report that you cannot complete it.
- Do NOT create tools like 'apply_for_job', 'search_jobs', 'custom_search_engine', etc.

You will receive:
1. A step description from the Planner (what to do)
2. Current DOM state (interactive elements with mmid attributes)
3. Job details (for filling forms)

Your task is to select the appropriate tool(s) to execute the step. You have access to the 6 tools listed above.

Be precise - use the mmid attributes to target the correct elements. If the required element is not in the DOM state, report that you cannot complete the step."""
    
    def __init__(
        self,
        provider,
        config: Dict[str, Any],
        mcp_client: Optional[Any] = None,
        page: Optional[Any] = None
    ):
        """
        Initialize Browser Agent with optional MCP client for hybrid mode.
        
        Args:
            provider: AIProvider instance
            config: auto_apply configuration
            mcp_client: Optional MCPClient instance for MCP-based execution
            page: Optional Playwright Page instance for screenshot capture
        """
        self.provider = provider
        self.config = config
        self.mcp_client = mcp_client
        self.page = page
        self.use_mcp = mcp_client is not None and config.get("mcp", {}).get("enabled", False)
        self.log_interactions = config.get("logging", {}).get("log_dom_interactions", True)
        self.structured_logger = StructuredLogger("browser", config.get("logging", {}))
        
        # Retry configuration
        retry_settings = config.get("retry", {})
        self.retry_config = RetryConfig(
            max_retries=retry_settings.get("max_retries", 3),
            initial_delay_seconds=retry_settings.get("initial_delay_seconds", 1.0),
            backoff_multiplier=retry_settings.get("backoff_multiplier", 2.0),
            max_delay_seconds=retry_settings.get("max_delay_seconds", 30.0)
        )
        
        # Screenshot configuration
        screenshot_config = config.get("screenshots", {})
        self.screenshot_enabled = screenshot_config.get("enabled", True)
        self.screenshot_dir = screenshot_config.get("directory", "logs/screenshots")
        self.screenshot_on_failure = screenshot_config.get("on_failure", True)
        self.screenshot_on_unexpected = screenshot_config.get("on_unexpected_structure", True)
        self.screenshot_each_iteration = screenshot_config.get("each_iteration", False)
        
        # Network monitoring configuration
        network_config = config.get("network_monitoring", {})
        self.network_monitoring_enabled = network_config.get("enabled", True)
        self.network_requests = []  # Store network requests
        self._network_listener_attached = False
        
        logger.info(
            f"BrowserAgent initialized with MCP={'enabled' if self.use_mcp else 'disabled'}, "
            f"retry_config={self.retry_config}, screenshots={'enabled' if self.screenshot_enabled else 'disabled'}, "
            f"network_monitoring={'enabled' if self.network_monitoring_enabled else 'disabled'}"
        )
    
    def validate_tool_call(self, tool_call: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate that tool_call uses an allowed tool name.
        
        Args:
            tool_call: Tool call dictionary with "name" and "arguments" keys
            
        Returns:
            (is_valid, error_message) tuple where:
            - is_valid: True if tool name is in ALLOWED_TOOLS, False otherwise
            - error_message: None if valid, error message string if invalid
        """
        tool_name = tool_call.get("name", "")
        if tool_name not in self.ALLOWED_TOOLS:
            allowed_tools_list = ', '.join(sorted(self.ALLOWED_TOOLS))
            return False, f"Invalid tool '{tool_name}'. Allowed tools: {allowed_tools_list}"
        return True, None
    
    def set_page(self, page: Any):
        """
        Set the Playwright page instance for screenshot capture and network monitoring.
        
        Args:
            page: Playwright Page instance
        """
        self.page = page
        logger.debug("Playwright page instance set for screenshot capture and network monitoring")
        
        # Attach network monitoring listeners if enabled
        if self.network_monitoring_enabled and not self._network_listener_attached:
            self.monitor_network_requests()
    
    def monitor_network_requests(self):
        """
        Attach network event listeners to monitor XHR and Fetch requests.
        
        Tracks:
        - URL, method, status code, response time
        - Request and response timestamps
        - Resource type (xhr, fetch, document, etc.)
        
        Requirements: 14.1, 14.2, 14.5
        """
        if not self.page:
            logger.warning("Cannot monitor network requests: Playwright page not set")
            return
        
        if self._network_listener_attached:
            logger.debug("Network listeners already attached")
            return
        
        try:
            # Track request start times
            request_start_times = {}
            
            def on_request(request):
                """Handle request event"""
                request_start_times[request.url] = datetime.now()
                logger.debug(f"Network request started: {request.method} {request.url}")
            
            def on_response(response):
                """Handle response event"""
                try:
                    url = response.url
                    method = response.request.method
                    status_code = response.status
                    resource_type = response.request.resource_type
                    
                    # Calculate response time
                    start_time = request_start_times.get(url)
                    response_time_ms = None
                    if start_time:
                        response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
                        del request_start_times[url]
                    
                    # Store network request data
                    request_data = {
                        "timestamp": datetime.now().isoformat(),
                        "method": method,
                        "url": url,
                        "status_code": status_code,
                        "response_time_ms": response_time_ms,
                        "resource_type": resource_type
                    }
                    
                    self.network_requests.append(request_data)
                    
                    # Log XHR and Fetch requests (most relevant for form submissions)
                    if resource_type in ["xhr", "fetch"]:
                        if response_time_ms is not None:
                            logger.info(
                                "Network request: %s %s -> %s (%.2fms)",
                                method, url, status_code, response_time_ms
                            )
                        else:
                            logger.info(
                                "Network request: %s %s -> %s",
                                method, url, status_code
                            )
                    
                except Exception as e:
                    logger.error(f"Error handling network response: {e}", exc_info=True)
            
            # Attach event listeners
            self.page.on("request", on_request)
            self.page.on("response", on_response)
            
            self._network_listener_attached = True
            logger.info("Network monitoring listeners attached successfully")
            
        except Exception as e:
            logger.error(f"Failed to attach network monitoring listeners: {e}", exc_info=True)
    
    def get_network_requests(self, clear: bool = False) -> List[Dict[str, Any]]:
        """
        Get captured network requests.
        
        Args:
            clear: If True, clear the network requests list after returning
            
        Returns:
            List of network request dictionaries
        """
        requests = self.network_requests.copy()
        if clear:
            self.network_requests.clear()
        return requests
    
    def detect_form_submission(self) -> Optional[Dict[str, Any]]:
        """
        Detect form submission requests and check their status.
        
        Looks for POST requests to application endpoints and checks:
        - 200-299 status codes = success
        - 400-599 status codes = error
        
        Returns:
            Dictionary with submission details if found, None otherwise
            {
                "url": str,
                "method": str,
                "status_code": int,
                "success": bool,
                "timestamp": str
            }
        
        Requirements: 14.3, 14.4
        """
        # Look for POST requests (typical for form submissions)
        post_requests = [
            req for req in self.network_requests
            if req["method"] == "POST" and req["resource_type"] in ["xhr", "fetch"]
        ]
        
        if not post_requests:
            return None
        
        # Get the most recent POST request
        latest_post = post_requests[-1]
        status_code = latest_post["status_code"]
        
        # Check if it's a successful submission (2xx status codes)
        success = 200 <= status_code <= 299
        
        result = {
            "url": latest_post["url"],
            "method": latest_post["method"],
            "status_code": status_code,
            "success": success,
            "timestamp": latest_post["timestamp"],
            "response_time_ms": latest_post.get("response_time_ms")
        }
        
        if success:
            logger.info(f"Form submission detected: {latest_post['url']} -> {status_code} (SUCCESS)")
            # Log with structured logger for better analytics
            self.structured_logger.log_ai_decision(
                decision_type="form_submission_success",
                data={
                    "url": latest_post["url"],
                    "status_code": status_code,
                    "response_time_ms": latest_post.get("response_time_ms")
                },
                reasoning="Successful form submission detected via POST request with 2xx status code"
            )
        else:
            logger.warning(f"Form submission detected: {latest_post['url']} -> {status_code} (ERROR)")
            # Log form submission error with structured logger
            self.structured_logger.log_ai_decision(
                decision_type="form_submission_error",
                data={
                    "url": latest_post["url"],
                    "status_code": status_code,
                    "response_time_ms": latest_post.get("response_time_ms"),
                    "error_type": "client_error" if 400 <= status_code < 500 else "server_error"
                },
                reasoning=f"Form submission failed with status code {status_code}"
            )
        
        return result
    
    def capture_screenshot(self, reason: str, job_id: Optional[str] = None) -> Optional[str]:
        """
        Capture a screenshot of the current page state for debugging.
        
        Args:
            reason: Reason for capturing screenshot (e.g., "application_failed", "unexpected_structure")
            job_id: Optional job identifier for organizing screenshots
            
        Returns:
            File path of saved screenshot, or None if capture failed
        """
        if not self.screenshot_enabled:
            logger.debug("Screenshot capture disabled in configuration")
            return None
        
        if not self.page:
            logger.warning("Cannot capture screenshot: Playwright page not set")
            return None
        
        try:
            # Create screenshot directory structure
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if job_id:
                # Organize by job_id: logs/screenshots/{job_id}/
                screenshot_path = Path(self.screenshot_dir) / job_id
            else:
                # Default: logs/screenshots/
                screenshot_path = Path(self.screenshot_dir)
            
            screenshot_path.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp and reason
            filename = f"{timestamp}_{reason}.png"
            file_path = screenshot_path / filename
            
            # Capture screenshot using Playwright
            self.page.screenshot(path=str(file_path), full_page=True)
            
            logger.info(f"Screenshot captured: {file_path} (reason: {reason})")
            
            # Log with structured logger
            self.structured_logger.log_screenshot(
                file_path=str(file_path),
                reason=reason,
                context={
                    "job_id": job_id,
                    "timestamp": timestamp,
                    "url": self.page.url if self.page else "unknown"
                }
            )
            
            return str(file_path)
        
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}", exc_info=True)
            return None
    
    def execute_step(
        self,
        step: str,
        dom_state: Dict[str, Any],
        dom_toolkit,
        job_data: Dict[str, Any],
        use_mcp: bool = None
    ) -> Dict[str, Any]:
        """
        Execute a step using MCP or legacy approach (hybrid mode) with connection recovery.
        
        Tries MCP first when enabled, attempts reconnection on connection lost,
        falls back to legacy DOM_Toolkit on MCP failure.
        
        Args:
            step: Step description from Planner
            dom_state: Current DOM state
            dom_toolkit: DOMToolkit instance
            job_data: Job details for form filling
            use_mcp: Override to force MCP on/off (None = use instance setting)
            
        Returns:
            Dictionary with execution results
        """
        # Determine which approach to use
        should_use_mcp = use_mcp if use_mcp is not None else self.use_mcp
        
        # Clear previous network requests before executing step
        if self.network_monitoring_enabled:
            self.network_requests.clear()
        
        if should_use_mcp and self.mcp_client:
            logger.info("Attempting MCP-based execution")
            
            # Try MCP approach
            mcp_result = self._execute_step_mcp(step, dom_state, job_data)
            
            if mcp_result.get("success", False):
                logger.info("MCP execution succeeded")
                # Log network requests after execution
                self._log_network_requests()
                return mcp_result
            else:
                error_msg = mcp_result.get('error', 'Unknown error')
                
                # Check if error indicates connection lost
                connection_lost_indicators = [
                    "connection closed",
                    "connection lost",
                    "broken pipe",
                    "not connected",
                    "connection refused",
                    "stdin not available",
                    "stdout not available"
                ]
                
                is_connection_lost = any(
                    indicator in error_msg.lower() 
                    for indicator in connection_lost_indicators
                )
                
                if is_connection_lost:
                    logger.warning(f"MCP connection lost detected: {error_msg}")
                    logger.info("Attempting to reconnect MCP client...")
                    
                    # Attempt to reconnect once
                    try:
                        if self.mcp_client.connect():
                            logger.info("MCP reconnection successful, retrying operation")
                            
                            # Retry the operation after successful reconnection
                            retry_result = self._execute_step_mcp(step, dom_state, job_data)
                            
                            if retry_result.get("success", False):
                                logger.info("MCP execution succeeded after reconnection")
                                self._log_network_requests()
                                return retry_result
                            else:
                                logger.warning(
                                    f"MCP execution failed after reconnection: {retry_result.get('error')}. "
                                    "Falling back to legacy"
                                )
                        else:
                            logger.error("MCP reconnection failed, falling back to legacy")
                    except Exception as reconnect_error:
                        logger.error(f"MCP reconnection attempt failed: {reconnect_error}")
                
                # MCP failed - fall back to legacy
                logger.warning(
                    f"MCP execution failed: {error_msg}. "
                    "Falling back to legacy DOM_Toolkit"
                )
                result = self._execute_step_legacy(step, dom_state, dom_toolkit, job_data)
                # Log network requests after execution
                self._log_network_requests()
                return result
        else:
            # Use legacy approach
            logger.info("Using legacy DOM_Toolkit execution")
            result = self._execute_step_legacy(step, dom_state, dom_toolkit, job_data)
            # Log network requests after execution
            self._log_network_requests()
            return result
    
    def _log_network_requests(self):
        """Log captured network requests to structured logger."""
        if not self.network_monitoring_enabled:
            return
        
        # Log all captured network requests
        for request in self.network_requests:
            self.structured_logger.log_network_request(
                method=request["method"],
                url=request["url"],
                status_code=request["status_code"],
                response_time_ms=request.get("response_time_ms"),
                resource_type=request.get("resource_type")
            )
    
    def _execute_step_mcp(
        self,
        step: str,
        dom_state: Dict[str, Any],
        job_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute step using MCP tools with comprehensive error handling.
        
        Translates high-level step into MCP tool calls:
        - "Click on careers link" -> playwright_click
        - "Fill form field" -> playwright_fill
        - "Navigate to URL" -> playwright_navigate
        
        Args:
            step: Step description
            dom_state: Current DOM state
            job_data: Job details
            
        Returns:
            Execution result dictionary with success, action_summary, and error fields
        """
        current_url = dom_state.get("url", "unknown")
        
        try:
            step_lower = step.lower()
            
            # Parse step to determine action type
            if "click" in step_lower:
                # Extract selector from step or dom_state
                selector = self._extract_selector_from_step(step, dom_state)
                if selector:
                    logger.debug(f"MCP: Executing click on selector: {selector}")
                    result = self.mcp_client.call_tool(
                        "playwright_click",
                        {"selector": selector}
                    )
                    
                    # Log error details if failed
                    if not result.get("success"):
                        error_msg = result.get("error", "Unknown error")
                        logger.error(
                            f"MCP click failed: tool=playwright_click, selector={selector}, "
                            f"error={error_msg}, url={current_url}"
                        )
                    
                    return {
                        "success": result.get("success", False),
                        "action_summary": f"Clicked element: {selector}",
                        "error": result.get("error")
                    }
                else:
                    logger.error(f"MCP: Could not extract selector from step: {step}")
                    return {
                        "success": False,
                        "error": "Could not extract selector from step",
                        "action_summary": "No action taken"
                    }
            
            elif "fill" in step_lower or "enter" in step_lower:
                selector, text = self._extract_fill_params(step, dom_state, job_data)
                if selector and text:
                    logger.debug(f"MCP: Executing fill on selector: {selector}")
                    result = self.mcp_client.call_tool(
                        "playwright_fill",
                        {"selector": selector, "value": text}
                    )
                    
                    # Log error details if failed
                    if not result.get("success"):
                        error_msg = result.get("error", "Unknown error")
                        logger.error(
                            f"MCP fill failed: tool=playwright_fill, selector={selector}, "
                            f"error={error_msg}, url={current_url}"
                        )
                    
                    return {
                        "success": result.get("success", False),
                        "action_summary": f"Filled field: {selector}",
                        "error": result.get("error")
                    }
                else:
                    logger.error(f"MCP: Could not extract fill parameters from step: {step}")
                    return {
                        "success": False,
                        "error": "Could not extract fill parameters from step",
                        "action_summary": "No action taken"
                    }
            
            elif "navigate" in step_lower:
                url = self._extract_url_from_step(step)
                if url:
                    logger.debug(f"MCP: Executing navigate to URL: {url}")
                    result = self.mcp_client.call_tool(
                        "playwright_navigate",
                        {"url": url}
                    )
                    
                    # Log error details if failed
                    if not result.get("success"):
                        error_msg = result.get("error", "Unknown error")
                        logger.error(
                            f"MCP navigate failed: tool=playwright_navigate, target_url={url}, "
                            f"error={error_msg}, current_url={current_url}"
                        )
                    
                    return {
                        "success": result.get("success", False),
                        "action_summary": f"Navigated to: {url}",
                        "error": result.get("error")
                    }
                else:
                    logger.error(f"MCP: Could not extract URL from step: {step}")
                    return {
                        "success": False,
                        "error": "Could not extract URL from step",
                        "action_summary": "No action taken"
                    }
            
            # If no action matched, return error
            logger.warning(f"MCP: Could not translate step to MCP action: {step}")
            return {
                "success": False,
                "error": f"Could not translate step to MCP action: {step}",
                "action_summary": "No action taken"
            }
            
        except Exception as e:
            # Comprehensive error logging with context
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(
                f"MCP execution exception: error_type={error_type}, error={error_msg}, "
                f"step={step}, url={current_url}",
                exc_info=True
            )
            
            return {
                "success": False,
                "error": f"{error_type}: {error_msg}",
                "action_summary": f"MCP error: {error_msg}"
            }
    
    def _extract_selector_from_step(self, step: str, dom_state: Dict[str, Any]) -> Optional[str]:
        """
        Extract CSS selector from step description and DOM state.
        
        Uses pattern matching to identify target element from step text.
        
        Args:
            step: Step description
            dom_state: Current DOM state
            
        Returns:
            CSS selector or None
        """
        # Simple implementation: look for mmid in step
        # More sophisticated: use AI to match step text to DOM elements
        import re
        mmid_match = re.search(r'mmid[=:]?\s*["\']?(\d+)["\']?', step)
        if mmid_match:
            mmid = mmid_match.group(1)
            return f"[mmid='{mmid}']"
        
        # Fallback: return None (will trigger error in caller)
        return None
    
    def _extract_fill_params(
        self, 
        step: str, 
        dom_state: Dict[str, Any], 
        job_data: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Extract selector and text value for fill operation.
        
        Args:
            step: Step description
            dom_state: Current DOM state
            job_data: Job details
            
        Returns:
            (selector, text_value) tuple
        """
        # Extract selector
        selector = self._extract_selector_from_step(step, dom_state)
        
        # Extract text value from step or job_data
        # Simple implementation: look for quoted text in step
        import re
        text_match = re.search(r'["\']([^"\']+)["\']', step)
        if text_match:
            text = text_match.group(1)
            return (selector, text)
        
        # Fallback: return None
        return (selector, None)
    
    def _extract_url_from_step(self, step: str) -> Optional[str]:
        """
        Extract URL from step description.
        
        Args:
            step: Step description
            
        Returns:
            URL or None
        """
        import re
        # Look for URL pattern
        url_match = re.search(r'https?://[^\s]+', step)
        if url_match:
            return url_match.group(0)
        
        return None
    
    def _execute_step_legacy(
        self,
        step: str,
        dom_state: Dict[str, Any],
        dom_toolkit,
        job_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute step using legacy DOM_Toolkit approach.
        
        Args:
            step: Step description from Planner
            dom_state: Current DOM state
            dom_toolkit: DOMToolkit instance
            job_data: Job details for form filling
            
        Returns:
            Dictionary with execution results
        """
        # Define available tools for function calling
        tools = self._get_tool_definitions()
        
        context = {
            "step": step,
            "dom_state": dom_state,
            "user_details": job_data.get("user_details", self.config.get("user_details", {})),
            "resume_path": job_data.get("resume_path", self.config.get("resume_path", "")),
            "job_title": job_data["title"],
            "company": job_data.get("company", "")
        }
        
        try:
            response = self.provider.generate_browser_response(
                prompt=self.SYSTEM_PROMPT,
                tools=tools,
                context=context
            )
            
            # Log API usage
            if response.usage:
                self.structured_logger.log_api_usage(
                    provider=self.provider.get_provider_name(),
                    model=self.provider.model,
                    endpoint="generate_browser_response",
                    tokens_used=response.usage.get("total_tokens")
                )
            
            if not response.tool_calls:
                logger.warning("Browser Agent returned no tool calls")
                return {
                    "success": False,
                    "action_summary": "No actions taken",
                    "error": "No tool calls returned"
                }
            
            # Execute tool calls
            results = []
            for tool_call in response.tool_calls:
                # Handle both OpenAI format and nested function format
                if "function" in tool_call:
                    # Nested format: {"function": {"name": "...", "arguments": "..."}}
                    tool_name = tool_call["function"]["name"]
                    tool_args_str = tool_call["function"]["arguments"]
                    # Parse arguments if they're a JSON string
                    tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    # Normalize to direct format for validation
                    normalized_tool_call = {"name": tool_name, "arguments": tool_args}
                else:
                    # Direct format: {"name": "...", "arguments": {...}}
                    tool_name = tool_call["name"]
                    tool_args = tool_call["arguments"]
                    normalized_tool_call = tool_call
                
                # Validate tool name before execution
                is_valid, error_msg = self.validate_tool_call(normalized_tool_call)
                if not is_valid:
                    logger.error(f"Tool hallucination detected: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": "HALLUCINATION_ERROR",
                        "tool_name": normalized_tool_call.get("name")
                    }
                
                if self.log_interactions:
                    # Log with structured logger
                    element_data = {"mmid": tool_args.get("mmid", "unknown")}
                    if "text" in tool_args:
                        element_data["text_preview"] = str(tool_args["text"])[:50] + "..." if len(str(tool_args["text"])) > 50 else str(tool_args["text"])
                    if "file_path" in tool_args:
                        element_data["file_path"] = tool_args["file_path"]
                    if "url" in tool_args:
                        element_data["url"] = tool_args["url"]
                    if "key" in tool_args:
                        element_data["key"] = tool_args["key"]
                    
                    # Log the intent (before execution)
                    element_desc = "unknown element"
                    if "elements" in dom_state:
                        # Find the element metadata for better logging
                        target_mmid = str(tool_args.get("mmid", ""))
                        element = next((el for el in dom_state["elements"] if str(el.get("mmid")) == target_mmid), None)
                        if element:
                            # Improved hierarchy: Label > Aria-Label > Placeholder > Name > Text
                            label = (
                                element.get("label") or 
                                element.get("aria_label") or 
                                element.get("placeholder") or 
                                element.get("name") or 
                                element.get("text") or 
                                ""
                            ).strip()
                            
                            tag = element.get("tag", "element")
                            element_desc = f"'{label}' ({tag})" if label else f"({tag})"
                    
                    # Create a highly visible action log
                    action_msg = f"[ACTION] {tool_name.replace('_', ' ').title()}"
                    if element_desc != "unknown element":
                        action_msg += f" on {element_desc}"
                    
                    if "text" in tool_args:
                        action_msg += f" with value: '{tool_args['text']}'"
                    elif "value" in tool_args:
                        action_msg += f" with value: '{tool_args['value']}'"
                    elif "url" in tool_args:
                        action_msg += f" to: {tool_args['url']}"
                        
                    logger.info("%s [mmid=%s]", action_msg, tool_args.get("mmid", "N/A"))
                    
                    # Log the raw intent for debugging
                    logger.debug(
                        "Preparing to execute tool: %s on element: %s",
                        tool_name, tool_args.get("mmid", "unknown")
                    )
                
                # Execute the tool
                result = self._execute_tool(tool_name, tool_args, dom_toolkit)
                results.append(result)
                
                # Update logging if execution failed
                if self.log_interactions and not result.get("success", False):
                    self.structured_logger.log_dom_interaction(
                        action_type=tool_name,
                        element_data=element_data,
                        success=False,
                        error=result.get("action", "Unknown error")
                    )
            
            action_summary = f"Executed {len(results)} action(s): " + ", ".join(
                r.get("action", "unknown") for r in results
            )
            
            return {
                "success": all(r.get("success", False) for r in results),
                "action_summary": action_summary,
                "results": results
            }
        
        except Exception as e:
            logger.error("Browser Agent error: %s", e, exc_info=True)
            return {
                "success": False,
                "action_summary": f"Error: {str(e)}",
                "error": str(e)
            }
    
    def execute_with_retry_wrapper(
        self,
        operation: Callable[[], Dict[str, Any]],
        operation_name: str = "browser_operation"
    ) -> Dict[str, Any]:
        """
        Execute a browser operation with retry logic and exponential backoff.
        
        Wrapper around execute_with_retry that uses the agent's retry configuration.
        
        Args:
            operation: Callable that performs the operation
            operation_name: Name for logging
            
        Returns:
            Execution result dictionary
        """
        return execute_with_retry(
            operation=operation,
            retry_config=self.retry_config,
            operation_name=operation_name
        )
    
    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get OpenAI-style tool definitions for function calling"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "click_element",
                    "description": "Click an interactive element (button, link, etc.)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mmid": {
                                "type": "string",
                                "description": "The mmid attribute of the element to click"
                            }
                        },
                        "required": ["mmid"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "enter_text",
                    "description": "Type text into an input field",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mmid": {
                                "type": "string",
                                "description": "The mmid attribute of the input element"
                            },
                            "text": {
                                "type": "string",
                                "description": "The text to type"
                            }
                        },
                        "required": ["mmid", "text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "select_option",
                    "description": "Select an option from a dropdown menu (<select>)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mmid": {
                                "type": "string",
                                "description": "The mmid attribute of the <select> element"
                            },
                            "value": {
                                "type": "string",
                                "description": "The option text or value to select"
                            }
                        },
                        "required": ["mmid", "value"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "upload_file",
                    "description": "Upload a file (e.g., resume PDF)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mmid": {
                                "type": "string",
                                "description": "The mmid attribute of the file input element"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to upload"
                            }
                        },
                        "required": ["mmid", "file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "press_key",
                    "description": "Press a keyboard key",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Key to press (e.g., 'Enter', 'Tab')"
                            }
                        },
                        "required": ["key"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "navigate",
                    "description": "Navigate to a URL",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to navigate to"
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]
    
    def wait_for_page_ready(self, timeout: int = 30000):
        """
        Wait for page to be ready for interaction using adaptive wait strategies.
        
        Implements intelligent wait logic:
        1. Wait for domcontentloaded event
        2. Detect and wait for loading indicators to disappear
        3. Use configurable timeout
        
        Validates Requirements: 15.1, 15.3
        
        Args:
            timeout: Maximum wait time in milliseconds (default: 30000)
        """
        if not self.page:
            logger.warning("Cannot wait for page ready: Playwright page not set")
            return
        
        start_time = datetime.now()
        
        try:
            # Step 1: Wait for domcontentloaded event
            logger.debug("Waiting for domcontentloaded event")
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
            logger.debug("DOM content loaded")
            
            # Step 2: Detect and wait for loading indicators to disappear
            self._wait_for_loading_indicators(timeout=timeout)
            
            # Calculate duration
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Log wait operation
            self.structured_logger.log_wait_operation(
                wait_type="page_ready",
                duration_ms=duration_ms,
                outcome="success",
                context={"url": self.page.url if self.page else "unknown"}
            )
            
            logger.info("Page ready for interaction")
            
        except Exception as e:
            # Calculate duration
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Log wait operation timeout
            self.structured_logger.log_wait_operation(
                wait_type="page_ready",
                duration_ms=duration_ms,
                outcome="timeout",
                context={
                    "url": self.page.url if self.page else "unknown",
                    "error": str(e)
                }
            )
            
            logger.warning(f"Wait for page ready timeout (non-critical): {e}")
    
    def _wait_for_loading_indicators(self, timeout: int = 30000):
        """
        Detect loading indicators and wait for them to disappear.
        
        Common loading indicators:
        - Spinners (class/id containing 'spinner', 'loading', 'loader')
        - Progress bars (class/id containing 'progress')
        - Overlay elements (class/id containing 'overlay', 'modal')
        
        Validates Requirements: 15.3
        
        Args:
            timeout: Maximum wait time in milliseconds
        """
        if not self.page:
            return
        
        try:
            # Common loading indicator selectors
            loading_selectors = [
                "[class*='spinner']",
                "[class*='loading']",
                "[class*='loader']",
                "[id*='spinner']",
                "[id*='loading']",
                "[id*='loader']",
                "[class*='progress']",
                "[class*='overlay']",
                ".spinner",
                ".loading",
                ".loader",
                "#loading",
                "#spinner"
            ]
            
            # Check for each loading indicator type
            for selector in loading_selectors:
                try:
                    # Check if loading indicator exists and is visible
                    locator = self.page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        logger.debug(f"Loading indicator detected: {selector}, waiting for it to disappear")
                        # Wait for it to be hidden (with timeout)
                        locator.wait_for(state="hidden", timeout=min(timeout, 10000))
                        logger.debug(f"Loading indicator disappeared: {selector}")
                except Exception as e:
                    # Timeout or not found is OK - continue checking other indicators
                    logger.debug(f"No loading indicator for selector {selector}: {e}")
                    continue
            
            logger.debug("All loading indicators cleared")
            
        except Exception as e:
            logger.debug(f"Error checking loading indicators: {e}")
    
    def calculate_adaptive_wait_time(self, element_count: int) -> int:
        """
        Calculate adaptive wait time based on page complexity (number of elements).
        
        More elements = longer wait time, capped at maximum.
        
        Formula:
        - Base wait: 1000ms
        - Additional wait: 100ms per 10 elements
        - Maximum wait: 10000ms (10 seconds)
        
        Validates Requirements: 15.5
        
        Args:
            element_count: Number of elements on the page
            
        Returns:
            Wait time in milliseconds
        """
        base_wait_ms = 1000
        additional_wait_per_10_elements = 100
        max_wait_ms = 10000
        
        # Calculate additional wait based on element count
        additional_wait = (element_count // 10) * additional_wait_per_10_elements
        
        # Total wait time
        total_wait = base_wait_ms + additional_wait
        
        # Cap at maximum
        adaptive_wait = min(total_wait, max_wait_ms)
        
        logger.debug(
            f"Adaptive wait calculated: {adaptive_wait}ms "
            f"(element_count={element_count}, base={base_wait_ms}ms, "
            f"additional={additional_wait}ms, max={max_wait_ms}ms)"
        )
        
        return adaptive_wait
    
    def wait_for_element(
        self,
        selector: str,
        timeout: int = 30000,
        max_retries: int = 5,
        retry_interval: int = 1000
    ) -> bool:
        """
        Wait for an element to appear with retry logic.
        
        Implements retry logic for element detection:
        - Retries up to max_retries times
        - Waits retry_interval milliseconds between retries
        - Uses Playwright's wait_for_selector with configurable timeout
        
        Validates Requirements: 15.2, 15.4
        
        Args:
            selector: CSS selector or XPath for the element
            timeout: Timeout for each wait attempt in milliseconds (default: 30000)
            max_retries: Maximum number of retry attempts (default: 5)
            retry_interval: Wait time between retries in milliseconds (default: 1000)
            
        Returns:
            True if element found, False otherwise
        """
        if not self.page:
            logger.warning("Cannot wait for element: Playwright page not set")
            return False
        
        start_time = datetime.now()
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(
                    f"Waiting for element (attempt {attempt}/{max_retries}): {selector}"
                )
                
                # Use Playwright's wait_for_selector with timeout
                self.page.wait_for_selector(selector, timeout=timeout, state="visible")
                
                # Calculate duration
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # Log successful wait operation
                self.structured_logger.log_wait_operation(
                    wait_type="element",
                    duration_ms=duration_ms,
                    outcome="success",
                    context={
                        "selector": selector,
                        "attempts": attempt,
                        "max_retries": max_retries
                    }
                )
                
                logger.info(f"Element found on attempt {attempt}: {selector}")
                return True
                
            except Exception as e:
                if attempt < max_retries:
                    logger.debug(
                        f"Element not found on attempt {attempt}, retrying in {retry_interval}ms: {e}"
                    )
                    # Wait before retry
                    self.page.wait_for_timeout(retry_interval)
                else:
                    # Calculate duration
                    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    
                    # Log failed wait operation
                    self.structured_logger.log_wait_operation(
                        wait_type="element",
                        duration_ms=duration_ms,
                        outcome="not_found",
                        context={
                            "selector": selector,
                            "attempts": max_retries,
                            "max_retries": max_retries,
                            "error": str(e)
                        }
                    )
                    
                    logger.warning(
                        f"Element not found after {max_retries} attempts: {selector}"
                    )
                    return False
        
        return False
    
    def _execute_tool(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any], 
        dom_toolkit
    ) -> Dict[str, Any]:
        """Execute a single tool call"""
        try:
            if tool_name == "click_element":
                dom_toolkit.click_element(tool_args["mmid"])
                return {"success": True, "action": f"Clicked mmid={tool_args['mmid']}"}
            
            elif tool_name == "enter_text":
                dom_toolkit.enter_text(tool_args["mmid"], tool_args["text"])
                return {"success": True, "action": f"Entered text into mmid={tool_args['mmid']}"}
            
            elif tool_name == "select_option":
                dom_toolkit.select_option(tool_args["mmid"], tool_args["value"])
                return {"success": True, "action": f"Selected option '{tool_args['value']}' in mmid={tool_args['mmid']}"}
            
            elif tool_name == "upload_file":
                dom_toolkit.upload_file(tool_args["mmid"], tool_args["file_path"])
                return {"success": True, "action": f"Uploaded file to mmid={tool_args['mmid']}"}
            
            elif tool_name == "press_key":
                dom_toolkit.press_key(tool_args["key"])
                return {"success": True, "action": f"Pressed key: {tool_args['key']}"}
            
            elif tool_name == "navigate":
                dom_toolkit.navigate(tool_args["url"])
                # Wait for page to be ready after navigation (non-critical)
                try:
                    self.wait_for_page_ready()
                except Exception as e:
                    logger.debug(f"Wait for page ready after navigation failed (non-critical): {e}")
                return {"success": True, "action": f"Navigated to {tool_args['url']}"}
            
            else:
                logger.warning("Unknown tool: %s", tool_name)
                return {"success": False, "action": f"Unknown tool: {tool_name}"}
        
        except Exception as e:
            logger.error("Tool execution error (%s): %s", tool_name, e)
            return {"success": False, "action": f"Error in {tool_name}: {str(e)}"}
