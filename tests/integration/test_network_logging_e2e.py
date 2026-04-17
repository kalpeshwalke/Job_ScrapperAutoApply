import pytest
import asyncio
import os
import sys
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.agents.browser_agent import BrowserAgent
from src.ai_auto_apply.core.structured_logger import StructuredLogger

@pytest.mark.asyncio
async def test_network_logging_e2e():
    """
    Integration test for network request logging.
    Verifies that network events are captured and logged.
    """
    # 1. Setup mocks
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    
    logger = StructuredLogger(component_name="browser", config={})
    agent = BrowserAgent(provider=MagicMock(), config={}, page=mock_page)
    agent.network_monitoring_enabled = True
    
    agent.set_page(mock_page)
    
    # 2. Extract the listener functions from mock calls
    # We look for 'on' calls with 'request' and 'response' events
    on_request = None
    on_response = None
    for call in mock_page.on.call_args_list:
        args, kwargs = call
        if args and args[0] == "request":
            on_request = args[1]
        elif args and args[0] == "response":
            on_response = args[1]
            
    if not on_request or not on_response:
        pytest.fail(f"Failed to extract network listeners. attached={agent._network_listener_attached}, calls={mock_page.on.call_args_list}")

    # Simulate a network request event
    request = MagicMock()
    request.url = "https://api.test.com/apply"
    request.method = "POST"
    request.resource_type = "xhr"
    
    response = MagicMock()
    response.url = request.url
    response.status = 201
    response.request = request
    
    # Execute handlers
    on_request(request)
    on_response(response)
    
    # 4. Verify logs (This depends on how StructuredLogger is implemented)
    # Since we can't easily check the file, we just ensure no crashes occurred
    assert len(agent.network_requests) > 0
    assert agent.network_requests[0]["url"] == request.url
    assert agent.network_requests[0]["status_code"] == 201

if __name__ == "__main__":
    pytest.main([__file__])
