"""
Property-Based Test: Preservation - Valid Tool Execution Unchanged

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

These tests verify that valid tool execution remains unchanged after implementing
the hallucination fix.

EXPECTED OUTCOME ON UNFIXED CODE: These tests SHOULD PASS
- They capture the current behavior for valid tool calls
- They ensure the fix doesn't break existing functionality
- They should continue to pass after the fix is implemented

Property 2: Preservation - Valid Tool Execution Unchanged

Preservation Requirements:
- Valid tool calls (click_element, enter_text, select_option, upload_file, press_key, navigate) execute successfully
- DOM analysis and element detection remain unchanged
- Ollama API integration continues to work correctly
- MCP and legacy execution modes both continue to function
- Logging captures all tool calls correctly
- Error handling for recoverable errors remains unchanged
"""

import pytest
from hypothesis import given, strategies as st, settings, Phase
from unittest.mock import Mock, MagicMock, patch
import json
from typing import Dict, Any

# Import the BrowserAgent class
from src.ai_auto_apply.agents.browser_agent import BrowserAgent


# Define the valid tool names
VALID_TOOLS = [
    "click_element",
    "enter_text",
    "select_option",
    "upload_file",
    "press_key",
    "navigate"
]


@pytest.mark.property
class TestPreservationValidToolExecution:
    """
    Property 2: Preservation - Valid Tool Execution Unchanged
    
    These tests verify that valid tool calls continue to execute successfully
    after implementing the hallucination fix.
    
    EXPECTED OUTCOME: These tests SHOULD PASS on both unfixed and fixed code.
    """
    
    @settings(
        max_examples=20,
        phases=[Phase.generate, Phase.target],
        deadline=None
    )
    @given(
        valid_tool=st.sampled_from(VALID_TOOLS)
    )
    def test_valid_tools_execute_successfully(self, valid_tool: str):
        """
        Property: For all valid tool names in ALLOWED_TOOLS, execution succeeds.
        
        **Validates: Requirement 3.1**
        
        EXPECTED OUTCOME: PASS on unfixed code (baseline behavior)
        EXPECTED OUTCOME: PASS on fixed code (preservation confirmed)
        """
        # Setup: Create a BrowserAgent instance with mocked dependencies
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        
        # Prepare tool-specific arguments
        tool_arguments = self._get_valid_arguments_for_tool(valid_tool)
        
        # Mock the AI provider to return a valid tool call
        mock_provider = Mock()
        mock_response = Mock()
        mock_response.tool_calls = [
            {
                "name": valid_tool,
                "arguments": tool_arguments
            }
        ]
        mock_response.usage = {"total_tokens": 100}
        mock_provider.generate_browser_response.return_value = mock_response
        mock_provider.get_provider_name.return_value = "ollama"
        mock_provider.model = "qwen2.5:3b"
        
        # Create BrowserAgent with mocked provider
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Mock DOM toolkit with successful execution
        mock_dom_toolkit = Mock()
        mock_dom_toolkit.click_element = Mock()
        mock_dom_toolkit.enter_text = Mock()
        mock_dom_toolkit.select_option = Mock()
        mock_dom_toolkit.upload_file = Mock()
        mock_dom_toolkit.press_key = Mock()
        mock_dom_toolkit.navigate = Mock()
        
        # Prepare test inputs
        step = f"Execute {valid_tool}"
        dom_state = {"elements": [{"mmid": "123", "tag": "button", "text": "Submit"}]}
        job_data = {
            "title": "Software Engineer",
            "company": "Test Company",
            "user_details": {},
            "resume_path": "/path/to/resume.pdf"
        }
        
        # Execute: Call _execute_step_legacy with the valid tool
        result = agent._execute_step_legacy(
            step=step,
            dom_state=dom_state,
            dom_toolkit=mock_dom_toolkit,
            job_data=job_data
        )
        
        # Assert: Verify the valid tool executes successfully
        assert result["success"] is True, \
            f"Expected valid tool '{valid_tool}' to execute successfully, but got failure: {result}"
        
        # Assert: Verify no error_type is set (or it's not HALLUCINATION_ERROR)
        assert result.get("error_type") != "HALLUCINATION_ERROR", \
            f"Valid tool '{valid_tool}' should not be flagged as hallucination"
        
        # Assert: Verify the appropriate DOM toolkit method was called
        self._verify_dom_toolkit_called(valid_tool, tool_arguments, mock_dom_toolkit)
    
    def _get_valid_arguments_for_tool(self, tool_name: str) -> Dict[str, Any]:
        """Generate valid arguments for each tool type"""
        if tool_name == "click_element":
            return {"mmid": "123"}
        elif tool_name == "enter_text":
            return {"mmid": "123", "text": "test input"}
        elif tool_name == "select_option":
            return {"mmid": "123", "value": "option1"}
        elif tool_name == "upload_file":
            return {"mmid": "123", "file_path": "/path/to/file.pdf"}
        elif tool_name == "press_key":
            return {"key": "Enter"}
        elif tool_name == "navigate":
            return {"url": "https://example.com"}
        else:
            return {}
    
    def _verify_dom_toolkit_called(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any], 
        mock_dom_toolkit: Mock
    ):
        """Verify the correct DOM toolkit method was called"""
        if tool_name == "click_element":
            mock_dom_toolkit.click_element.assert_called_once_with(arguments["mmid"])
        elif tool_name == "enter_text":
            mock_dom_toolkit.enter_text.assert_called_once_with(
                arguments["mmid"], 
                arguments["text"]
            )
        elif tool_name == "select_option":
            mock_dom_toolkit.select_option.assert_called_once_with(
                arguments["mmid"], 
                arguments["value"]
            )
        elif tool_name == "upload_file":
            mock_dom_toolkit.upload_file.assert_called_once_with(
                arguments["mmid"], 
                arguments["file_path"]
            )
        elif tool_name == "press_key":
            mock_dom_toolkit.press_key.assert_called_once_with(arguments["key"])
        elif tool_name == "navigate":
            mock_dom_toolkit.navigate.assert_called_once_with(arguments["url"])
    
    def test_multiple_valid_tools_execute_in_sequence(self):
        """
        Test that multiple valid tool calls execute successfully in sequence.
        
        **Validates: Requirement 3.1**
        
        EXPECTED OUTCOME: PASS on unfixed code (baseline behavior)
        EXPECTED OUTCOME: PASS on fixed code (preservation confirmed)
        """
        # Setup
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        
        # Mock the AI provider to return multiple valid tool calls
        mock_provider = Mock()
        mock_response = Mock()
        mock_response.tool_calls = [
            {"name": "click_element", "arguments": {"mmid": "123"}},
            {"name": "enter_text", "arguments": {"mmid": "456", "text": "test"}},
            {"name": "press_key", "arguments": {"key": "Enter"}}
        ]
        mock_response.usage = {"total_tokens": 100}
        mock_provider.generate_browser_response.return_value = mock_response
        mock_provider.get_provider_name.return_value = "ollama"
        mock_provider.model = "qwen2.5:3b"
        
        # Create BrowserAgent
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Mock DOM toolkit
        mock_dom_toolkit = Mock()
        mock_dom_toolkit.click_element = Mock()
        mock_dom_toolkit.enter_text = Mock()
        mock_dom_toolkit.press_key = Mock()
        
        # Execute
        result = agent._execute_step_legacy(
            step="Fill and submit form",
            dom_state={"elements": []},
            dom_toolkit=mock_dom_toolkit,
            job_data={
                "title": "Software Engineer",
                "company": "Test Company",
                "user_details": {},
                "resume_path": "/path/to/resume.pdf"
            }
        )
        
        # Assert: All tools should execute successfully
        assert result["success"] is True, \
            "Expected all valid tools to execute successfully"
        
        # Assert: All DOM toolkit methods should be called
        mock_dom_toolkit.click_element.assert_called_once_with("123")
        mock_dom_toolkit.enter_text.assert_called_once_with("456", "test")
        mock_dom_toolkit.press_key.assert_called_once_with("Enter")
    
    def test_error_handling_for_dom_toolkit_failures_preserved(self):
        """
        Test that error handling for DOM toolkit failures remains unchanged.
        
        **Validates: Requirement 3.2**
        
        EXPECTED OUTCOME: PASS on unfixed code (baseline behavior)
        EXPECTED OUTCOME: PASS on fixed code (preservation confirmed)
        """
        # Setup
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        
        # Mock the AI provider
        mock_provider = Mock()
        mock_response = Mock()
        mock_response.tool_calls = [
            {"name": "click_element", "arguments": {"mmid": "123"}}
        ]
        mock_response.usage = {"total_tokens": 100}
        mock_provider.generate_browser_response.return_value = mock_response
        mock_provider.get_provider_name.return_value = "ollama"
        mock_provider.model = "qwen2.5:3b"
        
        # Create BrowserAgent
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Mock DOM toolkit to raise an exception (simulating element not found)
        mock_dom_toolkit = Mock()
        mock_dom_toolkit.click_element.side_effect = Exception("Element not found")
        
        # Execute
        result = agent._execute_step_legacy(
            step="Click button",
            dom_state={"elements": []},
            dom_toolkit=mock_dom_toolkit,
            job_data={
                "title": "Software Engineer",
                "company": "Test Company",
                "user_details": {},
                "resume_path": "/path/to/resume.pdf"
            }
        )
        
        # Assert: Execution should fail gracefully
        assert result["success"] is False, \
            "Expected execution to fail when DOM toolkit raises exception"
        
        # Assert: Error should be captured in results
        assert "results" in result, "Expected results to be present"
        assert len(result["results"]) > 0, "Expected at least one result"
        assert result["results"][0]["success"] is False, \
            "Expected tool result to indicate failure"
        
        # Assert: Should NOT be a HALLUCINATION_ERROR (it's a legitimate DOM error)
        assert result.get("error_type") != "HALLUCINATION_ERROR", \
            "DOM toolkit errors should not be classified as hallucination"
    
    def test_logging_captures_valid_tool_calls(self):
        """
        Test that logging continues to capture all valid tool calls correctly.
        
        **Validates: Requirement 3.5**
        
        EXPECTED OUTCOME: PASS on unfixed code (baseline behavior)
        EXPECTED OUTCOME: PASS on fixed code (preservation confirmed)
        """
        # Setup with logging enabled
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "logging": {"log_dom_interactions": True},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        
        # Mock the AI provider
        mock_provider = Mock()
        mock_response = Mock()
        mock_response.tool_calls = [
            {"name": "click_element", "arguments": {"mmid": "123"}}
        ]
        mock_response.usage = {"total_tokens": 100}
        mock_provider.generate_browser_response.return_value = mock_response
        mock_provider.get_provider_name.return_value = "ollama"
        mock_provider.model = "qwen2.5:3b"
        
        # Create BrowserAgent
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Mock DOM toolkit
        mock_dom_toolkit = Mock()
        mock_dom_toolkit.click_element = Mock()
        
        # Execute
        with patch('src.ai_auto_apply.agents.browser_agent.logger') as mock_logger:
            result = agent._execute_step_legacy(
                step="Click button",
                dom_state={"elements": [{"mmid": "123", "tag": "button", "text": "Submit"}]},
                dom_toolkit=mock_dom_toolkit,
                job_data={
                    "title": "Software Engineer",
                    "company": "Test Company",
                    "user_details": {},
                    "resume_path": "/path/to/resume.pdf"
                }
            )
            
            # Assert: Execution should succeed
            assert result["success"] is True
            
            # Assert: Logger should be called (logging is preserved)
            # We don't check exact log messages as they may vary,
            # but we verify logging functionality is still active
            assert mock_logger.info.called or mock_logger.debug.called, \
                "Expected logging to be active for valid tool calls"
    
    def test_ai_provider_integration_preserved(self):
        """
        Test that AI provider integration (Ollama) continues to work correctly.
        
        **Validates: Requirement 3.4**
        
        EXPECTED OUTCOME: PASS on unfixed code (baseline behavior)
        EXPECTED OUTCOME: PASS on fixed code (preservation confirmed)
        """
        # Setup
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        
        # Mock the AI provider
        mock_provider = Mock()
        mock_response = Mock()
        mock_response.tool_calls = [
            {"name": "navigate", "arguments": {"url": "https://example.com"}}
        ]
        mock_response.usage = {"total_tokens": 150}
        mock_provider.generate_browser_response.return_value = mock_response
        mock_provider.get_provider_name.return_value = "ollama"
        mock_provider.model = "qwen2.5:3b"
        
        # Create BrowserAgent
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Mock DOM toolkit
        mock_dom_toolkit = Mock()
        mock_dom_toolkit.navigate = Mock()
        
        # Execute
        result = agent._execute_step_legacy(
            step="Navigate to careers page",
            dom_state={"elements": []},
            dom_toolkit=mock_dom_toolkit,
            job_data={
                "title": "Software Engineer",
                "company": "Test Company",
                "user_details": {},
                "resume_path": "/path/to/resume.pdf"
            }
        )
        
        # Assert: Execution should succeed
        assert result["success"] is True
        
        # Assert: AI provider should be called with correct parameters
        mock_provider.generate_browser_response.assert_called_once()
        call_kwargs = mock_provider.generate_browser_response.call_args[1]
        
        # Verify tools are passed to AI provider
        assert "tools" in call_kwargs, "Expected tools to be passed to AI provider"
        assert len(call_kwargs["tools"]) == 6, \
            "Expected all 6 valid tools to be passed to AI provider"
        
        # Verify context is passed
        assert "context" in call_kwargs, "Expected context to be passed to AI provider"
    
    def test_tool_definitions_structure_preserved(self):
        """
        Test that _get_tool_definitions() returns the correct structure.
        
        **Validates: Requirement 3.1**
        
        EXPECTED OUTCOME: PASS on unfixed code (baseline behavior)
        EXPECTED OUTCOME: PASS on fixed code (preservation confirmed)
        """
        # Setup
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        
        mock_provider = Mock()
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Get tool definitions
        tools = agent._get_tool_definitions()
        
        # Assert: Should have exactly 6 tools
        assert len(tools) == 6, f"Expected 6 tools, got {len(tools)}"
        
        # Assert: Each tool should have the correct structure
        for tool in tools:
            assert "type" in tool, "Tool should have 'type' field"
            assert tool["type"] == "function", "Tool type should be 'function'"
            assert "function" in tool, "Tool should have 'function' field"
            assert "name" in tool["function"], "Function should have 'name' field"
            assert "description" in tool["function"], "Function should have 'description' field"
            assert "parameters" in tool["function"], "Function should have 'parameters' field"
        
        # Assert: All valid tool names are present
        tool_names = [tool["function"]["name"] for tool in tools]
        for valid_tool in VALID_TOOLS:
            assert valid_tool in tool_names, \
                f"Expected tool '{valid_tool}' to be in tool definitions"
    
    def test_no_tool_calls_handling_preserved(self):
        """
        Test that handling of "no tool calls" response remains unchanged.
        
        **Validates: Requirement 3.1**
        
        EXPECTED OUTCOME: PASS on unfixed code (baseline behavior)
        EXPECTED OUTCOME: PASS on fixed code (preservation confirmed)
        """
        # Setup
        config = {
            "ai_provider": "ollama",
            "ollama_model": "qwen2.5:3b",
            "ollama_base_url": "http://localhost:11434",
            "logging": {"log_dom_interactions": False},
            "retry": {},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": False}
        }
        
        # Mock the AI provider to return no tool calls
        mock_provider = Mock()
        mock_response = Mock()
        mock_response.tool_calls = []  # Empty list
        mock_response.usage = {"total_tokens": 50}
        mock_provider.generate_browser_response.return_value = mock_response
        mock_provider.get_provider_name.return_value = "ollama"
        mock_provider.model = "qwen2.5:3b"
        
        # Create BrowserAgent
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Mock DOM toolkit
        mock_dom_toolkit = Mock()
        
        # Execute
        result = agent._execute_step_legacy(
            step="Do something",
            dom_state={"elements": []},
            dom_toolkit=mock_dom_toolkit,
            job_data={
                "title": "Software Engineer",
                "company": "Test Company",
                "user_details": {},
                "resume_path": "/path/to/resume.pdf"
            }
        )
        
        # Assert: Should fail with appropriate message
        assert result["success"] is False, \
            "Expected failure when no tool calls are returned"
        
        assert "No tool calls returned" in result.get("error", ""), \
            "Expected error message about no tool calls"
        
        # Assert: Should NOT be a HALLUCINATION_ERROR
        assert result.get("error_type") != "HALLUCINATION_ERROR", \
            "No tool calls should not be classified as hallucination"
