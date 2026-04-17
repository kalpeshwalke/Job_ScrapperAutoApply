"""
FSM Orchestrator

Finite State Machine orchestrator for AI auto-apply workflow.
"""

import os
from typing import Dict, Any
from src.common.logger import get_logger
from src.ai_auto_apply.agents.planner_agent import PlannerAgent
from src.ai_auto_apply.agents.browser_agent import BrowserAgent
from src.ai_auto_apply.tools.dom_tools import DOMToolkit
from src.ai_auto_apply.core.anti_spam_tracker import AntiSpamTracker
from src.ai_auto_apply.core.structured_logger import StructuredLogger
from src.ai_auto_apply.core.career_page_validator import CareerPageValidator
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
        
        # Initialize agents
        self.planner = PlannerAgent(provider, config)
        self.browser_agent = BrowserAgent(provider, config)
        
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
            
            # STEP 2: Handle homepage redirect - navigate to careers page
            if is_homepage_redirect:
                logger.info("Homepage redirect detected, attempting to navigate to careers page")
                
                # Instantiate HomepageNavigator
                homepage_navigator = HomepageNavigator(self.page, self.config)
                
                # Track navigation attempts (max 3)
                max_homepage_attempts = 3
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
            
            # Inject mmid attributes
            dom_toolkit.inject_mmids()
            
            # FSM loop
            while iteration < self.max_iterations:
                iteration += 1
                logger.debug("FSM iteration %d/%d", iteration, self.max_iterations)
                
                # Get current DOM state
                dom_state = dom_toolkit.get_dom_state()
                
                # Get current DOM state
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
                            **network_summary  # Include network request data
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
                            **network_summary  # Include network request data
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
                    **network_summary  # Include network request data
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
                    **network_summary  # Include network request data
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
