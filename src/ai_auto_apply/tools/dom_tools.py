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
        # Accessibility tree element mapping: {ref_number: {role, name}}
        self._ax_elements = {}
    
    # ----------------------------------------------------------------
    # Accessibility Tree (Industry-standard AI browser agent approach)
    # ----------------------------------------------------------------
    
    def get_accessibility_snapshot(self, depth: int = 5) -> str:
        """
        Get a compact accessibility tree representation of the page via CDP.
        
        Uses Chrome DevTools Protocol (Accessibility.getFullAXTree) to extract
        the browser's built-in accessibility tree. This is the same data source
        used by browser-use, Agent-E, and Playwright MCP.
        
        5-10x more token-efficient than sending raw DOM element lists.
        
        Args:
            depth: Controls how many interactive elements to include.
                   3 = navigation only (~30 elements, for finding careers links)
                   5 = standard (~80 elements, forms + buttons)
                   7 = deep (~150 elements, complex multi-section pages)
        
        Returns:
            Compact text representation with numbered interactive elements,
            or None if accessibility snapshot is unavailable.
        """
        self._ax_elements = {}
        
        try:
            # Create CDP session to query Chrome's accessibility tree directly
            client = self.page.context.new_cdp_session(self.page)
            result = client.send('Accessibility.getFullAXTree')
            nodes = result.get('nodes', [])
            
            if not nodes:
                logger.warning("CDP returned empty accessibility tree")
                client.detach()
                return None
            
            # Format the flat CDP nodes into compact text
            counter = [0]
            max_interactive = depth * 20  # Scale interactive element limit with depth
            formatted = self._format_cdp_ax_tree(nodes, max_interactive, counter)
            
            client.detach()
            
            logger.debug(
                "Accessibility tree: %d interactive elements, %d chars (from %d CDP nodes)",
                counter[0], len(formatted), len(nodes)
            )
            return formatted
            
        except Exception as e:
            logger.warning("CDP accessibility snapshot failed: %s", e)
            return None
    
    def _format_cdp_ax_tree(self, nodes: list, max_interactive: int = 80, counter: list = None) -> str:
        """
        Format flat CDP accessibility nodes into compact numbered text.
        
        CDP returns a flat list of AX nodes (not nested). Each node has:
        - role: {value: "link"}
        - name: {value: "Careers"}
        - children: [nodeId references]
        
        Output example:
            navigation "Main"
              [1] link "Home"
              [2] link "Careers"
            main
              heading "Welcome"
              [3] textbox "Your Name"
              [4] button "Submit"
        
        Args:
            nodes: Flat list of CDP AX tree nodes
            max_interactive: Maximum number of interactive elements to include
            counter: Mutable list for numbering interactive elements
            
        Returns:
            Formatted compact text string
        """
        if counter is None:
            counter = [0]
        
        # Interactive roles the AI can act on
        interactive_roles = {
            'link', 'button', 'textbox', 'combobox', 'checkbox',
            'radio', 'menuitem', 'option', 'searchbox', 'tab',
            'switch', 'spinbutton', 'slider'
        }
        
        # Structural roles to include for context
        structural_roles = {
            'banner', 'main', 'navigation', 'contentinfo', 'complementary',
            'form', 'region', 'article', 'heading'
        }
        
        # Roles to skip entirely (noise)
        skip_roles = {
            'generic', 'none', 'presentation', 'separator', 'StaticText',
            'InlineTextBox', 'LineBreak', 'paragraph', 'list', 'listitem',
            'image', 'figure', 'group', 'LayoutTable', 'LayoutTableRow',
            'LayoutTableCell'
        }
        
        lines = []
        
        for node in nodes:
            role = node.get('role', {}).get('value', '')
            name_obj = node.get('name', {})
            name = name_obj.get('value', '') if isinstance(name_obj, dict) else str(name_obj)
            
            # Clean name: remove icon characters and excess whitespace
            if name:
                name = ''.join(c for c in name if ord(c) < 0xE000 or ord(c) > 0xF8FF)
                name = ' '.join(name.split()).strip()
            
            # Skip noise roles
            if role in skip_roles:
                continue
            
            # Skip unnamed non-structural, non-interactive nodes
            if not name and role not in structural_roles and role not in interactive_roles:
                continue
            
            if role in interactive_roles and name:
                if counter[0] >= max_interactive:
                    continue  # Cap interactive elements
                counter[0] += 1
                idx = counter[0]
                # Store mapping for action execution
                self._ax_elements[idx] = {
                    "role": role,
                    "name": name,
                    "value": node.get('value', {}).get('value', '') if isinstance(node.get('value'), dict) else '',
                }
                lines.append(f'  [{idx}] {role} "{name}"')
                
            elif role in structural_roles:
                if name:
                    lines.append(f'{role} "{name}"')
                else:
                    lines.append(f'{role}')
        
        return "\n".join(lines)
    
    def _format_ax_tree(self, node: dict, max_depth: int = 5, level: int = 0, counter: list = None) -> str:
        """
        Recursively format a raw accessibility tree dict into compact text.
        
        Interactive elements get numbered references like [1], [2], etc.
        The AI references these numbers to indicate which element to interact with.
        
        Output example:
            banner
              navigation "Main"
                [1] link "Home"
                [2] link "Careers"
            main
              heading "Welcome" (h1)
              [3] textbox "Your Name"
              [4] textbox "Email"
              [5] button "Submit"
        
        Args:
            node: Raw accessibility tree node dict from Playwright
            max_depth: Maximum depth to traverse
            level: Current indentation level
            counter: Mutable list with single int for numbering interactive elements
        
        Returns:
            Formatted text string
        """
        if counter is None:
            counter = [0]
        if max_depth <= 0 or not node:
            return ""
        
        role = node.get("role", "")
        name = node.get("name", "")
        
        # Roles to skip (noise that adds tokens without value)
        skip_roles = {"generic", "none", "presentation", "separator", "StaticText"}
        if role in skip_roles and not name:
            # Still process children
            lines = []
            for child in node.get("children", []):
                child_text = self._format_ax_tree(child, max_depth - 1, level, counter)
                if child_text:
                    lines.append(child_text)
            return "\n".join(lines)
        
        # Interactive roles that the AI can act on
        interactive_roles = {
            "link", "button", "textbox", "combobox", "checkbox",
            "radio", "menuitem", "option", "searchbox", "tab",
            "switch", "spinbutton", "slider"
        }
        
        indent = "  " * level
        line_parts = []
        
        if role.lower() in interactive_roles:
            counter[0] += 1
            idx = counter[0]
            # Store mapping for action execution
            self._ax_elements[idx] = {
                "role": role,
                "name": name,
                "value": node.get("value", ""),
                "checked": node.get("checked"),
                "disabled": node.get("disabled", False)
            }
            # Format: [1] link "Careers"
            if name:
                line_parts.append(f'{indent}[{idx}] {role} "{name}"')
            else:
                line_parts.append(f'{indent}[{idx}] {role}')
        elif name:
            # Non-interactive but named (headings, landmarks, etc.)
            line_parts.append(f'{indent}{role} "{name}"')
        elif role and role not in {"group", "generic", "none"}:
            # Structural roles (banner, main, navigation, etc.)
            line_parts.append(f'{indent}{role}')
        
        # Process children
        children = node.get("children", [])
        if children and max_depth > 1:
            for child in children:
                child_text = self._format_ax_tree(child, max_depth - 1, level + 1, counter)
                if child_text:
                    line_parts.append(child_text)
        
        return "\n".join(line_parts)
    
    def get_element_by_ref(self, ref_id: int) -> dict:
        """
        Get element info by accessibility tree reference number.
        
        Args:
            ref_id: The [N] reference number from the formatted AX tree
            
        Returns:
            Dict with role and name, or empty dict if not found
        """
        return self._ax_elements.get(ref_id, {})
    
    def click_by_ref(self, ref_id: int):
        """
        Click an element using its accessibility tree reference number.
        
        Maps [N] references from AI decisions back to Playwright locators
        using get_by_role().
        
        Args:
            ref_id: The [N] reference number from the formatted AX tree
        """
        el = self._ax_elements.get(ref_id)
        if not el:
            raise ValueError(f"Element [{ref_id}] not found in accessibility tree")
        
        role = el["role"]
        name = el["name"]
        
        try:
            locator = self.page.get_by_role(role, name=name)
            if locator.count() > 1:
                logger.debug("Multiple matches for [%d] %s '%s', using first", ref_id, role, name)
                locator = locator.first
            locator.scroll_into_view_if_needed()
            locator.click(timeout=5000)
            logger.debug("Clicked [%d] %s '%s'", ref_id, role, name)
            time.sleep(0.5)
        except Exception as e:
            logger.error("Failed to click [%d] %s '%s': %s", ref_id, role, name, e)
            raise
    
    def fill_by_ref(self, ref_id: int, text: str):
        """
        Fill text, check a box, or select an option using its accessibility tree reference number.
        
        Automatically routes the interaction to Playwright's native .fill(), .check(),
        .uncheck(), or .select_option() based on the extracted ARIA role.
        
        Args:
            ref_id: The [N] reference number from the formatted AX tree
            text: The text to enter, or boolean logic ('true'/'yes') for toggles
        """
        el = self._ax_elements.get(ref_id)
        if not el:
            raise ValueError(f"Element [{ref_id}] not found in accessibility tree")
        
        role = el["role"]
        name = el["name"]
        
        try:
            locator = self.page.get_by_role(role, name=name)
            if locator.count() > 1:
                locator = locator.first
            locator.scroll_into_view_if_needed()
            
            # Action router based on role
            if role in {"checkbox", "radio", "switch", "menuitemcheckbox", "menuitemradio"}:
                # Handle boolean-like interactions natively
                text_lower = str(text).lower().strip()
                if text_lower in {"true", "yes", "on", "1", "check", "checked", "select"}:
                    locator.check(timeout=5000)
                    logger.debug("Checked [%d] %s '%s'", ref_id, role, name)
                else:
                    locator.uncheck(timeout=5000)
                    logger.debug("Unchecked [%d] %s '%s'", ref_id, role, name)
                    
            elif role in {"combobox", "listbox", "menu"}:
                # Handle select dropdown elements natively
                try:
                    locator.select_option(label=str(text), timeout=5000)
                    logger.debug("Selected option label [%d] %s '%s' = '%s'", ref_id, role, name, text)
                except Exception:
                    # Fallback to value if label select fails
                    locator.select_option(value=str(text), timeout=5000)
                    logger.debug("Selected option value [%d] %s '%s' = '%s'", ref_id, role, name, text)
                    
            else:
                # Fallback to standard text area/input filling
                locator.fill(str(text), timeout=5000)
                logger.debug("Filled [%d] %s '%s' with '%s'", ref_id, role, name, str(text)[:30])
                
            time.sleep(0.3)
        except Exception as e:
            logger.error("Failed to action [%d] %s '%s': %s", ref_id, role, name, e)
            raise
    
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
            
            # Apply relevance-based sorting and truncation to avoid missing critical elements
            if len(optimized_elements) > 80:
                logger.warning(f"DOM has {len(optimized_elements)} elements, applying relevance sorting before truncating to 80")
                optimized_elements = self._sort_elements_by_relevance(optimized_elements)[:80]
            
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
    
    def _sort_elements_by_relevance(self, elements: list) -> list:
        """
        Sort elements by relevance to prioritize interactive elements over generic content.
        
        Priority order (highest to lowest):
        1. Buttons and submit inputs (most likely to be action elements)
        2. Text inputs, textareas, selects (form fields)
        3. Links with action keywords (apply, submit, next, continue)
        4. Other inputs (checkboxes, radio, file)
        5. Links in navigation areas
        6. Generic links and other elements
        """
        def get_relevance_score(element: dict) -> int:
            tag = element.get('tag', '').lower()
            el_type = element.get('type', '').lower()
            text = element.get('text', '').lower()
            role = element.get('role', '').lower()
            
            # Priority 1: Buttons and submit inputs (score 1000+)
            if tag == 'button' or (tag == 'input' and el_type == 'submit'):
                return 1000
            if role == 'button':
                return 950
            
            # Priority 2: Form input fields (score 800+)
            if tag == 'input' and el_type in ('text', 'email', 'tel', 'number', 'password'):
                return 850
            if tag in ('textarea', 'select'):
                return 840
            
            # Priority 3: Action links (score 700+)
            if tag == 'a':
                action_keywords = ['apply', 'submit', 'next', 'continue', 'proceed', 'start', 'begin']
                if any(keyword in text for keyword in action_keywords):
                    return 750
            
            # Priority 4: Other inputs (score 600+)
            if tag == 'input' and el_type in ('checkbox', 'radio', 'file'):
                return 650
            
            # Priority 5: Navigation links (score 500+)
            if tag == 'a' and ('nav' in element.get('class', '').lower() or 'menu' in element.get('class', '').lower()):
                return 550
            
            # Priority 6: Generic elements (score 100+)
            if tag == 'a':
                return 200
            
            # Everything else gets base score
            return 100
        
        # Sort by relevance score (descending)
        return sorted(elements, key=get_relevance_score, reverse=True)
            
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
