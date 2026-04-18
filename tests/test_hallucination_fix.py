"""
Comprehensive Unit Tests for AI Tool Hallucination Fix

This test file provides comprehensive coverage for Task 3.8, ensuring all
aspects of the hallucination fix are properly tested.

**Validates: Requirements 2.2, 2.3, 2.5, 2.6**

Test Coverage:
1. validate_tool_call() with valid/invalid tool names
2. _execute_step_legacy() with hallucinated/valid tool names
3. SYSTEM_PROMPT includes tool list and warnings
4. SYSTEM_PROMPT_BASE includes Browser Agent tools summary
5. Correction messages are injected into AI context after hallucinations
6. Fail-fast logic terminates after 3 consecutive hallucinations

Note: Some tests may overlap with existing test files (test_validate_tool_call.py,
test_execute_step_legacy_validation.py, test_orchestrator_fail_fast.py) but are
included here for comprehensive coverage as requested in Task 3.8.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.ai_auto_apply.agents.browser_agent import BrowserAgent
from src.ai_auto_apply.agents.planner_agent import PlannerAgent
from src.ai_auto_apply.core.orchestrator import FSMOrchestrator


class TestValidateToolCall:
    """Test validate_tool_call() method - Requirements 2.2, 2.3"""
    
    @pytest.fixture
    def browser_agent(self):
        """Create a BrowserAgent instance for testing"""
        config = {
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        mock_provider = Mock()
        return BrowserAgent(provider=mock_provider, config=config)
    
    def test_validate_tool_call_with_valid_tools(self, browser_agent):
        """Test validate_tool_call returns (True, None) for valid tools"""
        valid_tools = [
            'click_element',
            'enter_text',
            'select_option',
            'upload_file',
            'press_key',
            'navigate'
        ]
        
        for tool_name in valid_tools:
            tool_call = {"name": tool_name, "arguments": {}}
            is_valid, error_message = browser_agent.validate_tool_call(tool_call)
            
            assert is_valid is True, f"Expected {tool_name} to be valid"
            assert error_message is None, f"Expected no error message for {tool_name}"
    
    def test_validate_tool_call_with_invalid_tools(self, browser_agent):
        """Test validate_tool_call returns (False, error_message) for invalid tools"""
        invalid_tools = [
            'apply_for_job',
            'custom_search_engine',
            'generate_job_ad_template',
            'apply_job_description',
            'custom_interview_preparation_tool',
            'search_interview_questions',
            'autofill_form',
            'search_jobs'
        ]
        
        for tool_name in invalid_tools:
            tool_call = {"name": tool_name, "arguments": {}}
            is_valid, error_message = browser_agent.validate_tool_call(tool_call)
            
            assert is_valid is False, f"Expected {tool_name} to be invalid"
            assert error_message is not None, f"Expected error message for {tool_name}"
            assert tool_name in error_message, f"Expected error message to mention {tool_name}"
            assert "Invalid tool" in error_message
            assert "Allowed tools:" in error_message
            
            # Verify all valid tools are listed in error message
            for valid_tool in browser_agent.ALLOWED_TOOLS:
                assert valid_tool in error_message, \
                    f"Expected error message to list valid tool '{valid_tool}'"


class TestExecuteStepLegacyValidation:
    """Test _execute_step_legacy() validation - Requirements 2.2, 2.3"""
    
    @pytest.fixture
    def browser_agent(self):
        """Create a BrowserAgent instance for testing"""
        config = {
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        mock_provider = Mock()
        return BrowserAgent(provider=mock_provider, config=config)
    
    def test_execute_step_legacy_rejects_hallucinated_tools(self, browser_agent):
        """Test that _execute_step_legacy rejects hallucinated tool names"""
        hallucinated_tools = [
            "apply_for_job",
            "custom_search_engine",
            "generate_job_ad_template"
        ]
        
        for tool_name in hallucinated_tools:
            # Mock the provider to return a hallucinated tool call
            mock_response = Mock()
            mock_response.tool_calls = [
                {"name": tool_name, "arguments": {}}
            ]
            mock_response.usage = None
            browser_agent.provider.generate_browser_response = Mock(return_value=mock_response)
            
            # Mock DOM toolkit
            mock_dom_toolkit = Mock()
            
            # Execute step
            result = browser_agent._execute_step_legacy(
                step=f"Use {tool_name}",
                dom_state={"elements": []},
                dom_toolkit=mock_dom_toolkit,
                job_data={"title": "Software Engineer", "company": "Test Corp"}
            )
            
            # Verify rejection
            assert result["success"] is False, f"Expected rejection for {tool_name}"
            assert result["error_type"] == "HALLUCINATION_ERROR", \
                f"Expected HALLUCINATION_ERROR for {tool_name}"
            assert f"Invalid tool '{tool_name}'" in result["error"]
            assert "Allowed tools:" in result["error"]
            assert result["tool_name"] == tool_name
    
    def test_execute_step_legacy_accepts_valid_tools(self, browser_agent):
        """Test that _execute_step_legacy accepts valid tool names"""
        # Mock the provider to return a valid tool call
        mock_response = Mock()
        mock_response.tool_calls = [
            {"name": "click_element", "arguments": {"mmid": "123"}}
        ]
        mock_response.usage = None
        browser_agent.provider.generate_browser_response = Mock(return_value=mock_response)
        
        # Mock DOM toolkit to return success
        mock_dom_toolkit = Mock()
        mock_dom_toolkit.click_element = Mock(return_value={"success": True, "action": "Clicked element"})
        
        # Execute step
        result = browser_agent._execute_step_legacy(
            step="Click the submit button",
            dom_state={"elements": [{"mmid": "123", "tag": "button", "text": "Submit"}]},
            dom_toolkit=mock_dom_toolkit,
            job_data={"title": "Software Engineer", "company": "Test Corp"}
        )
        
        # Verify acceptance and execution
        assert result["success"] is True, "Expected success=True for valid tool"
        assert "error_type" not in result or result["error_type"] != "HALLUCINATION_ERROR"
        assert mock_dom_toolkit.click_element.called


class TestSystemPromptContent:
    """Test SYSTEM_PROMPT includes tool list and warnings - Requirement 2.5"""
    
    def test_browser_agent_system_prompt_includes_tool_list(self):
        """Test that BrowserAgent SYSTEM_PROMPT explicitly lists all 6 tools"""
        prompt = BrowserAgent.SYSTEM_PROMPT
        
        # Verify prompt includes "AVAILABLE TOOLS" section
        assert "AVAILABLE TOOLS" in prompt, \
            "SYSTEM_PROMPT should have 'AVAILABLE TOOLS' section"
        
        # Verify all 6 tools are listed
        required_tools = [
            "click_element",
            "enter_text",
            "select_option",
            "upload_file",
            "press_key",
            "navigate"
        ]
        
        for tool in required_tools:
            assert tool in prompt, \
                f"SYSTEM_PROMPT should list tool '{tool}'"
    
    def test_browser_agent_system_prompt_includes_critical_rules(self):
        """Test that BrowserAgent SYSTEM_PROMPT includes critical rules against hallucination"""
        prompt = BrowserAgent.SYSTEM_PROMPT
        
        # Verify prompt includes "CRITICAL RULES" section
        assert "CRITICAL RULES" in prompt, \
            "SYSTEM_PROMPT should have 'CRITICAL RULES' section"
        
        # Verify specific warnings are present
        assert "NEVER invent tool names" in prompt, \
            "SYSTEM_PROMPT should warn against inventing tool names"
        
        assert "Only use the 6 tools listed above" in prompt, \
            "SYSTEM_PROMPT should emphasize using only listed tools"
        
        assert "Do NOT create tools like" in prompt, \
            "SYSTEM_PROMPT should provide examples of invalid tools"
    
    def test_browser_agent_system_prompt_mentions_hallucinated_examples(self):
        """Test that SYSTEM_PROMPT mentions specific hallucinated tool examples"""
        prompt = BrowserAgent.SYSTEM_PROMPT
        
        # Verify prompt mentions common hallucinated tools as examples
        hallucinated_examples = [
            "apply_for_job",
            "search_jobs",
            "custom_search_engine"
        ]
        
        # At least some of these should be mentioned as examples of what NOT to do
        mentions_count = sum(1 for tool in hallucinated_examples if tool in prompt)
        assert mentions_count >= 2, \
            "SYSTEM_PROMPT should mention at least 2 hallucinated tool examples"


class TestPlannerSystemPromptContent:
    """Test SYSTEM_PROMPT_BASE includes Browser Agent tools - Requirement 2.5"""
    
    def test_planner_system_prompt_includes_browser_tools_section(self):
        """Test that PlannerAgent SYSTEM_PROMPT_BASE includes Browser Agent tools summary"""
        prompt = PlannerAgent.SYSTEM_PROMPT_BASE
        
        # Verify prompt includes "BROWSER AGENT TOOLS AVAILABLE" section
        assert "BROWSER AGENT TOOLS AVAILABLE" in prompt, \
            "SYSTEM_PROMPT_BASE should have 'BROWSER AGENT TOOLS AVAILABLE' section"
        
        # Verify all 6 Browser Agent tools are mentioned
        required_tools = [
            "click_element",
            "enter_text",
            "select_option",
            "upload_file",
            "press_key",
            "navigate"
        ]
        
        for tool in required_tools:
            assert tool in prompt, \
                f"SYSTEM_PROMPT_BASE should mention Browser Agent tool '{tool}'"
    
    def test_planner_system_prompt_includes_hallucination_warning(self):
        """Test that PlannerAgent SYSTEM_PROMPT_BASE includes hallucination warning"""
        prompt = PlannerAgent.SYSTEM_PROMPT_BASE
        
        # Verify prompt includes "HALLUCINATION WARNING" section
        assert "HALLUCINATION WARNING" in prompt, \
            "SYSTEM_PROMPT_BASE should have 'HALLUCINATION WARNING' section"
        
        # Verify specific warnings are present
        assert "Do NOT invent tool names" in prompt, \
            "SYSTEM_PROMPT_BASE should warn against inventing tool names"
        
        assert "Only reference the 6 Browser Agent tools" in prompt, \
            "SYSTEM_PROMPT_BASE should emphasize using only Browser Agent tools"
    
    def test_planner_system_prompt_mentions_invalid_tool_examples(self):
        """Test that SYSTEM_PROMPT_BASE mentions examples of invalid tools"""
        prompt = PlannerAgent.SYSTEM_PROMPT_BASE
        
        # Verify prompt mentions common hallucinated tools as examples
        invalid_examples = [
            "apply_for_job",
            "search_jobs",
            "autofill_form"
        ]
        
        # At least some of these should be mentioned as examples of what NOT to assume
        mentions_count = sum(1 for tool in invalid_examples if tool in prompt)
        assert mentions_count >= 2, \
            "SYSTEM_PROMPT_BASE should mention at least 2 invalid tool examples"


class TestOrchestratorCorrectionMessages:
    """Test correction messages are injected into AI context - Requirement 2.3"""
    
    def test_correction_message_injected_after_hallucination(self):
        """Test that orchestrator injects correction message after hallucination"""
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
        
        # Mock the validator
        orchestrator.validator.validate = Mock(return_value=("Yes", "Valid career page"))
        orchestrator.tracker.mark_failed = Mock()
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
                
                mock_dom_toolkit.get_accessibility_snapshot.return_value = "mock ax tree"
                mock_dom_toolkit.get_dom_state.return_value = {
                    "elements": [{"mmid": "123", "tag": "button", "text": "Apply"}],
                    "ax_snapshot": "mock ax tree"
                }
                
                # Mock planner to return steps
                planner_responses = [
                    {"status": "in_progress", "next_step": "Step 1", "reasoning": "Reason 1"},
                    {"status": "success", "reasoning": "Application completed"}
                ]
                orchestrator.planner.plan_next_step = Mock(side_effect=planner_responses)
                
                # Mock browser agent to return HALLUCINATION_ERROR once, then success
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
                
                # Assert: Correction message should be stored in planner
                assert hasattr(orchestrator.planner, 'correction_messages'), \
                    "Planner should have correction_messages attribute after hallucination"
                
                assert len(orchestrator.planner.correction_messages) > 0, \
                    "Planner should have at least one correction message"
                
                correction_msg = orchestrator.planner.correction_messages[0]
                
                # Verify correction message content
                assert "ERROR" in correction_msg, \
                    "Correction message should start with ERROR"
                
                assert "invalid tool name" in correction_msg, \
                    "Correction message should mention invalid tool name"
                
                assert "apply_for_job" in correction_msg, \
                    "Correction message should mention the hallucinated tool"
                
                assert "Valid tools are:" in correction_msg, \
                    "Correction message should list valid tools"
                
                # Verify all valid tools are listed
                valid_tools = ["click_element", "enter_text", "select_option", 
                              "upload_file", "press_key", "navigate"]
                for tool in valid_tools:
                    assert tool in correction_msg, \
                        f"Correction message should list valid tool '{tool}'"


class TestOrchestratorFailFast:
    """Test fail-fast logic terminates after 3 consecutive hallucinations - Requirement 2.6"""
    
    def test_fail_fast_after_three_consecutive_hallucinations(self):
        """Test that orchestrator terminates after 3 consecutive hallucinations"""
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
        
        # Mock the validator
        orchestrator.validator.validate = Mock(return_value=("Yes", "Valid career page"))
        orchestrator.tracker.mark_failed = Mock()
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
                
                mock_dom_toolkit.get_accessibility_snapshot.return_value = "mock ax tree"
                mock_dom_toolkit.get_dom_state.return_value = {
                    "elements": [{"mmid": "123", "tag": "button", "text": "Apply"}],
                    "ax_snapshot": "mock ax tree"
                }
                
                # Mock planner to return steps
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
                    f"Expected reason to mention repeated hallucinations"
                
                assert result["hallucination_count"] == 3, \
                    f"Expected hallucination_count=3, got: {result.get('hallucination_count')}"
                
                # Assert: Should terminate after 3 iterations
                assert result["iterations"] == 3, \
                    f"Expected to terminate after 3 iterations, got: {result['iterations']}"
                
                # Assert: Browser agent should be called exactly 3 times
                assert orchestrator.browser_agent.execute_step.call_count == 3, \
                    f"Expected browser agent to be called 3 times"


class TestIntegrationHallucinationFix:
    """Integration tests for complete hallucination fix workflow"""
    
    def test_end_to_end_hallucination_detection_and_recovery(self):
        """Test complete workflow: hallucination detected, corrected, then success"""
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
        
        # Mock the validator
        orchestrator.validator.validate = Mock(return_value=("Yes", "Valid career page"))
        orchestrator.tracker.mark_applied = Mock()
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
                
                mock_dom_toolkit.get_accessibility_snapshot.return_value = "mock ax tree"
                mock_dom_toolkit.get_dom_state.return_value = {
                    "elements": [{"mmid": "123", "tag": "button", "text": "Apply"}],
                    "ax_snapshot": "mock ax tree"
                }
                
                # Mock planner to return steps
                planner_responses = [
                    {"status": "in_progress", "next_step": "Step 1", "reasoning": "Reason 1"},
                    {"status": "in_progress", "next_step": "Step 2", "reasoning": "Reason 2"},
                    {"status": "success", "reasoning": "Application completed"}
                ]
                orchestrator.planner.plan_next_step = Mock(side_effect=planner_responses)
                
                # Mock browser agent: hallucination, then success
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
                    hallucination_response,  # First attempt: hallucination
                    success_response         # Second attempt: success (after correction)
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
                
                # Assert: Should succeed after correction
                assert result["status"] == "success", \
                    f"Expected status='success' after correction, got: {result['status']}"
                
                # Assert: Correction message was created
                assert hasattr(orchestrator.planner, 'correction_messages'), \
                    "Planner should have correction_messages after hallucination"
                
                assert len(orchestrator.planner.correction_messages) > 0, \
                    "Planner should have correction message"
                
                # Assert: Browser agent was called twice (hallucination + success)
                assert orchestrator.browser_agent.execute_step.call_count == 2, \
                    f"Expected browser agent to be called 2 times"
