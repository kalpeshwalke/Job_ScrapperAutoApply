"""
Unit Test: Fail-Fast Termination After Repeated Hallucinations

This test verifies that the orchestrator terminates after 3 consecutive
hallucinations as specified in Task 3.6.

**Validates: Requirement 2.6**
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.ai_auto_apply.core.orchestrator import FSMOrchestrator


class TestOrchestratorFailFast:
    """Test fail-fast termination logic in orchestrator"""
    
    def test_fail_fast_after_three_consecutive_hallucinations(self):
        """
        Test that orchestrator terminates after 3 consecutive hallucinations.
        
        **Validates: Requirement 2.6**
        
        Scenario:
        1. Browser agent returns HALLUCINATION_ERROR 3 times in a row
        2. Orchestrator should terminate with specific error message
        3. Result should include hallucination_count = 3
        """
        # Setup: Create orchestrator with mocked dependencies
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "fsm": {
                "max_iterations": 20,
                "page_load_timeout": 30
            },
            "browser": {
                "headless": True,
                "page_load_wait_seconds": 1
            },
            "validation": {},
            "logging": {},
            "screenshots": {
                "enabled": False,
                "directory": "logs/screenshots",
                "retention_days": 30
            },
            "network_monitoring": {"enabled": False},
            "mcp": {"enabled": False}
        }
        
        mock_provider = Mock()
        excel_path = "test.xlsx"
        
        # Create orchestrator
        orchestrator = FSMOrchestrator(
            provider=mock_provider,
            config=config,
            excel_path=excel_path
        )
        
        # Mock the validator to pass validation
        orchestrator.validator.validate = Mock(return_value=("Yes", "Valid career page"))
        
        # Mock the tracker
        orchestrator.tracker.mark_failed = Mock()
        
        # Mock the structured logger
        orchestrator.structured_logger.log_application_result = Mock()
        
        # Mock Playwright browser
        with patch('src.ai_auto_apply.core.orchestrator.sync_playwright') as mock_playwright:
            mock_playwright_instance = MagicMock()
            mock_playwright.return_value.start.return_value = mock_playwright_instance
            
            mock_browser = MagicMock()
            mock_playwright_instance.chromium.launch.return_value = mock_browser
            
            mock_page = MagicMock()
            mock_browser.new_page.return_value = mock_page
            mock_page.url = "https://example.com/careers"
            mock_page.content.return_value = "<html><body>careers page</body></html>"
            
            # Mock DOM toolkit
            with patch('src.ai_auto_apply.core.orchestrator.DOMToolkit') as mock_dom_toolkit_class:
                mock_dom_toolkit = MagicMock()
                mock_dom_toolkit_class.return_value = mock_dom_toolkit
                
                # Mock DOM state
                mock_dom_toolkit.get_accessibility_snapshot.return_value = "mock ax tree"
                mock_dom_toolkit.get_dom_state.return_value = {
                    "elements": [{"mmid": "123", "tag": "button", "text": "Apply"}],
                    "ax_snapshot": "mock ax tree"
                }
                
                # Mock planner to return a step
                orchestrator.planner.plan_next_step = Mock(return_value={
                    "status": "in_progress",
                    "next_step": "Click the apply button",
                    "reasoning": "Need to click apply"
                })
                
                # Mock browser agent to return HALLUCINATION_ERROR 3 times
                hallucination_response = {
                    "success": False,
                    "error_type": "HALLUCINATION_ERROR",
                    "error": "Invalid tool 'apply_for_job'. Allowed tools: click_element, enter_text, select_option, upload_file, press_key, navigate",
                    "tool_name": "apply_for_job",
                    "action_summary": "Failed: hallucinated tool"
                }
                
                orchestrator.browser_agent.execute_step = Mock(return_value=hallucination_response)
                orchestrator.browser_agent.set_page = Mock()
                orchestrator.browser_agent.capture_screenshot = Mock()
                orchestrator.browser_agent.screenshot_each_iteration = False
                orchestrator.browser_agent.network_monitoring_enabled = False
                
                # Prepare job data
                job_data = {
                    "title": "Software Engineer",
                    "company": "Test Company",
                    "career_url": "https://example.com/careers",
                    "excel_index": 1
                }
                
                # Execute: Apply to job
                result = orchestrator.apply_to_job(job_data)
                
                # Assert: Should fail with hallucination error
                assert result["status"] == "failed", \
                    f"Expected status='failed', got: {result['status']}"
                
                assert "repeatedly hallucinating tool names" in result["reason"], \
                    f"Expected reason to mention repeated hallucinations, got: {result['reason']}"
                
                assert result["hallucination_count"] == 3, \
                    f"Expected hallucination_count=3, got: {result.get('hallucination_count')}"
                
                # Assert: Should terminate after 3 iterations (not continue to max_iterations)
                assert result["iterations"] == 3, \
                    f"Expected to terminate after 3 iterations, got: {result['iterations']}"
                
                # Assert: Browser agent should be called exactly 3 times
                assert orchestrator.browser_agent.execute_step.call_count == 3, \
                    f"Expected browser agent to be called 3 times, got: {orchestrator.browser_agent.execute_step.call_count}"
                
                # Assert: Tracker should mark as failed
                orchestrator.tracker.mark_failed.assert_called_once()
                
                # Assert: Structured logger should log the failure
                orchestrator.structured_logger.log_application_result.assert_called_once()
                log_call = orchestrator.structured_logger.log_application_result.call_args
                assert log_call[1]["status"] == "failed"
                assert log_call[1]["metrics"]["hallucination_count"] == 3
    
    def test_hallucination_count_resets_on_successful_execution(self):
        """
        Test that hallucination_count resets to 0 after a successful execution.
        
        **Validates: Requirement 2.6**
        
        Scenario:
        1. Browser agent returns HALLUCINATION_ERROR 2 times
        2. Browser agent returns success on 3rd attempt
        3. Browser agent returns HALLUCINATION_ERROR 2 more times
        4. Orchestrator should NOT terminate (count was reset)
        """
        # Setup: Create orchestrator with mocked dependencies
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "fsm": {
                "max_iterations": 20,
                "page_load_timeout": 30
            },
            "browser": {
                "headless": True,
                "page_load_wait_seconds": 1
            },
            "validation": {},
            "logging": {},
            "screenshots": {
                "enabled": False,
                "directory": "logs/screenshots",
                "retention_days": 30
            },
            "network_monitoring": {"enabled": False},
            "mcp": {"enabled": False}
        }
        
        mock_provider = Mock()
        excel_path = "test.xlsx"
        
        # Create orchestrator
        orchestrator = FSMOrchestrator(
            provider=mock_provider,
            config=config,
            excel_path=excel_path
        )
        
        # Mock the validator to pass validation
        orchestrator.validator.validate = Mock(return_value=("Yes", "Valid career page"))
        
        # Mock the tracker
        orchestrator.tracker.mark_applied = Mock()
        
        # Mock the structured logger
        orchestrator.structured_logger.log_application_result = Mock()
        
        # Mock Playwright browser
        with patch('src.ai_auto_apply.core.orchestrator.sync_playwright') as mock_playwright:
            mock_playwright_instance = MagicMock()
            mock_playwright.return_value.start.return_value = mock_playwright_instance
            
            mock_browser = MagicMock()
            mock_playwright_instance.chromium.launch.return_value = mock_browser
            
            mock_page = MagicMock()
            mock_browser.new_page.return_value = mock_page
            mock_page.url = "https://example.com/careers"
            mock_page.content.return_value = "<html><body>careers page</body></html>"
            
            # Mock DOM toolkit
            with patch('src.ai_auto_apply.core.orchestrator.DOMToolkit') as mock_dom_toolkit_class:
                mock_dom_toolkit = MagicMock()
                mock_dom_toolkit_class.return_value = mock_dom_toolkit
                
                # Mock DOM state
                mock_dom_toolkit.get_accessibility_snapshot.return_value = "mock ax tree"
                mock_dom_toolkit.get_dom_state.return_value = {
                    "elements": [{"mmid": "123", "tag": "button", "text": "Apply"}],
                    "ax_snapshot": "mock ax tree"
                }
                
                # Mock planner to return different responses
                planner_responses = [
                    {"status": "in_progress", "next_step": "Step 1", "reasoning": "Reason 1"},
                    {"status": "in_progress", "next_step": "Step 2", "reasoning": "Reason 2"},
                    {"status": "in_progress", "next_step": "Step 3", "reasoning": "Reason 3"},
                    {"status": "in_progress", "next_step": "Step 4", "reasoning": "Reason 4"},
                    {"status": "in_progress", "next_step": "Step 5", "reasoning": "Reason 5"},
                    {"status": "success", "reasoning": "Application completed"}
                ]
                orchestrator.planner.plan_next_step = Mock(side_effect=planner_responses)
                
                # Mock browser agent responses: 2 hallucinations, 1 success, 2 hallucinations, then success
                hallucination_response = {
                    "success": False,
                    "error_type": "HALLUCINATION_ERROR",
                    "error": "Invalid tool 'apply_for_job'",
                    "tool_name": "apply_for_job",
                    "action_summary": "Failed: hallucinated tool"
                }
                
                success_response = {
                    "success": True,
                    "action_summary": "Clicked button successfully"
                }
                
                browser_responses = [
                    hallucination_response,  # Iteration 1: hallucination (count = 1)
                    hallucination_response,  # Iteration 2: hallucination (count = 2)
                    success_response,        # Iteration 3: success (count resets to 0)
                    hallucination_response,  # Iteration 4: hallucination (count = 1)
                    hallucination_response,  # Iteration 5: hallucination (count = 2)
                ]
                
                orchestrator.browser_agent.execute_step = Mock(side_effect=browser_responses)
                orchestrator.browser_agent.set_page = Mock()
                orchestrator.browser_agent.capture_screenshot = Mock()
                orchestrator.browser_agent.screenshot_each_iteration = False
                orchestrator.browser_agent.network_monitoring_enabled = False
                
                # Prepare job data
                job_data = {
                    "title": "Software Engineer",
                    "company": "Test Company",
                    "career_url": "https://example.com/careers",
                    "excel_index": 1
                }
                
                # Execute: Apply to job
                result = orchestrator.apply_to_job(job_data)
                
                # Assert: Should succeed (planner returns success after 5 iterations)
                assert result["status"] == "success", \
                    f"Expected status='success', got: {result['status']}"
                
                # Assert: Should complete after 5 iterations (not terminate early)
                assert result["iterations"] == 6, \
                    f"Expected 6 iterations (5 browser + 1 planner success), got: {result['iterations']}"
                
                # Assert: Browser agent should be called 5 times (not terminated at 3)
                assert orchestrator.browser_agent.execute_step.call_count == 5, \
                    f"Expected browser agent to be called 5 times, got: {orchestrator.browser_agent.execute_step.call_count}"
    
    def test_fail_fast_logs_error_message(self):
        """
        Test that fail-fast logs the correct error message.
        
        **Validates: Requirement 2.6**
        """
        # Setup: Create orchestrator with mocked dependencies
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "fsm": {
                "max_iterations": 20,
                "page_load_timeout": 30
            },
            "browser": {
                "headless": True,
                "page_load_wait_seconds": 1
            },
            "validation": {},
            "logging": {},
            "screenshots": {
                "enabled": False,
                "directory": "logs/screenshots",
                "retention_days": 30
            },
            "network_monitoring": {"enabled": False},
            "mcp": {"enabled": False}
        }
        
        mock_provider = Mock()
        excel_path = "test.xlsx"
        
        # Create orchestrator
        orchestrator = FSMOrchestrator(
            provider=mock_provider,
            config=config,
            excel_path=excel_path
        )
        
        # Mock the validator to pass validation
        orchestrator.validator.validate = Mock(return_value=("Yes", "Valid career page"))
        
        # Mock the tracker
        orchestrator.tracker.mark_failed = Mock()
        
        # Mock the structured logger
        orchestrator.structured_logger.log_application_result = Mock()
        
        # Mock Playwright browser
        with patch('src.ai_auto_apply.core.orchestrator.sync_playwright') as mock_playwright:
            mock_playwright_instance = MagicMock()
            mock_playwright.return_value.start.return_value = mock_playwright_instance
            
            mock_browser = MagicMock()
            mock_playwright_instance.chromium.launch.return_value = mock_browser
            
            mock_page = MagicMock()
            mock_browser.new_page.return_value = mock_page
            mock_page.url = "https://example.com/careers"
            mock_page.content.return_value = "<html><body>careers page</body></html>"
            
            # Mock DOM toolkit
            with patch('src.ai_auto_apply.core.orchestrator.DOMToolkit') as mock_dom_toolkit_class:
                mock_dom_toolkit = MagicMock()
                mock_dom_toolkit_class.return_value = mock_dom_toolkit
                
                # Mock DOM state
                mock_dom_toolkit.get_accessibility_snapshot.return_value = "mock ax tree"
                mock_dom_toolkit.get_dom_state.return_value = {
                    "elements": [{"mmid": "123", "tag": "button", "text": "Apply"}],
                    "ax_snapshot": "mock ax tree"
                }
                
                # Mock planner
                orchestrator.planner.plan_next_step = Mock(return_value={
                    "status": "in_progress",
                    "next_step": "Click button",
                    "reasoning": "Need to click"
                })
                
                # Mock browser agent to return HALLUCINATION_ERROR
                hallucination_response = {
                    "success": False,
                    "error_type": "HALLUCINATION_ERROR",
                    "error": "Invalid tool 'apply_for_job'",
                    "tool_name": "apply_for_job",
                    "action_summary": "Failed: hallucinated tool"
                }
                
                orchestrator.browser_agent.execute_step = Mock(return_value=hallucination_response)
                orchestrator.browser_agent.set_page = Mock()
                orchestrator.browser_agent.capture_screenshot = Mock()
                orchestrator.browser_agent.screenshot_each_iteration = False
                orchestrator.browser_agent.network_monitoring_enabled = False
                
                # Prepare job data
                job_data = {
                    "title": "Software Engineer",
                    "company": "Test Company",
                    "career_url": "https://example.com/careers",
                    "excel_index": 1
                }
                
                # Execute with logger mock
                with patch('src.ai_auto_apply.core.orchestrator.logger') as mock_logger:
                    result = orchestrator.apply_to_job(job_data)
                    
                    # Assert: Logger should log the fail-fast error
                    mock_logger.error.assert_any_call(
                        "Fail-fast: 3 consecutive hallucinations detected. Terminating."
                    )
                    
                    # Assert: Logger should log warnings for each hallucination
                    assert mock_logger.warning.call_count >= 3, \
                        f"Expected at least 3 warning logs for hallucinations, got: {mock_logger.warning.call_count}"
