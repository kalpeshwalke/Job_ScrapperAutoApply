"""
Unit tests for BrowserAgent.validate_tool_call() method

Tests Task 3.1 implementation:
- ALLOWED_TOOLS constant
- validate_tool_call() method
"""

import pytest
from unittest.mock import Mock
from src.ai_auto_apply.agents.browser_agent import BrowserAgent


class TestValidateToolCall:
    """Unit tests for validate_tool_call method"""
    
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
    
    def test_allowed_tools_constant_exists(self, browser_agent):
        """Test that ALLOWED_TOOLS constant is defined"""
        assert hasattr(browser_agent, 'ALLOWED_TOOLS')
        assert isinstance(browser_agent.ALLOWED_TOOLS, set)
        assert len(browser_agent.ALLOWED_TOOLS) == 6
    
    def test_allowed_tools_contains_correct_tools(self, browser_agent):
        """Test that ALLOWED_TOOLS contains the six valid tool names"""
        expected_tools = {
            'click_element',
            'enter_text',
            'select_option',
            'upload_file',
            'press_key',
            'navigate'
        }
        assert browser_agent.ALLOWED_TOOLS == expected_tools
    
    def test_validate_tool_call_with_valid_tool(self, browser_agent):
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
    
    def test_validate_tool_call_with_invalid_tool(self, browser_agent):
        """Test validate_tool_call returns (False, error_msg) for invalid tools"""
        invalid_tools = [
            'apply_for_job',
            'custom_search_engine',
            'generate_job_ad_template',
            'apply_job_description',
            'custom_interview_preparation_tool',
            'search_interview_questions'
        ]
        
        for tool_name in invalid_tools:
            tool_call = {"name": tool_name, "arguments": {}}
            is_valid, error_message = browser_agent.validate_tool_call(tool_call)
            
            assert is_valid is False, f"Expected {tool_name} to be invalid"
            assert error_message is not None, f"Expected error message for {tool_name}"
            assert tool_name in error_message, f"Expected error message to mention {tool_name}"
            assert "Invalid tool" in error_message, f"Expected 'Invalid tool' in error message"
            assert "Allowed tools:" in error_message, f"Expected 'Allowed tools:' in error message"
    
    def test_validate_tool_call_error_message_lists_all_valid_tools(self, browser_agent):
        """Test that error message lists all valid tools"""
        tool_call = {"name": "invalid_tool", "arguments": {}}
        is_valid, error_message = browser_agent.validate_tool_call(tool_call)
        
        assert is_valid is False
        assert error_message is not None
        
        # Check that all valid tools are mentioned in the error message
        for valid_tool in browser_agent.ALLOWED_TOOLS:
            assert valid_tool in error_message, \
                f"Expected error message to list valid tool '{valid_tool}'"
    
    def test_validate_tool_call_with_missing_name(self, browser_agent):
        """Test validate_tool_call handles missing 'name' key"""
        tool_call = {"arguments": {}}
        is_valid, error_message = browser_agent.validate_tool_call(tool_call)
        
        assert is_valid is False
        assert error_message is not None
        assert "Invalid tool" in error_message
    
    def test_validate_tool_call_with_empty_name(self, browser_agent):
        """Test validate_tool_call handles empty tool name"""
        tool_call = {"name": "", "arguments": {}}
        is_valid, error_message = browser_agent.validate_tool_call(tool_call)
        
        assert is_valid is False
        assert error_message is not None
        assert "Invalid tool" in error_message
