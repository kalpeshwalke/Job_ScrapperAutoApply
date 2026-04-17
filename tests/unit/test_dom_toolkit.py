import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.tools.dom_tools import DOMToolkit

class TestDOMToolkit(unittest.TestCase):
    def setUp(self):
        self.mock_page = MagicMock()
        self.toolkit = DOMToolkit(self.mock_page)

    def test_inject_mmids(self):
        # Setup mock behavior
        self.mock_page.evaluate.return_value = 10
        self.mock_page.frames = []
        
        result = self.toolkit.inject_mmids()
        
        self.assertEqual(result, 9) # counter returns 10, so 10-1
        self.mock_page.evaluate.assert_called_once()

    def test_get_dom_state(self):
        # Mock elements
        raw_elements = [
            {"mmid": "1", "tag": "input", "type": "text", "text": "Name"},
            {"mmid": "2", "tag": "button", "text": "Submit", "id": "btn-1"}
        ]
        self.mock_page.evaluate.return_value = raw_elements
        self.mock_page.url = "https://test.com"
        self.mock_page.title.return_value = "Test Page"
        self.mock_page.frames = []
        
        state = self.toolkit.get_dom_state()
        
        self.assertEqual(state["url"], "https://test.com")
        self.assertEqual(len(state["elements"]), 2)
        self.assertEqual(state["elements"][0]["mmid"], "1")

    @patch.object(DOMToolkit, "_get_locator")
    def test_click_element(self, mock_get_locator):
        mock_loc = MagicMock()
        mock_get_locator.return_value = mock_loc
        
        self.toolkit.click_element("1")
        
        mock_loc.scroll_into_view_if_needed.assert_called_once()
        mock_loc.click.assert_called_once()

    @patch.object(DOMToolkit, "_get_locator")
    def test_enter_text(self, mock_get_locator):
        mock_loc = MagicMock()
        mock_get_locator.return_value = mock_loc
        
        self.toolkit.enter_text("1", "Hello World")
        
        mock_loc.fill.assert_called_with("Hello World", timeout=5000)

if __name__ == "__main__":
    unittest.main()
