"""
Property-Based Test: Bug Condition - AI Tool Hallucination Detection

**Validates: Requirements 2.2, 2.3**

This test encodes the EXPECTED behavior for tool hallucination detection.
When run on UNFIXED code, this test MUST FAIL - failure confirms the bug exists.
When run on FIXED code, this test MUST PASS - success confirms the bug is fixed.

The test verifies that:
1. Hallucinated tool names are rejected with HALLUCINATION_ERROR
2. Error messages include the list of valid tools
3. System does not attempt to execute hallucinated tools
"""

import pytest
from hypothesis import given, strategies as st, settings, Phase
from unittest.mock import Mock, MagicMock, patch
import json
from typing import Dict, Any

# Import the BrowserAgent class
from src.ai_auto_apply.agents.browser_agent import BrowserAgent


# Define the known hallucinated tool names from the bug report
HALLUCINATED_TOOLS = [
    "apply_for_job",
    "custom_search_engine", 
    "generate_job_ad_template",
    "apply_job_description",
    "custom_interview_preparation_tool",
    "search_interview_questions"
]

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
class TestBugConditionHallucinationDetection:
    """
    Property 1: Bug Condition - AI Tool Hallucination Detection
    
    CRITICAL: This test MUST FAIL on unfixed code - failure confirms the bug exists.
    """
    
    @settings(
        max_examples=10,
        phases=[Phase.generate, Phase.target],
        deadline=None
    )
    @given(
        hallucinated_tool=st.sampled_from(HALLUCINATED_TOOLS),
        arguments=st.fixed_dictionaries({})
    )
    def test_hallucinated_tools_rejected_with_error(
        self, 
        hallucinated_tool: str,
        arguments: Dict[str, Any]
    ):
        """
        Property: For all hallucinated tool names, the system SHALL reject them 
        with HALLUCINATION_ERROR and provide a correction message listing valid tools.
        
        **Validates: Requirements 2.2, 2.3**
        
        EXPECTED OUTCOME ON UNFIXED CODE: FAIL (proves bug exists)
        EXPECTED OUTCOME ON FIXED CODE: PASS (proves bug is fixed)
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
        
        # Mock the AI provider to return a hallucinated tool call
        mock_provider = Mock()
        mock_response = Mock()
        mock_response.tool_calls = [
            {
                "name": hallucinated_tool,
                "arguments": arguments
            }
        ]
        mock_response.usage = {"total_tokens": 100}
        mock_provider.generate_browser_response.return_value = mock_response
        mock_provider.get_provider_name.return_value = "ollama"
        mock_provider.model = "qwen2.5:3b"
        
        # Create BrowserAgent with mocked provider
        agent = BrowserAgent(provider=mock_provider, config=config)
        
        # Mock DOM toolkit
        mock_dom_toolkit = Mock()
        
        # Prepare test inputs
        step = "Apply for the job"
        dom_state = {"elements": []}
        job_data = {
            "title": "Software Engineer",
            "company": "Test Company",
            "user_details": {},
            "resume_path": "/path/to/resume.pdf"
        }
        
        # Execute: Call _execute_step_legacy with the hallucinated tool
        result = agent._execute_step_legacy(
            step=step,
            dom_state=dom_state,
            dom_toolkit=mock_dom_toolkit,
            job_data=job_data
        )
        
        # Assert: Verify the system rejects the hallucinated tool
        assert result["success"] is False, \
            f"Expected hallucinated tool '{hallucinated_tool}' to be rejected, but execution succeeded"
        
        assert result.get("error_type") == "HALLUCINATION_ERROR", \
            f"Expected error_type='HALLUCINATION_ERROR' for tool '{hallucinated_tool}', got: {result.get('error_type')}"
        
        # Assert: Verify error message includes the hallucinated tool name
        error_message = result.get("error", "")
        assert hallucinated_tool in error_message, \
            f"Expected error message to mention hallucinated tool '{hallucinated_tool}', got: {error_message}"
        
        # Assert: Verify error message includes list of valid tools
        for valid_tool in VALID_TOOLS:
            assert valid_tool in error_message, \
                f"Expected error message to list valid tool '{valid_tool}', got: {error_message}"
    
    
    @pytest.mark.property
    def test_specific_hallucinated_tools_from_bug_report(self):
        """
        Test the specific hallucinated tools mentioned in the bug report.
        
        This is a concrete test case that verifies the exact tools that caused
        the bug in production.
        
        **Validates: Requirements 2.2, 2.3**
        
        EXPECTED OUTCOME ON UNFIXED CODE: FAIL (proves bug exists)
        EXPECTED OUTCOME ON FIXED CODE: PASS (proves bug is fixed)
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
        
        test_cases = [
            ("apply_for_job", {"job_id": "12345"}),
            ("custom_search_engine", {"query": "Software Engineer"}),
            ("generate_job_ad_template", {}),
            ("apply_job_description", {}),
            ("custom_interview_preparation_tool", {}),
            ("search_interview_questions", {"role": "Software Engineer"})
        ]
        
        for hallucinated_tool, arguments in test_cases:
            # Mock the AI provider
            mock_provider = Mock()
            mock_response = Mock()
            mock_response.tool_calls = [
                {
                    "name": hallucinated_tool,
                    "arguments": arguments
                }
            ]
            mock_response.usage = {"total_tokens": 100}
            mock_provider.generate_browser_response.return_value = mock_response
            mock_provider.get_provider_name.return_value = "ollama"
            mock_provider.model = "qwen2.5:3b"
            
            # Create BrowserAgent
            agent = BrowserAgent(provider=mock_provider, config=config)
            
            # Mock DOM toolkit
            mock_dom_toolkit = Mock()
            
            # Execute
            result = agent._execute_step_legacy(
                step="Apply for the job",
                dom_state={"elements": []},
                dom_toolkit=mock_dom_toolkit,
                job_data={
                    "title": "Software Engineer",
                    "company": "Test Company",
                    "user_details": {},
                    "resume_path": "/path/to/resume.pdf"
                }
            )
            
            # Assert: System should reject the hallucinated tool
            assert result["success"] is False, \
                f"Expected hallucinated tool '{hallucinated_tool}' to be rejected"
            
            assert result.get("error_type") == "HALLUCINATION_ERROR", \
                f"Expected HALLUCINATION_ERROR for '{hallucinated_tool}', got: {result.get('error_type')}"
            
            # Assert: Error message should include valid tools list
            error_message = result.get("error", "")
            assert "click_element" in error_message, \
                f"Error message should list valid tools for '{hallucinated_tool}'"
            assert "enter_text" in error_message, \
                f"Error message should list valid tools for '{hallucinated_tool}'"
            assert "select_option" in error_message, \
                f"Error message should list valid tools for '{hallucinated_tool}'"
