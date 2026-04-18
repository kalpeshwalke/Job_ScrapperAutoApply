"""
Bug Condition Exploration Test for MCP Connection Issue

This test demonstrates the bug where MCPClient.connect() fails because
it doesn't perform the required MCP protocol initialization handshake.

EXPECTED OUTCOME ON UNFIXED CODE: This test SHOULD FAIL
- The test encodes the expected behavior (successful connection with handshake)
- When it fails, it confirms the bug exists
- When it passes (after fix), it confirms the bug is resolved

Bug Condition: isBugCondition(connection_attempt) where:
  - connection_attempt.server_spawned = true
  - connection_attempt.initialize_request_sent = false
  - connection_attempt.list_tools_called = true
  - connection_attempt.connection_closed = true

Expected Behavior: Connection should establish successfully with complete handshake:
  - initialize request sent
  - server responds with capabilities
  - initialized notification sent
  - connection remains open
  - tools are discoverable
"""

import unittest
from unittest.mock import MagicMock, patch, call
import subprocess
import json
import sys
import os
import time

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.core.mcp_client import MCPClient


class TestMCPConnectionBugCondition(unittest.TestCase):
    """
    Property 1: Bug Condition - MCP Connection Without Protocol Handshake
    
    This test verifies that the MCP client performs the required protocol
    initialization handshake when connecting to the Playwright MCP server.
    
    The MCP protocol requires:
    1. Client sends 'initialize' request with protocol version and capabilities
    2. Server responds with its capabilities
    3. Client sends 'initialized' notification
    4. Only then can the client call tools
    
    Without this handshake, the server closes the connection with error -32000.
    """
    
    def setUp(self):
        """Set up test configuration"""
        self.config = {
            "enabled": True,
            "command": "npx",
            "args": ["-y", "@playwright/mcp-server"],
            "timeout": 30000,
            "autoApprove": ["playwright_*"]
        }
    
    @patch("subprocess.Popen")
    def test_mcp_connection_performs_initialization_handshake(self, mock_popen):
        """
        Test that MCPClient.connect() performs the MCP protocol initialization handshake.
        
        This test will FAIL on unfixed code because the current implementation
        skips the handshake and goes directly to list_tools(), causing the
        server to close the connection with error -32000.
        
        After the fix, this test will PASS, confirming the bug is resolved.
        """
        # Mock the MCP server process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        
        # Mock stdin for sending requests
        mock_stdin = MagicMock()
        mock_process.stdin = mock_stdin
        
        # Mock stdout for receiving responses
        # The server should respond to:
        # 1. initialize request -> server capabilities
        # 2. tools/list request -> list of tools
        mock_stdout = MagicMock()
        
        # Response to initialize request
        initialize_response = json.dumps({
            "jsonrpc": "2.0",
            "id": "initialize",
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "playwright-mcp-server",
                    "version": "1.0.0"
                }
            }
        }) + "\n"
        
        # Response to tools/list request
        tools_response = json.dumps({
            "jsonrpc": "2.0",
            "id": "list_tools",
            "result": {
                "tools": [
                    {"name": "playwright_navigate", "description": "Navigate to URL"},
                    {"name": "playwright_click", "description": "Click element"}
                ]
            }
        }) + "\n"
        
        # Set up readline to return responses in order
        mock_stdout.readline.side_effect = [initialize_response, tools_response]
        mock_process.stdout = mock_stdout
        
        mock_popen.return_value = mock_process
        
        # Create client and connect
        client = MCPClient(config=self.config)
        
        # Attempt to connect
        success = client.connect()
        
        # ASSERTIONS - These encode the expected behavior
        
        # 1. Connection should succeed
        self.assertTrue(success, "Connection should succeed with proper handshake")
        self.assertTrue(client.connected, "Client should be marked as connected")
        
        # 2. Verify the initialization handshake was performed
        # Check that stdin.write was called with the initialize request
        write_calls = mock_stdin.write.call_args_list
        
        # Should have at least 2 writes: initialize request + initialized notification
        # (plus tools/list request)
        self.assertGreaterEqual(
            len(write_calls), 
            2, 
            "Should have at least 2 writes: initialize request and initialized notification"
        )
        
        # Parse the first write call - should be initialize request
        first_write = write_calls[0][0][0]  # Get the first argument of first call
        first_request = json.loads(first_write.strip())
        
        self.assertEqual(
            first_request.get("method"), 
            "initialize",
            "First request should be 'initialize' method"
        )
        self.assertIn(
            "protocolVersion",
            first_request.get("params", {}),
            "Initialize request should include protocolVersion"
        )
        self.assertIn(
            "capabilities",
            first_request.get("params", {}),
            "Initialize request should include client capabilities"
        )
        
        # Parse the second write call - should be initialized notification
        second_write = write_calls[1][0][0]
        second_request = json.loads(second_write.strip())
        
        self.assertEqual(
            second_request.get("method"),
            "notifications/initialized",
            "Second request should be 'notifications/initialized' method"
        )
        
        # 3. Verify tools were discovered after handshake
        self.assertGreater(
            len(client.available_tools),
            0,
            "Tools should be discovered after successful handshake"
        )
        
        # 4. Verify the process is still running (connection not closed)
        self.assertIsNotNone(client.process, "Process should still be running")
        
        # Clean up
        client.disconnect()
    
    @patch("subprocess.Popen")
    def test_mcp_connection_handles_initialization_failure(self, mock_popen):
        """
        Test that MCPClient.connect() handles initialization failures gracefully.
        
        If the server doesn't respond to the initialize request or responds
        with an error, the connection should fail cleanly.
        """
        # Mock the MCP server process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        
        # Mock stdin/stdout
        mock_stdin = MagicMock()
        mock_process.stdin = mock_stdin
        
        mock_stdout = MagicMock()
        
        # Server responds with error to initialize request
        error_response = json.dumps({
            "jsonrpc": "2.0",
            "id": "initialize",
            "error": {
                "code": -32600,
                "message": "Invalid request"
            }
        }) + "\n"
        
        mock_stdout.readline.return_value = error_response
        mock_process.stdout = mock_stdout
        
        mock_popen.return_value = mock_process
        
        # Create client and attempt to connect
        client = MCPClient(config=self.config)
        success = client.connect()
        
        # Connection should fail gracefully
        self.assertFalse(success, "Connection should fail when initialization fails")
        self.assertFalse(client.connected, "Client should not be marked as connected")
        
        # Process should be terminated
        mock_process.terminate.assert_called_once()
    
    @patch("subprocess.Popen")
    def test_mcp_connection_handles_timeout(self, mock_popen):
        """
        Test that MCPClient.connect() handles timeout during initialization.
        
        If the server doesn't respond to the initialize request within the
        timeout period, the connection should fail.
        """
        # Mock the MCP server process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        
        # Mock stdin/stdout
        mock_stdin = MagicMock()
        mock_process.stdin = mock_stdin
        
        mock_stdout = MagicMock()
        # Simulate timeout by returning None (no response)
        mock_stdout.readline.return_value = None
        mock_process.stdout = mock_stdout
        
        mock_popen.return_value = mock_process
        
        # Create client with short timeout
        config = self.config.copy()
        config["timeout"] = 1000  # 1 second
        client = MCPClient(config=config)
        
        # Attempt to connect
        success = client.connect()
        
        # Connection should fail due to timeout
        self.assertFalse(success, "Connection should fail on initialization timeout")
        self.assertFalse(client.connected, "Client should not be marked as connected")


if __name__ == "__main__":
    unittest.main()
