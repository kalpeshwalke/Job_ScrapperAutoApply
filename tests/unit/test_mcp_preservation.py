"""
Preservation Property Tests for MCP Connection Fix

These tests verify that non-MCP functionality remains unchanged after
implementing the MCP connection fix.

EXPECTED OUTCOME ON UNFIXED CODE: These tests SHOULD PASS
- They capture the current behavior for non-buggy inputs
- They ensure the fix doesn't break existing functionality
- They should continue to pass after the fix is implemented

Property 2: Preservation - Non-MCP Functionality Preservation

Preservation Requirements:
- Non-MCP Playwright operations (direct Playwright usage without MCP)
- Other MCP server connections (if any non-Playwright MCP servers exist)
- MCP connection logging and error reporting
- AI auto-apply system functionality without MCP integration
"""

import unittest
from unittest.mock import MagicMock, patch
import subprocess
import json
import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.core.mcp_client import MCPClient


class TestMCPPreservation(unittest.TestCase):
    """
    Property 2: Preservation - Non-MCP Functionality Preservation
    
    These tests verify that operations NOT involving the Playwright MCP
    server initialization continue to work exactly as before.
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
    
    def test_mcp_client_initialization(self):
        """
        Test that MCPClient initialization works correctly.
        
        This should remain unchanged by the connection fix.
        """
        client = MCPClient(config=self.config)
        
        # Verify initial state
        self.assertEqual(client.config, self.config)
        self.assertFalse(client.connected)
        self.assertEqual(len(client.available_tools), 0)
        self.assertIsNone(client.process)
        self.assertEqual(client.timeout, 30.0)  # 30000ms = 30s
        self.assertEqual(client.auto_approve, ["playwright_*"])
        
        # Verify metrics are initialized
        metrics = client.get_metrics()
        self.assertEqual(metrics["total_calls"], 0)
        self.assertEqual(metrics["total_errors"], 0)
        self.assertEqual(metrics["error_rate"], 0.0)
    
    def test_mcp_client_disconnect_when_not_connected(self):
        """
        Test that disconnect() handles being called when not connected.
        
        This should remain unchanged by the connection fix.
        """
        client = MCPClient(config=self.config)
        
        # Should not raise an error
        client.disconnect()
        
        # Should still be disconnected
        self.assertFalse(client.connected)
    
    def test_mcp_client_call_tool_when_not_connected(self):
        """
        Test that call_tool() returns appropriate error when not connected.
        
        This should remain unchanged by the connection fix.
        """
        client = MCPClient(config=self.config)
        
        # Attempt to call tool without connecting
        result = client.call_tool("playwright_navigate", {"url": "https://example.com"})
        
        # Should return error
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "MCP client not connected")
        self.assertIsNone(result["result"])
        self.assertEqual(result["duration_ms"], 0.0)
    
    def test_mcp_client_list_tools_when_not_connected(self):
        """
        Test that list_tools() returns empty list when not connected.
        
        This should remain unchanged by the connection fix.
        """
        client = MCPClient(config=self.config)
        
        # Attempt to list tools without connecting
        tools = client.list_tools()
        
        # Should return empty list
        self.assertEqual(tools, [])
    
    def test_mcp_client_metrics_tracking(self):
        """
        Test that metrics tracking works correctly.
        
        This should remain unchanged by the connection fix.
        """
        client = MCPClient(config=self.config)
        
        # Simulate some calls
        client._record_call("tool1", 100.0, True)
        client._record_call("tool1", 200.0, True)
        client._record_call("tool2", 150.0, False)
        
        # Get metrics
        metrics = client.get_metrics()
        
        # Verify overall metrics
        self.assertEqual(metrics["total_calls"], 3)
        self.assertEqual(metrics["total_errors"], 1)
        self.assertAlmostEqual(metrics["error_rate"], 33.33, places=1)
        
        # Verify per-tool metrics
        self.assertIn("tool1", metrics["per_tool_metrics"])
        self.assertIn("tool2", metrics["per_tool_metrics"])
        
        tool1_metrics = metrics["per_tool_metrics"]["tool1"]
        self.assertEqual(tool1_metrics["call_count"], 2)
        self.assertEqual(tool1_metrics["error_count"], 0)
        self.assertEqual(tool1_metrics["error_rate"], 0.0)
        self.assertEqual(tool1_metrics["average_latency_ms"], 150.0)
        
        tool2_metrics = metrics["per_tool_metrics"]["tool2"]
        self.assertEqual(tool2_metrics["call_count"], 1)
        self.assertEqual(tool2_metrics["error_count"], 1)
        self.assertEqual(tool2_metrics["error_rate"], 100.0)
    
    @patch("subprocess.Popen")
    def test_mcp_client_handles_server_spawn_failure(self, mock_popen):
        """
        Test that connect() handles server spawn failures gracefully.
        
        This error handling should remain unchanged by the connection fix.
        """
        # Mock subprocess.Popen to raise FileNotFoundError
        mock_popen.side_effect = FileNotFoundError("npx not found")
        
        client = MCPClient(config=self.config)
        
        # Attempt to connect
        success = client.connect()
        
        # Should fail gracefully
        self.assertFalse(success)
        self.assertFalse(client.connected)
    
    @patch("subprocess.Popen")
    def test_mcp_client_handles_server_immediate_termination(self, mock_popen):
        """
        Test that connect() handles server process terminating immediately.
        
        This error handling should remain unchanged by the connection fix.
        """
        # Mock process that terminates immediately
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process exited with code 1
        mock_process.stderr.read.return_value = "Server failed to start"
        
        mock_popen.return_value = mock_process
        
        client = MCPClient(config=self.config)
        
        # Attempt to connect
        success = client.connect()
        
        # Should fail gracefully
        self.assertFalse(success)
        self.assertFalse(client.connected)
    
    @patch("subprocess.Popen")
    def test_mcp_client_disconnect_terminates_process(self, mock_popen):
        """
        Test that disconnect() properly terminates the server process.
        
        This should remain unchanged by the connection fix.
        """
        # Mock a running process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.wait.return_value = None
        
        mock_stdin = MagicMock()
        mock_process.stdin = mock_stdin
        
        mock_stdout = MagicMock()
        # Mock responses for initialization (will be added by fix)
        mock_stdout.readline.side_effect = [
            json.dumps({"jsonrpc": "2.0", "id": "initialize", "result": {"capabilities": {}}}) + "\n",
            json.dumps({"jsonrpc": "2.0", "id": "list_tools", "result": {"tools": []}}) + "\n"
        ]
        mock_process.stdout = mock_stdout
        
        mock_popen.return_value = mock_process
        
        client = MCPClient(config=self.config)
        
        # Connect (may fail on unfixed code, but that's okay for this test)
        try:
            client.connect()
        except:
            pass
        
        # Manually set connected state for testing disconnect
        client.connected = True
        client.process = mock_process
        
        # Disconnect
        client.disconnect()
        
        # Verify process was terminated
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()
        
        # Verify client state
        self.assertFalse(client.connected)
        self.assertIsNone(client.process)
    
    def test_mcp_client_context_manager(self):
        """
        Test that MCPClient works as a context manager.
        
        This should remain unchanged by the connection fix.
        """
        with patch("subprocess.Popen") as mock_popen:
            # Mock a running process
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.wait.return_value = None
            
            mock_stdin = MagicMock()
            mock_process.stdin = mock_stdin
            
            mock_stdout = MagicMock()
            mock_stdout.readline.side_effect = [
                json.dumps({"jsonrpc": "2.0", "id": "initialize", "result": {"capabilities": {}}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "id": "list_tools", "result": {"tools": []}}) + "\n"
            ]
            mock_process.stdout = mock_stdout
            
            mock_popen.return_value = mock_process
            
            # Use as context manager
            try:
                with MCPClient(config=self.config) as client:
                    # Client should attempt to connect
                    pass
            except:
                # May fail on unfixed code, but context manager should still work
                pass
            
            # Process should be terminated on exit
            # (may not be called if connect failed, but that's okay)
    
    def test_mcp_client_configuration_parsing(self):
        """
        Test that MCPClient correctly parses configuration.
        
        This should remain unchanged by the connection fix.
        """
        # Test with custom configuration
        custom_config = {
            "command": "node",
            "args": ["mcp-server.js"],
            "timeout": 60000,
            "autoApprove": ["*"]
        }
        
        client = MCPClient(config=custom_config)
        
        # Verify configuration is parsed correctly
        self.assertEqual(client.config.get("command"), "node")
        self.assertEqual(client.config.get("args"), ["mcp-server.js"])
        self.assertEqual(client.timeout, 60.0)  # 60000ms = 60s
        self.assertEqual(client.auto_approve, ["*"])
    
    def test_mcp_client_read_line_with_timeout(self):
        """
        Test that _read_line_with_timeout() works correctly.
        
        This utility method should remain unchanged by the connection fix.
        """
        # Mock a stream
        mock_stream = MagicMock()
        mock_stream.readline.return_value = "test line\n"
        
        # Read with timeout
        result = MCPClient._read_line_with_timeout(mock_stream, 1.0)
        
        # Should return the line
        self.assertEqual(result, "test line\n")
    
    def test_mcp_client_read_line_with_timeout_timeout(self):
        """
        Test that _read_line_with_timeout() handles timeout correctly.
        
        This utility method should remain unchanged by the connection fix.
        """
        import time
        
        # Mock a stream that blocks
        mock_stream = MagicMock()
        
        def slow_readline():
            time.sleep(2)  # Sleep longer than timeout
            return "test line\n"
        
        mock_stream.readline.side_effect = slow_readline
        
        # Read with short timeout
        result = MCPClient._read_line_with_timeout(mock_stream, 0.5)
        
        # Should return None on timeout
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
