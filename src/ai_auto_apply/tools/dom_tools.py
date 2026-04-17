"""
DOM Toolkit

Provides Python functions for manipulating Playwright browser instances.
"""

import time
from typing import Dict, Any, List
from playwright.sync_api import Page, Locator
from src.common.logger import get_logger

logger = get_logger("dom_toolkit")

class DOMToolkit:
    """Toolkit for DOM manipulation via Playwright, with deep frame penetration and advanced element detection."""
    
    def __init__(self, page: Page):
        """
        Initialize DOM toolkit.
        
        Args:
            page: Playwright Page instance
        """
        self.page = page
        self.mmid_counter = 0
    
    def inject_mmids(self):
        """
        Inject mmid attributes into all interactive elements across all frames.
        """
        script = """
        (startCounter) => {
            let counter = startCounter;
            try {
                const selectors = 'input:not([type="hidden"]), button, a[href], textarea, select, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="combobox"], [role="menuitem"], [role="option"], [tabindex]:not([tabindex="-1"]), label';
                const elements = document.querySelectorAll(selectors);
                elements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        if (!el.hasAttribute('mmid')) {
                            el.setAttribute('mmid', counter.toString());
                            counter++;
                        }
                    }
                });
            } catch(e) {}
            return counter;
        }
        """
        
        try:
            logger.debug("Injecting mmids via Playwright evaluate across all frames...")
            counter = 1
            
            # Start with main page
            try:
                counter = self.page.evaluate(script, counter)
            except Exception as e:
                logger.debug(f"Main page mmid evaluation skipped: {e}")
                
            # Iterate all frames to pierce through iframes (e.g. Workday/Greenhouse)
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                try:
                    counter = frame.evaluate(script, counter)
                except Exception:
                    pass
                    
            self.mmid_counter = counter - 1
            logger.debug("Injected mmid attributes into %d elements", self.mmid_counter)
            return self.mmid_counter
        except Exception as e:
            logger.error("Failed to inject mmids: %s", e)
            self.mmid_counter = 0
            return 0
    
    def get_dom_state(self) -> Dict[str, Any]:
        """
        Get current DOM state combining interactive elements across all frames.
        """
        script = """
        () => {
            const elements = [];
            try {
                const mmidElements = document.querySelectorAll('[mmid]');
                mmidElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;
                    
                    let options = [];
                    if (el.tagName.toLowerCase() === 'select') {
                        const optElements = el.querySelectorAll('option');
                        optElements.forEach(opt => {
                            options.push({
                                text: opt.innerText.trim(),
                                value: opt.getAttribute('value') || ''
                            });
                        });
                    }
                    
                    // Try to find an associated label
                    let labelText = '';
                    if (el.id) {
                        const labelEl = document.querySelector(`label[for="${el.id}"]`);
                        if (labelEl) labelText = labelEl.innerText.trim();
                    }
                    if (!labelText) {
                        const parentLabel = el.closest('label');
                        if (parentLabel) labelText = parentLabel.innerText.trim();
                    }
                    
                    elements.push({
                        mmid: el.getAttribute('mmid') || '',
                        tag: el.tagName.toLowerCase(),
                        type: el.getAttribute('type') || '',
                        text: (el.innerText || el.value || '').substring(0, 100).trim(),
                        label: labelText,
                        placeholder: el.getAttribute('placeholder') || '',
                        aria_label: el.getAttribute('aria-label') || '',
                        name: el.getAttribute('name') || '',
                        id: el.getAttribute('id') || '',
                        href: el.getAttribute('href') || '',
                        role: el.getAttribute('role') || '',
                        options: options.length > 0 ? options : undefined
                    });
                });
            } catch(e) {}
            return elements;
        }
        """
        
        try:
            all_elements = []
            
            # Extract from main page
            try:
                main_elements = self.page.evaluate(script)
                all_elements.extend(main_elements)
            except Exception as e:
                logger.debug(f"Main page DOM state evaluation skipped: {e}")
                
            # Extract from all sub-frames
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                try:
                    frame_elements = frame.evaluate(script)
                    if frame_elements:
                        all_elements.extend(frame_elements)
                except Exception:
                    pass
            
            url = self.page.url
            title = self.page.title()
            
            # Clean up JSON serialization
            # Clean up JSON serialization to save tokens
            optimized_elements = []
            for el in all_elements:
                opt_el = {}
                for k, v in el.items():
                    # Only include non-empty values
                    if v and v != '':
                        # Compress standard keys to save JSON overhead if desired, 
                        # but just stripping empty is enough.
                        opt_el[k] = v
                # Avoid passing completely empty tags except for mmid and tag
                if opt_el:
                    optimized_elements.append(opt_el)
            
            # Further protect against large DOMs (Groq 6k TPM limit constraint)
            if len(optimized_elements) > 80:
                logger.warning(f"DOM has {len(optimized_elements)} elements, truncating to top 80 to avoid TPM rate limits")
                optimized_elements = optimized_elements[:80]
            
            logger.debug("Retrieved DOM state: %d optimized elements across all frames", len(optimized_elements))
            
            return {
                "url": url,
                "title": title[:100],
                "elements": optimized_elements
            }
            
        except Exception as e:
            logger.error("Failed to get full DOM state: %s", e)
            return {
                "url": self.page.url if self.page else "",
                "title": "",
                "elements": []
            }
            
    def _get_locator(self, mmid: str) -> Locator:
        """Helper to find an element locator across all frames by mmid."""
        # Try main frame first
        try:
            loc = self.page.locator(f"//*[@mmid='{mmid}']").first
            if loc.count() > 0:
                return loc
        except Exception:
            pass
            
        # Try all other frames
        for frame in self.page.frames:
            try:
                loc = frame.locator(f"//*[@mmid='{mmid}']").first
                if loc.count() > 0:
                    return loc
            except Exception:
                continue
                
        raise ValueError(f"Element with mmid='{mmid}' not found in any frame")

    def click_element(self, mmid: str):
        """Click an element by mmid across any frame."""
        try:
            logger.debug("Attempting to click mmid=%s", mmid)
            locator = self._get_locator(mmid)
            locator.scroll_into_view_if_needed()
            locator.click(timeout=5000)
            logger.debug("Clicked element mmid=%s", mmid)
            time.sleep(0.5)
        except Exception as e:
            logger.error("Failed to click mmid=%s: %s", mmid, e)
            raise
    
    def enter_text(self, mmid: str, text: str):
        """Enter text into an input field across any frame."""
        try:
            locator = self._get_locator(mmid)
            locator.scroll_into_view_if_needed()
            locator.fill(text, timeout=5000)
            logger.debug("Entered text into mmid=%s", mmid)
            time.sleep(0.3)
        except Exception as e:
            logger.error("Failed to enter text into mmid=%s: %s", mmid, e)
            raise
    
    def upload_file(self, mmid: str, file_path: str):
        """Upload a file to a file input across any frame."""
        try:
            import os
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
                
            locator = self._get_locator(mmid)
            locator.scroll_into_view_if_needed()
            locator.set_input_files(file_path, timeout=5000)
            logger.debug("Uploaded file to mmid=%s: %s", mmid, file_path)
            time.sleep(0.5)
        except Exception as e:
            logger.error("Failed to upload file to mmid=%s: %s", mmid, e)
            raise

    def select_option(self, mmid: str, option_value: str):
        """Select an option from a dropdown by text, value, or label across any frame."""
        try:
            locator = self._get_locator(mmid)
            locator.scroll_into_view_if_needed()
            # Try to select by value or label
            locator.select_option(value=option_value, timeout=5000)
            logger.debug("Selected option '%s' in mmid=%s", option_value, mmid)
            time.sleep(0.5)
        except Exception as e:
            # If value fails, try selecting by visible text/label using a string match
            try:
                locator = self._get_locator(mmid)
                locator.select_option(label=option_value, timeout=5000)
                logger.debug("Selected option label '%s' in mmid=%s", option_value, mmid)
                time.sleep(0.5)
            except Exception as e2:
                logger.error("Failed to select option in mmid=%s: %s", mmid, e2)
                raise
    
    def press_key(self, key: str):
        """Press a keyboard key."""
        try:
            self.page.keyboard.press(key)
            logger.debug("Pressed key: %s", key)
            time.sleep(0.3)
        except Exception as e:
            logger.error("Failed to press key %s: %s", key, e)
            raise
    
    def navigate(self, url: str):
        """Navigate to a URL."""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            logger.debug("Navigated to: %s", url)
            time.sleep(1)
        except Exception as e:
            logger.error("Failed to navigate to %s: %s", url, e)
            raise
    
    def bulk_enter_text(self, fields: Dict[str, str]):
        for mmid, text in fields.items():
            try:
                self.enter_text(mmid, text)
            except Exception as e:
                logger.warning("Failed to fill field mmid=%s: %s", mmid, e)
