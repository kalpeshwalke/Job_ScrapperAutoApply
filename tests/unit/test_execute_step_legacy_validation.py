"""
Unit tests for _execute_step_legacy() tool validation (Task 3.2)

Tests that _execute_step_legacy() validates tool names before execution
and returns HALLUCINATION_ERROR for invalid tools.
"""

import pytest
from unittest.mock import Mock, MagicMock
from src.ai_auto_apply.agents.browser_agent import BrowserAgent


class TestExecuteStepLegacyValidation:
    """Test suite for _execute_step_legacy() tool name validation"""
    
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
    
    def test_execute_step_legacy_rejects_hallucinated_tool(self, browser_agent):
        """Test that _execute_step_legacy rejects hallucinated tool names"""
        # Mock the provider to return a hallucinated tool call
        mock_response = Mock()
        mock_response.tool_calls = [
            {"name": "apply_for_job", "arguments": {"job_id": "12345"}}
        ]
        mock_response.usage = None
        browser_agent.provider.generate_browser_response = Mock(return_value=mock_response)
        
        # Mock DOM toolkit
        mock_dom_toolkit = Mock()
        
        # Execute step
        result = browser_agent._execute_step_legacy(
            step="Apply for the job",
            dom_state={"elements": []},
            dom_toolkit=mock_dom_toolkit,
            job_data={"title": "Software Engineer", "company": "Test Corp"}
        )
        
        # Verify rejection
        assert result["success"] is False, "Expected success=False for hallucinated tool"
        assert result["error_type"] == "HALLUCINATION_ERROR", "Expected HALLUCINATION_ERROR error type"
        assert "Invalid tool 'apply_for_job'" in result["error"], "Expected error message about invalid tool"
        assert "Allowed tools:" in result["error"], "Expected error message to list allowed tools"
        assert result["tool_name"] == "apply_for_job", "Expected tool_name in result"
    
    def test_execute_step_legacy_accepts_valid_tool(self, browser_agent):
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
        assert "error_type" not in result or result["error_type"] != "HALLUCINATION_ERROR", \
            "Should not have HALLUCINATION_ERROR for valid tool"
        assert mock_dom_toolkit.click_element.called, "Expected tool to be executed"
    
    def test_execute_step_legacy_rejects_multiple_hallucinated_tools(self, browser_agent):
        """Test rejection of various hallucinated tool names"""
        hallucinated_tools = [
            "apply_for_job",
            "custom_search_engine",
            "generate_job_ad_template",
            "search_interview_questions",
            "autofill_form"
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
            assert f"Invalid tool '{tool_name}'" in result["error"], \
                f"Expected error message about {tool_name}"
    
    def test_execute_step_legacy_handles_nested_function_format(self, browser_agent):
        """Test that validation works with nested function format"""
        # Mock the provider to return a hallucinated tool in nested format
        mock_response = Mock()
        mock_response.tool_calls = [
            {
                "function": {
                    "name": "custom_search_engine",
                    "arguments": '{"query": "Software Engineer"}'
                }
            }
        ]
        mock_response.usage = None
        browser_agent.provider.generate_browser_response = Mock(return_value=mock_response)
        
        # Mock DOM toolkit
        mock_dom_toolkit = Mock()
        
        # Execute step
        result = browser_agent._execute_step_legacy(
            step="Search for jobs",
            dom_state={"elements": []},
            dom_toolkit=mock_dom_toolkit,
            job_data={"title": "Software Engineer", "company": "Test Corp"}
        )
        
        # Verify rejection
        assert result["success"] is False, "Expected rejection for nested format hallucination"
        assert result["error_type"] == "HALLUCINATION_ERROR", "Expected HALLUCINATION_ERROR"
        assert "Invalid tool 'custom_search_engine'" in result["error"], \
            "Expected error message about invalid tool"
