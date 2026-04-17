import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.agents.planner_agent import PlannerAgent, PageStructureType

class TestPlannerAgent(unittest.TestCase):
    def setUp(self):
        self.mock_provider = MagicMock()
        self.config = {
            "mcp": {"enabled": False},
            "logging": {"log_ai_decisions": False}
        }
        self.agent = PlannerAgent(self.mock_provider, self.config)

    def test_plan_next_step_success(self):
        # Mock AI response
        mock_response = MagicMock()
        mock_response.content = '{"next_step": "Click apply", "reasoning": "Found button", "status": "in_progress"}'
        mock_response.usage = {"total_tokens": 100}
        self.mock_provider.generate_planner_response.return_value = mock_response
        
        job_data = {"title": "QA", "company": "TestCo"}
        dom_state = {"elements": []}
        
        decision = self.agent.plan_next_step(job_data, dom_state, 1, [])
        
        self.assertEqual(decision["status"], "in_progress")
        self.assertEqual(decision["next_step"], "Click apply")

    def test_detect_page_structure_job_board(self):
        dom_state = {
            "elements": [
                {"tag": "a", "text": "View Job 1"},
                {"tag": "a", "text": "View Job 2"},
                {"tag": "a", "text": "View Job 3"},
                {"tag": "a", "text": "View Job 4"},
                {"tag": "a", "text": "View Job 5"},
            ]
        }
        
        structure = self.agent.detect_page_structure("https://test.com/careers", dom_state)
        
        self.assertEqual(structure.type, PageStructureType.JOB_BOARD)
        self.assertGreaterEqual(structure.confidence, 0.7)

    def test_detect_page_structure_form(self):
        dom_state = {
            "elements": [
                {"tag": "input", "type": "text", "placeholder": "First Name"},
                {"tag": "input", "type": "text", "placeholder": "Last Name"},
                {"tag": "input", "type": "email", "placeholder": "Email"},
                {"tag": "button", "text": "Submit"}
            ]
        }
        
        structure = self.agent.detect_page_structure("https://test.com/apply", dom_state)
        
        self.assertEqual(structure.type, PageStructureType.DIRECT_FORM)

    def test_select_best_element_fuzzy(self):
        candidates = [
            {"mmid": "1", "text": "Apply Now", "tag": "button"},
            {"mmid": "2", "text": "Contact Us", "tag": "button"}
        ]
        
        best = self.agent.select_best_element(candidates, "Apply")
        
        self.assertEqual(best["mmid"], "1")

if __name__ == "__main__":
    unittest.main()
