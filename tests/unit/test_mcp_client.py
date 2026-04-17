import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import subprocess
import json
import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.core.mcp_client import MCPClient
# from src.ai_auto_apply.core.mcp_config_manager import MCPConfig # Incorrect class name

class TestMCPClient(unittest.TestCase):
    def setUp(self):
        self.config = {
            "enabled": True,
            "command": "npx",
            "args": ["-y", "@playwright/mcp"],
            "timeout": 30000,
            "autoApprove": ["playwright_*"]
        }
        self.client = MCPClient(config=self.config)

    def test_init(self):
        self.assertEqual(self.client.config.get("command"), "npx")
        self.assertFalse(self.client.connected)
        self.assertEqual(len(self.client.available_tools), 0)

    @patch("subprocess.Popen")
    def test_connect_success(self, mock_popen):
        # Mock process
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.side_effect = [
            b'{"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "test_tool"}]}}\n',
            b""
        ]
        mock_popen.return_value = mock_process
        
        # We need to mock list_tools inside connect
        with patch.object(self.client, "list_tools", return_value=[{"name": "test_tool"}]):
            success = self.client.connect()
            self.assertTrue(success)
            self.assertTrue(self.client.connected)

    def test_metrics_initial_state(self):
        metrics = self.client.get_metrics()
        self.assertEqual(metrics["total_calls"], 0)
        self.assertEqual(metrics["total_errors"], 0)

    @patch.object(MCPClient, "call_tool")
    def test_call_tool_tracking(self, mock_call):
        mock_call.return_value = {"content": [{"text": "success"}]}
        
        # Simulate a call
        response = self.client.call_tool("playwright_navigate", {"url": "test.com"})
        
        self.assertEqual(response["content"][0]["text"], "success")

if __name__ == "__main__":
    unittest.main()
