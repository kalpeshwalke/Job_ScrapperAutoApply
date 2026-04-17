import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.agents.browser_agent import BrowserAgent

class TestBrowserAgent(unittest.TestCase):
    def setUp(self):
        self.mock_provider = MagicMock()
        self.config = {
            "mcp": {"enabled": False},
            "logging": {"log_dom_interactions": False},
            "screenshots": {"enabled": False},
            "network_monitoring": {"enabled": True}
        }
        self.agent = BrowserAgent(self.mock_provider, self.config)

    def test_network_monitoring_setup(self):
        mock_page = MagicMock()
        self.agent.set_page(mock_page)
        
        self.assertTrue(self.agent._network_listener_attached)
        mock_page.on.assert_any_call("request", unittest.mock.ANY)
        mock_page.on.assert_any_call("response", unittest.mock.ANY)

    def test_detect_form_submission_success(self):
        # Setup simulated network requests
        self.agent.network_requests = [
            {
                "method": "POST",
                "url": "https://api.test.com/v1/apply",
                "status_code": 201,
                "resource_type": "xhr",
                "timestamp": datetime.now().isoformat()
            }
        ]
        
        result = self.agent.detect_form_submission()
        
        self.assertIsNotNone(result)
        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 201)

    def test_detect_form_submission_failure(self):
        self.agent.network_requests = [
            {
                "method": "POST",
                "url": "https://api.test.com/v1/apply",
                "status_code": 400,
                "resource_type": "xhr",
                "timestamp": datetime.now().isoformat()
            }
        ]
        
        result = self.agent.detect_form_submission()
        
        self.assertIsNotNone(result)
        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 400)

    def test_calculate_adaptive_wait_time(self):
        # 10 elements -> 1000 + (10//10 * 100) = 1100
        wait_time = self.agent.calculate_adaptive_wait_time(10)
        self.assertEqual(wait_time, 1100)
        
        # 100 elements -> 1000 + (100//10 * 100) = 2000
        wait_time = self.agent.calculate_adaptive_wait_time(100)
        self.assertEqual(wait_time, 2000)

    @patch("src.ai_auto_apply.agents.browser_agent.Path")
    def test_capture_screenshot_disabled(self, mock_path):
        self.agent.screenshot_enabled = False
        result = self.agent.capture_screenshot("test")
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
