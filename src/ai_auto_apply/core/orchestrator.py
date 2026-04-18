"""
FSM Orchestrator

Finite State Machine orchestrator for AI auto-apply workflow.
"""

import os
from typing import Dict, Any, Optional
from src.common.logger import get_logger
from src.ai_auto_apply.agents.planner_agent import PlannerAgent
from src.ai_auto_apply.agents.browser_agent import BrowserAgent
from src.ai_auto_apply.tools.dom_tools import DOMToolkit
from src.ai_auto_apply.core.anti_spam_tracker import AntiSpamTracker
from src.ai_auto_apply.core.structured_logger import StructuredLogger
from src.ai_auto_apply.core.career_page_validator import CareerPageValidator
from src.ai_auto_apply.core.mcp_client import MCPClient
from src.ai_auto_apply.tools.homepage_navigator import HomepageNavigator
from playwright.sync_api import sync_playwright
import time

logger = get_logger("fsm_orchestrator")


class FSMOrchestrator:
    """Finite State Machine orchestrator for AI auto-apply workflow"""
    
    def __init__(self, provider, config: Dict[str, Any], excel_path: str):
        """
        Initialize FSM orchestrator.
        
        Args:
            provider: AIProvider instance
            config: auto_apply configuration dictionary
            excel_path: Path to master Excel file
        """
        self.provider = provider
        self.config = config
        self.max_iterations = config.get("fsm", {}).get("max_iterations", 20)
        self.page_load_timeout = config.get("fsm", {}).get("page_load_timeout", 30)
        
        # Initialize MCP client
        self.mcp_client = self._initialize_mcp_client()
        
        # Initialize agents with MCP client
        self.planner = PlannerAgent(provider, config, mcp_client=self.mcp_client)
        self.browser_agent = BrowserAgent(provider, config, mcp_client=self.mcp_client)
        
        # Initialize anti-spam tracker
        self.tracker = AntiSpamTracker(excel_path)
        
        # Initialize career page validator
        self.validator = CareerPageValidator(config.get("validation", {}))
        
        # Initialize structured logger
        self.structured_logger = StructuredLogger("orchestrator", config.get("logging", {}))
        
        # Initialize browser
        self.page = None
        
        # Run screenshot cleanup on initialization
        self._cleanup_old_screenshots()
        
        logger.info("FSMOrchestrator initialized: max_iterations=%d", self.max_iterations)
    
    def _initialize_mcp_client(self) -> Optional[MCPClient]:
        """
        Initialize MCP client from configuration with validation.
        
        Returns:
            MCPClient instance if successful, None if disabled or failed
        """
        mcp_config = self.config.get("mcp", {})
        
        if not mcp_config.get("enabled", False):
            logger.info("MCP integration disabled in configuration")
            return None
        
        # Validate configuration before attempting to create client
        is_valid, error_message = MCPClient.validate_config(mcp_config)
        if not is_valid:
            logger.error(f"MCP configuration validation failed: {error_message}")
            return None
        
        # Load MCP server configuration from file if config_path is specified
        config_path = mcp_config.get("config_path")
        if config_path:
            try:
                import json
                with open(config_path, 'r') as f:
                    mcp_server_config = json.load(f)
                    # Extract the playwright server config
                    playwright_config = mcp_server_config.get("mcpServers", {}).get("playwright", {})
                    if playwright_config:
                        mcp_config = playwright_config
                        logger.info(f"Loaded MCP configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load MCP config from {config_path}: {e}")
        
        try:
            mcp_client = MCPClient(mcp_config)
            if mcp_client.connect():
                logger.info("MCP client initialized and connected successfully")
                return mcp_client
            else:
                logger.error("MCP client connection failed")
                return None
        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}", exc_info=True)
            return None
    
    def _shutdown_mcp_client(self):
        """Clean up MCP client connection"""
        if self.mcp_client:
            try:
                self.mcp_client.disconnect()
                logger.info("MCP client disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting MCP client: {e}")
    
    def _ai_driven_homepage_navigation(self, job_data: Dict[str, Any]) -> bool:
        """
        Navigate from homepage to careers page using Accessibility Tree + AI.
        
        Uses the industry-standard approach:
        1. Get compact accessibility tree snapshot (not raw HTML)
        2. AI analyzes the tree to find careers/jobs links
        3. Execute navigation via Playwright role-based locators
        4. Verify destination page
        
        This uses ~700 tokens per attempt vs ~5000 with the old HTML approach.
        
        Args:
            job_data: Job details
            
        Returns:
            True if navigation successful, False otherwise
        """
        logger.info("Starting AI-driven homepage navigation (Accessibility Tree)")
        
        # Initialize DOM toolkit for this page
        from src.ai_auto_apply.tools.dom_tools import DOMToolkit
        nav_toolkit = DOMToolkit(self.page)
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            logger.info(f"AI navigation attempt {attempt}/{max_attempts}")
            
            # Step 1: Get compact accessibility tree (depth=3 for navigation)
            ax_snapshot = nav_toolkit.get_accessibility_snapshot(depth=4)
            
            if not ax_snapshot:
                logger.warning("Accessibility tree unavailable, falling back to legacy approach")
                # Fallback to old regex method
                page_html = self.page.content()
                current_url = self.page.url
                page_analysis = self.planner.analyze_page_with_ai(page_html, current_url)
                if page_analysis.get("careers_links"):
                    best_link = self.planner.select_best_careers_link(page_analysis["careers_links"])
                    if best_link and best_link.get('href'):
                        self.page.goto(best_link['href'], wait_until="domcontentloaded")
                        time.sleep(3)
                        if self._verify_careers_page():
                            return True
                continue
            
            current_url = self.page.url
            snapshot_size = len(ax_snapshot)
            logger.info(f"Accessibility tree: {snapshot_size} chars (page: {current_url})")
            
            # Step 2: Ask AI to find the careers link from the tree
            nav_result = self.planner.find_careers_link_from_ax_tree(
                ax_snapshot=ax_snapshot,
                current_url=current_url,
                company=job_data.get("company", "")
            )
            
            if not nav_result:
                logger.warning(f"AI could not find careers link on attempt {attempt}")
                if attempt < max_attempts:
                    time.sleep(2)
                    continue
                return False
            
            # Step 3: Execute navigation
            action_type = nav_result.get("action", "click_ref")
            
            try:
                self._close_modal_popups()
                
                if action_type == "navigate_url" and nav_result.get("url"):
                    # AI found a direct URL to navigate to
                    careers_url = nav_result["url"]
                    logger.info(f"AI: Navigate to URL: {careers_url}")
                    self.page.goto(careers_url, wait_until="domcontentloaded")
                    time.sleep(3)
                    
                elif action_type == "click_ref" and nav_result.get("ref"):
                    # AI picked an element by reference number
                    ref_id = nav_result["ref"]
                    el_info = nav_toolkit.get_element_by_ref(ref_id)
                    logger.info(f"AI: Click [{ref_id}] {el_info.get('role')} '{el_info.get('name')}'")
                    nav_toolkit.click_by_ref(ref_id)
                    time.sleep(3)
                    
                elif action_type == "click_text" and nav_result.get("text"):
                    # AI specified text to click
                    link_text = nav_result["text"]
                    logger.info(f"AI: Click link with text: '{link_text}'")
                    self.page.get_by_role("link", name=link_text).first.click()
                    time.sleep(3)
                    
                else:
                    logger.warning(f"AI returned unknown action: {nav_result}")
                    if attempt < max_attempts:
                        continue
                    return False
                
                # Step 4: Verify we're on careers page
                if self._verify_careers_page():
                    logger.info(f"Successfully navigated to careers page: {self.page.url}")
                    return True
                else:
                    logger.warning(f"Navigation succeeded but not on careers page (attempt {attempt})")
                    if attempt < max_attempts:
                        self.page.go_back()
                        time.sleep(2)
                        continue
            
            except Exception as e:
                logger.error(f"Navigation failed: {e}")
                if attempt < max_attempts:
                    continue
                return False
        
        return False
    
    def _verify_careers_page(self) -> bool:
        """
        Verify current page is a careers page by checking content.
        
        Checks for:
        - Job listings
        - Application forms
        - Career-related content
        
        Returns:
            True if on careers page, False otherwise
        """
        try:
            page_html = self.page.content().lower()
            current_url = self.page.url.lower()
            
            # Check URL
            if "career" in current_url or "job" in current_url:
                return True
            
            # Check for job-related keywords in content
            job_keywords = ["job", "position", "career", "apply", "opening", "opportunity"]
            keyword_count = sum(1 for keyword in job_keywords if keyword in page_html)
            
            if keyword_count >= 3:
                return True
            
            # Check for form fields (application forms)
            form_count = page_html.count("<input") + page_html.count("<textarea")
            if form_count >= 3:
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Careers page verification failed: {e}")
            return False
    
    def _close_modal_popups(self):
        """
        Close common modal popups that might block navigation.
        
        Uses Accessibility Tree + AI to dynamically locate and dismiss:
        - Cookie consent modals ("Accept All", "Decline")
        - Newsletter popups ("No thanks", "X")
        - Geo-location and arbitrary overlays
        """
        try:
            logger.info("Checking for popups/cookie banners to dismiss...")
            from src.ai_auto_apply.tools.dom_tools import DOMToolkit
            toolkit = DOMToolkit(self.page)
            
            # 1. Get compact AX tree (depth=4 is enough for most popups/banners)
            ax_snapshot = toolkit.get_accessibility_snapshot(depth=4)
            if not ax_snapshot:
                logger.debug("No AX tree available to check for popups.")
                return
            
            # 2. Ask AI to find dismiss button
            result = self.planner.find_popup_dismiss_action(
                ax_snapshot=ax_snapshot,
                current_url=self.page.url
            )
            
            # 3. Execute the dismiss action if found
            if result and result.get("action") == "click_ref" and result.get("ref"):
                ref_id = result["ref"]
                el_info = toolkit.get_element_by_ref(ref_id)
                logger.info(f"AI identified popup dismiss button: [{ref_id}] {el_info.get('role')} '{el_info.get('name')}'")
                try:
                    toolkit.click_by_ref(ref_id)
                    time.sleep(1.5)  # Let popup animation finish
                    logger.info("Popup dismissed successfully.")
                except Exception as e:
                    logger.warning(f"Failed to click popup dismiss button: {e}")
            else:
                logger.debug("No blocking popups detected by AI.")
                
        except Exception as e:
            logger.debug(f"Modal popup closing encountered non-critical error: {e}")
    
    
    def _cleanup_old_screenshots(self):
        """
        Clean up old screenshots based on retention policy.
        
        Deletes screenshots older than the configured retention period.
        Default retention: 30 days
        """
        try:
            screenshot_config = self.config.get("screenshots", {})
            retention_days = screenshot_config.get("retention_days", 30)
            screenshot_dir = screenshot_config.get("directory", "logs/screenshots")
            
            if not os.path.exists(screenshot_dir):
                logger.debug("Screenshot directory does not exist, skipping cleanup")
                return
            
            from datetime import datetime, timedelta
            import time
            
            cutoff_time = time.time() - (retention_days * 24 * 60 * 60)
            deleted_count = 0
            
            # Walk through screenshot directory
            for root, dirs, files in os.walk(screenshot_dir):
                for filename in files:
                    if filename.endswith('.png'):
                        file_path = os.path.join(root, filename)
                        try:
                            # Check file modification time
                            file_mtime = os.path.getmtime(file_path)
                            if file_mtime < cutoff_time:
                                os.remove(file_path)
                                deleted_count += 1
                                logger.debug(f"Deleted old screenshot: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete screenshot {file_path}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Screenshot cleanup: deleted {deleted_count} screenshots older than {retention_days} days")
            else:
                logger.debug(f"Screenshot cleanup: no screenshots older than {retention_days} days found")
        
        except Exception as e:
            logger.error(f"Screenshot cleanup failed: {e}", exc_info=True)
    
    def _get_network_request_summary(self) -> Dict[str, Any]:
        """
        Get summary of network requests for inclusion in application reports.
        
        Returns:
            Dictionary with network request statistics and form submission info
        """
        if not self.browser_agent.network_monitoring_enabled:
            return {}
        
        network_requests = self.browser_agent.get_network_requests(clear=False)
        
        if not network_requests:
            return {"network_requests_count": 0}
        
        # Calculate statistics
        total_requests = len(network_requests)
        xhr_fetch_requests = [r for r in network_requests if r.get("resource_type") in ["xhr", "fetch"]]
        post_requests = [r for r in network_requests if r["method"] == "POST"]
        
        # Calculate average response time
        response_times = [r.get("response_time_ms") for r in network_requests if r.get("response_time_ms")]
        avg_response_time = sum(response_times) / len(response_times) if response_times else None
        
        # Check for form submission
        form_submission = self.browser_agent.detect_form_submission()
        
        summary = {
            "network_requests_count": total_requests,
            "xhr_fetch_count": len(xhr_fetch_requests),
            "post_requests_count": len(post_requests),
            "avg_response_time_ms": round(avg_response_time, 2) if avg_response_time else None,
            "form_submission_detected": form_submission is not None,
        }
        
        if form_submission:
            summary["form_submission"] = {
                "url": form_submission["url"],
                "status_code": form_submission["status_code"],
                "success": form_submission["success"]
            }
        
        return summary
    
    def _get_mcp_metrics_summary(self) -> Dict[str, Any]:
        """
        Get summary of MCP metrics for inclusion in application reports.
        
        Returns:
            Dictionary with MCP operation statistics
        """
        if not self.mcp_client:
            return {"mcp_enabled": False}
        
        try:
            metrics = self.mcp_client.get_metrics()
            
            return {
                "mcp_enabled": True,
                "mcp_total_calls": metrics.get("total_calls", 0),
                "mcp_total_errors": metrics.get("total_errors", 0),
                "mcp_error_rate": round(metrics.get("error_rate", 0.0), 2),
                "mcp_avg_latency_ms": round(metrics.get("average_latency_ms", 0.0), 2),
                "mcp_p95_latency_ms": round(metrics.get("p95_latency_ms", 0.0), 2),
                "mcp_p99_latency_ms": round(metrics.get("p99_latency_ms", 0.0), 2),
                "mcp_per_tool_metrics": metrics.get("per_tool_metrics", {})
            }
        except Exception as e:
            logger.warning(f"Failed to get MCP metrics: {e}")
            return {"mcp_enabled": True, "mcp_metrics_error": str(e)}
    
    def apply_to_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply to a single job using FSM workflow.
        
        Args:
            job_data: Dictionary with job details (title, company, career_url, etc.)
            
        Returns:
            Dictionary with status and details:
            {
                "status": "success" | "failed",
                "reason": str,
                "iterations": int,
                "actions_taken": List[str]
            }
        """
        career_url = job_data["career_url"]
        excel_index = job_data["excel_index"]
        
        logger.info("Starting FSM for job: %s at %s", 
                   job_data["title"], job_data["company"])
        
        # STEP 1: Validate career page URL before attempting to apply
        logger.info("Validating career page: %s", career_url)
        validation_status, validation_reason = self.validator.validate(
            url=career_url,
            company_name=job_data["company"]
        )
        
        if validation_status != "Yes":
            logger.warning("Career page validation failed: %s - %s", career_url, validation_reason)
            
            self.tracker.mark_failed(
                excel_index=excel_index,
                reason=f"Invalid career page: {validation_reason}"
            )
            
            self.structured_logger.log_application_result(
                job_title=job_data["title"],
                company=job_data["company"],
                status="failed",
                reason=f"Invalid career page: {validation_reason}",
                metrics={
                    "iterations": 0,
                    "actions_taken": [],
                    "career_url": career_url,
                    "failure_type": "validation_failure",
                    "validation_status": validation_status
                }
            )
            
            return {
                "status": "failed",
                "reason": f"Invalid career page: {validation_reason}",
                "iterations": 0,
                "actions_taken": []
            }
        
        logger.info("Career page validation passed: %s", career_url)
        
        # Check if homepage redirect was detected
        is_homepage_redirect = "homepage redirect" in validation_reason.lower()
        
        iteration = 0
        actions_taken = []
        
        try:
            # Initialize Playwright browser and navigate to career page
            self.playwright = sync_playwright().start()
            headless = self.config.get("browser", {}).get("headless", False)
            self.browser = self.playwright.chromium.launch(headless=headless)
            self.page = self.browser.new_page()
            self.page.set_default_timeout(self.page_load_timeout * 1000)
            
            # Set page instance in browser agent for screenshot capture
            self.browser_agent.set_page(self.page)
            
            logger.debug("Navigating to %s", career_url)
            self.page.goto(career_url, wait_until="domcontentloaded")
            
            # Wait for page to fully load (configurable, default 5s)
            page_wait_seconds = self.config.get("browser", {}).get("page_load_wait_seconds", 5)
            logger.debug("Waiting %ds for page JavaScript to execute...", page_wait_seconds)
            time.sleep(page_wait_seconds)
            
            # Close any modal popups that might have appeared
            self._close_modal_popups()
            
            # STEP 2: Handle homepage redirect - navigate to careers page
            if is_homepage_redirect:
                logger.info("Homepage redirect detected, attempting to navigate to careers page")
                
                # Define max attempts (used for both AI and legacy modes)
                max_homepage_attempts = 3
                
                # Use AI-driven navigation if available, otherwise use legacy
                if self.planner.provider:  # Check if AI provider is available
                    logger.info("Using AI-driven homepage navigation")
                    homepage_navigation_success = self._ai_driven_homepage_navigation(job_data)
                else:
                    logger.info("Using legacy homepage navigation (MCP not available)")
                    # Instantiate HomepageNavigator
                    homepage_navigator = HomepageNavigator(self.page, self.config)
                    
                    # Track navigation attempts
                    homepage_navigation_success = False
                    
                    for attempt in range(1, max_homepage_attempts + 1):
                        logger.info(f"Homepage navigation attempt {attempt}/{max_homepage_attempts}")
                        
                        # Log navigation attempt with current URL
                        logger.info(
                            f"Attempting homepage navigation: original_url={career_url}, "
                            f"current_url={self.page.url}, attempt={attempt}"
                        )
                        
                        # Try to navigate to careers page
                        navigation_result = homepage_navigator.navigate_to_careers()
                        
                        if navigation_result:
                            # Verify we're on careers page
                            if homepage_navigator.verify_on_careers_page():
                                logger.info(
                                    f"[OK] Successfully navigated to careers page on attempt {attempt}: "
                                    f"{career_url} -> {self.page.url}"
                                )
                                homepage_navigation_success = True
                                
                                # Wait for page to fully load
                                time.sleep(3)
                                break
                            else:
                                logger.warning(
                                    f"[FAIL] Navigation succeeded but not on careers page (attempt {attempt}): "
                                    f"current_url={self.page.url}"
                                )
                        else:
                            logger.warning(
                                f"[FAIL] Failed to find/click careers link (attempt {attempt}): "
                                f"current_url={self.page.url}"
                            )
                        
                        # Wait before retry
                        if attempt < max_homepage_attempts:
                            logger.debug("Waiting 2 seconds before retry...")
                            time.sleep(2)
                
                # Check if homepage navigation failed after all attempts
                if not homepage_navigation_success:
                    logger.error(
                        f"[FAIL] Failed to navigate to careers page after {max_homepage_attempts} attempts: "
                        f"original_url={career_url}, final_url={self.page.url}"
                    )
                    
                    # Get network request summary
                    network_summary = self._get_network_request_summary()
                    
                    # Capture screenshot on failure
                    job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
                    self.browser_agent.capture_screenshot("homepage_navigation_failed", job_id)
                    
                    self.tracker.mark_failed(
                        excel_index=excel_index,
                        reason=f"Cannot find careers page from homepage after {max_homepage_attempts} attempts"
                    )
                    
                    self.structured_logger.log_application_result(
                        job_title=job_data["title"],
                        company=job_data["company"],
                        status="failed",
                        reason=f"Cannot navigate to careers page from homepage",
                        metrics={
                            "iterations": 0,
                            "actions_taken": [],
                            "career_url": career_url,
                            "failure_type": "homepage_navigation_failure",
                            "homepage_attempts": max_homepage_attempts,
                            "final_url": self.page.url,
                            **network_summary  # Include network request data
                        }
                    )
                    
                    return {
                        "status": "failed",
                        "reason": f"Cannot find careers page from homepage after {max_homepage_attempts} attempts",
                        "iterations": 0,
                        "actions_taken": []
                    }
            
            # Initialize DOM toolkit
            dom_toolkit = DOMToolkit(self.page)
            
            # Inject mmid attributes (kept for action execution fallback)
            dom_toolkit.inject_mmids()
            
            # FSM loop
            hallucination_count = 0  # Track consecutive hallucinations
            while iteration < self.max_iterations:
                iteration += 1
                logger.debug("FSM iteration %d/%d", iteration, self.max_iterations)
                
                # Get accessibility tree snapshot (primary context for AI - token efficient)
                ax_snapshot = dom_toolkit.get_accessibility_snapshot(depth=7)
                
                # Get mmid-based DOM state (fallback for action execution)
                dom_state = dom_toolkit.get_dom_state()
                
                # Attach AX snapshot to dom_state so planner can use it
                if ax_snapshot:
                    dom_state["ax_snapshot"] = ax_snapshot
                    logger.debug("AX tree: %d chars, DOM state: %d elements", 
                               len(ax_snapshot), len(dom_state.get("elements", [])))
                
                elements = dom_state.get("elements", [])
                element_count = len(elements)
                
                logger.debug("DOM state: %d interactive elements found", element_count)
                
                # If absolutely NO elements exist (page failed to load), wait and retry
                if element_count == 0:
                    if iteration >= 3:  # Give it 3 tries for page to load
                        logger.warning("No interactive elements found after %d iterations. Page may have failed to load.", iteration)
                        
                        # Capture screenshot on page load failure
                        job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
                        self.browser_agent.capture_screenshot("page_load_failure", job_id)
                        
                        self.tracker.mark_failed(
                            excel_index=excel_index,
                            reason=f"Page failed to load - no elements detected after {iteration} attempts"
                        )
                        
                        self.structured_logger.log_application_result(
                            job_title=job_data["title"],
                            company=job_data["company"],
                            status="failed",
                            reason="Page failed to load - no interactive elements detected",
                            metrics={
                                "iterations": iteration,
                                "actions_taken": actions_taken,
                                "career_url": job_data["career_url"],
                                "failure_type": "page_load_failure"
                            }
                        )
                        
                        return {
                            "status": "failed",
                            "reason": "Page failed to load - no interactive elements detected",
                            "iterations": iteration,
                            "actions_taken": actions_taken
                        }
                    else:
                        # Wait for page to load
                        logger.info("No elements found yet, waiting 3 seconds for page to load...")
                        time.sleep(3)
                        dom_toolkit.inject_mmids()
                        continue
                
                # Planner decides next step
                planner_response = self.planner.plan_next_step(
                    job_data=job_data,
                    dom_state=dom_state,
                    iteration=iteration,
                    actions_taken=actions_taken
                )
                
                logger.info("Planner decision: %s (status: %s)",
                           planner_response.get("next_step", "(no step)"),
                           planner_response.get("status", "(no status)"))
                
                # Check termination conditions
                if planner_response["status"] == "success":
                    logger.info("Application successful after %d iterations", iteration)
                    
                    # Get network request summary
                    network_summary = self._get_network_request_summary()
                    
                    # Get MCP metrics summary
                    mcp_summary = self._get_mcp_metrics_summary()
                    
                    # Update Excel: mark as AI-Applied
                    self.tracker.mark_applied(
                        excel_index=excel_index,
                        status="success",
                        notes=f"Applied successfully. {planner_response.get('reasoning', '')}"
                    )
                    
                    # Log with structured logger
                    self.structured_logger.log_application_result(
                        job_title=job_data["title"],
                        company=job_data["company"],
                        status="success",
                        reason=planner_response.get("reasoning", ""),
                        metrics={
                            "iterations": iteration,
                            "actions_taken": actions_taken,
                            "career_url": job_data["career_url"],
                            **network_summary,  # Include network request data
                            **mcp_summary  # Include MCP metrics
                        }
                    )
                    
                    return {
                        "status": "success",
                        "reason": planner_response.get("reasoning", ""),
                        "iterations": iteration,
                        "actions_taken": actions_taken
                    }
                
                elif planner_response["status"] == "failed":
                    logger.warning("Application failed: %s", planner_response.get("reasoning"))
                    
                    # Get network request summary
                    network_summary = self._get_network_request_summary()
                    
                    # Get MCP metrics summary
                    mcp_summary = self._get_mcp_metrics_summary()
                    
                    # Capture screenshot on application failure
                    job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
                    self.browser_agent.capture_screenshot("application_failed", job_id)
                    
                    # Update Excel: log failure
                    self.tracker.mark_failed(
                        excel_index=excel_index,
                        reason=planner_response.get("reasoning", "Unknown failure")
                    )
                    
                    # Log with structured logger
                    self.structured_logger.log_application_result(
                        job_title=job_data["title"],
                        company=job_data["company"],
                        status="failed",
                        reason=planner_response.get("reasoning", "Unknown failure"),
                        metrics={
                            "iterations": iteration,
                            "actions_taken": actions_taken,
                            "career_url": job_data["career_url"],
                            "failure_type": "planner_failure",
                            **network_summary,  # Include network request data
                            **mcp_summary  # Include MCP metrics
                        }
                    )
                    
                    return {
                        "status": "failed",
                        "reason": planner_response.get("reasoning", "Unknown failure"),
                        "iterations": iteration,
                        "actions_taken": actions_taken
                    }
                
                # Browser Agent executes the step
                browser_response = self.browser_agent.execute_step(
                    step=planner_response["next_step"],
                    dom_state=dom_state,
                    dom_toolkit=dom_toolkit,
                    job_data=job_data
                )
                
                # Check for hallucination error
                if browser_response.get("error_type") == "HALLUCINATION_ERROR":
                    hallucination_count += 1
                    tool_name = browser_response.get("tool_name", "unknown")
                    logger.warning(f"Hallucination detected (count: {hallucination_count}): {browser_response.get('error')}")
                    
                    # Create correction message for next AI iteration
                    correction_msg = (
                        f"ERROR: You used an invalid tool name '{tool_name}'. "
                        f"Valid tools are: click_element, enter_text, select_option, upload_file, press_key, navigate. "
                        f"Please retry using ONLY these tools."
                    )
                    
                    # Append correction message to planner's context for next iteration
                    # The planner will receive this feedback in its next plan_next_step call
                    if not hasattr(self.planner, 'correction_messages'):
                        self.planner.correction_messages = []
                    self.planner.correction_messages.append(correction_msg)
                    
                    # Fail-fast: Terminate after 3 consecutive hallucinations
                    if hallucination_count >= 3:
                        logger.error("Fail-fast: 3 consecutive hallucinations detected. Terminating.")
                        
                        # Get network request summary
                        network_summary = self._get_network_request_summary()
                        
                        # Get MCP metrics summary
                        mcp_summary = self._get_mcp_metrics_summary()
                        
                        # Capture screenshot on hallucination failure
                        job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
                        self.browser_agent.capture_screenshot("hallucination_failure", job_id)
                        
                        # Update Excel: mark as failed
                        self.tracker.mark_failed(
                            excel_index=excel_index,
                            reason="AI model repeatedly hallucinating tool names. Consider using a better model."
                        )
                        
                        # Log with structured logger
                        self.structured_logger.log_application_result(
                            job_title=job_data["title"],
                            company=job_data["company"],
                            status="failed",
                            reason="AI model repeatedly hallucinating tool names. Consider using a better model.",
                            metrics={
                                "iterations": iteration,
                                "actions_taken": actions_taken,
                                "career_url": job_data["career_url"],
                                "failure_type": "hallucination_failure",
                                "hallucination_count": hallucination_count,
                                **network_summary,
                                **mcp_summary
                            }
                        )
                        
                        return {
                            "status": "failed",
                            "reason": "AI model repeatedly hallucinating tool names. Consider using a better model.",
                            "iterations": iteration,
                            "hallucination_count": hallucination_count
                        }
                else:
                    # Reset hallucination count on successful execution
                    hallucination_count = 0
                
                # Log action taken
                action_summary = f"Iteration {iteration}: {browser_response.get('action_summary', 'Unknown action')}"
                actions_taken.append(action_summary)
                logger.debug("Browser action: %s", action_summary)
                
                # Optionally capture screenshot at each iteration (if configured)
                if self.browser_agent.screenshot_each_iteration:
                    job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
                    self.browser_agent.capture_screenshot(f"iteration_{iteration}", job_id)
                
                # Re-inject mmids after page changes
                dom_toolkit.inject_mmids()
            
            # Max iterations reached
            logger.warning("Max iterations (%d) reached without completion", self.max_iterations)
            
            # Capture screenshot on timeout
            job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
            self.browser_agent.capture_screenshot("max_iterations_timeout", job_id)
            
            # Get network request summary
            network_summary = self._get_network_request_summary()
            
            # Get MCP metrics summary
            mcp_summary = self._get_mcp_metrics_summary()
            
            self.tracker.mark_failed(
                excel_index=excel_index,
                reason=f"Timeout: Max iterations ({self.max_iterations}) reached"
            )
            
            # Log with structured logger
            self.structured_logger.log_application_result(
                job_title=job_data["title"],
                company=job_data["company"],
                status="failed",
                reason=f"Timeout after {self.max_iterations} iterations",
                metrics={
                    "iterations": iteration,
                    "actions_taken": actions_taken,
                    "career_url": job_data["career_url"],
                    "failure_type": "max_iterations",
                    **network_summary,  # Include network request data
                    **mcp_summary  # Include MCP metrics
                }
            )
            
            return {
                "status": "failed",
                "reason": f"Timeout after {self.max_iterations} iterations",
                "iterations": iteration,
                "actions_taken": actions_taken
            }
        
        except Exception as e:
            logger.error("FSM error for job at %s: %s", job_data["company"], e, exc_info=True)
            
            # Get network request summary
            try:
                network_summary = self._get_network_request_summary()
            except Exception:
                network_summary = {}  # Don't fail if network summary fails
            
            # Get MCP metrics summary
            try:
                mcp_summary = self._get_mcp_metrics_summary()
            except Exception:
                mcp_summary = {}  # Don't fail if MCP metrics fail
            
            # Capture screenshot on exception
            try:
                job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
                self.browser_agent.capture_screenshot("exception_error", job_id)
            except Exception:
                pass  # Don't fail if screenshot capture fails
            
            self.tracker.mark_failed(
                excel_index=excel_index,
                reason=f"Error: {str(e)[:100]}"
            )
            
            # Log with structured logger
            self.structured_logger.log_application_result(
                job_title=job_data["title"],
                company=job_data["company"],
                status="failed",
                reason=f"Error: {str(e)}",
                metrics={
                    "iterations": iteration if 'iteration' in locals() else 0,
                    "actions_taken": actions_taken if 'actions_taken' in locals() else [],
                    "career_url": job_data["career_url"],
                    "failure_type": "exception",
                    "error_type": type(e).__name__,
                    **network_summary,  # Include network request data
                    **mcp_summary  # Include MCP metrics
                }
            )
            
            return {
                "status": "failed",
                "reason": f"Error: {str(e)}",
                "iterations": iteration if 'iteration' in locals() else 0,
                "actions_taken": actions_taken if 'actions_taken' in locals() else []
            }
        
        finally:
            # Clean up browser — check both existence AND non-None value
            if hasattr(self, 'page') and self.page is not None:
                try:
                    self.page.close()
                    self.page = None
                except Exception:
                    pass
            if hasattr(self, 'browser') and self.browser:
                try:
                    self.browser.close()
                    self.browser = None
                except Exception:
                    pass
            if hasattr(self, 'playwright') and self.playwright:
                try:
                    self.playwright.stop()
                    self.playwright = None
                except Exception:
                    pass
