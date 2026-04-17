import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.core.orchestrator import FSMOrchestrator

class TestCoreInfrastructure(unittest.TestCase):
    def setUp(self):
        self.mock_provider = MagicMock()
        self.config = {
            "fsm": {"max_iterations": 5},
            "screenshots": {"retention_days": 30, "directory": "logs/screenshots"},
            "logging": {"log_ai_decisions": False}
        }
        self.excel_path = "data/master_tracker.xlsx"
        
        # Patch dependencies that require filesystem or browser
        with patch("src.ai_auto_apply.core.orchestrator.AntiSpamTracker"), \
             patch("src.ai_auto_apply.core.orchestrator.CareerPageValidator"), \
             patch("src.ai_auto_apply.core.orchestrator.StructuredLogger"), \
             patch("src.ai_auto_apply.core.orchestrator.FSMOrchestrator._cleanup_old_screenshots"):
            self.orchestrator = FSMOrchestrator(self.mock_provider, self.config, self.excel_path)

    def test_init(self):
        self.assertEqual(self.orchestrator.max_iterations, 5)
        self.assertIsNotNone(self.orchestrator.planner)
        self.assertIsNotNone(self.orchestrator.browser_agent)

    @patch("src.ai_auto_apply.core.orchestrator.os.path.exists")
    @patch("src.ai_auto_apply.core.orchestrator.os.walk")
    @patch("src.ai_auto_apply.core.orchestrator.os.remove")
    def test_cleanup_old_screenshots(self, mock_remove, mock_walk, mock_exists):
        mock_exists.return_value = True
        mock_walk.return_value = [
            ("logs/screenshots", [], ["old.png", "new.png"])
        ]
        
        # Mock mtime to make old.png look old
        with patch("src.ai_auto_apply.core.orchestrator.os.path.getmtime") as mock_mtime:
            import time
            mock_mtime.side_effect = [time.time() - 40*24*3600, time.time()]
            self.orchestrator._cleanup_old_screenshots()
            
            mock_remove.assert_called_once_with("logs/screenshots\\old.png")

    def test_apply_to_job_validation_failure(self):
        self.orchestrator.validator.validate.return_value = ("No", "Not a career page")
        
        job_data = {
            "title": "Engineer",
            "company": "FakeCo",
            "career_url": "https://fake.com",
            "excel_index": 1
        }
        
        result = self.orchestrator.apply_to_job(job_data)
        
        self.assertEqual(result["status"], "failed")
        self.assertIn("Invalid career page", result["reason"])

if __name__ == "__main__":
    unittest.main()
