"""
Action Observer

Post-action verification layer that checks if a browser action
actually had any effect. Detects no-ops, page navigations, modal
appearances, and form state changes.

This is the "verify" step in the Observe → Think → Act → Verify loop.
If an action had no effect, the target element gets penalized so the
system doesn't waste time clicking it again.
"""

import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from playwright.sync_api import Page
from src.common.logger import get_logger

logger = get_logger("observer")


class ResultType(Enum):
    """Classification of what happened after an action."""
    NAVIGATION = "navigation"       # URL changed
    MODAL_APPEARED = "modal"        # Dialog/overlay appeared
    FORM_UPDATE = "form_update"     # Form fields changed (new fields, values updated)
    CONTENT_CHANGE = "content"      # Page content changed but URL same
    NOOP = "noop"                   # Nothing observable changed


@dataclass
class ActionResult:
    """Result of observing what happened after an action."""
    success: bool
    result_type: ResultType
    details: str = ""
    penalize_ref: Optional[int] = None  # AX ref to penalize if noop
    new_url: str = ""
    new_element_count: int = 0


class PageSnapshot:
    """
    Lightweight snapshot of page state before an action.
    
    Captures only what's needed for comparison — not the full DOM.
    """

    def __init__(self, page: Page):
        try:
            self.url = page.url
        except Exception:
            self.url = ""
        
        try:
            self.title = page.title()
        except Exception:
            self.title = ""
        
        try:
            self.interactive_count = self._count_interactive(page)
        except Exception:
            self.interactive_count = 0
        
        try:
            self.has_modal = self._detect_modal(page)
        except Exception:
            self.has_modal = False
        
        try:
            self.form_field_count = self._count_form_fields(page)
        except Exception:
            self.form_field_count = 0
        
        self.timestamp = time.time()

    def _count_interactive(self, page: Page) -> int:
        """Count visible interactive elements."""
        try:
            return page.evaluate("""
                () => {
                    const els = document.querySelectorAll(
                        'button, a[href], input:not([type="hidden"]), textarea, select, '
                        + '[role="button"], [role="link"], [role="combobox"]'
                    );
                    let count = 0;
                    els.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) count++;
                    });
                    return count;
                }
            """)
        except Exception:
            return 0

    def _detect_modal(self, page: Page) -> bool:
        """Check if a modal/dialog/overlay is visible."""
        try:
            return page.evaluate("""
                () => {
                    // Check for open <dialog> elements
                    const dialogs = document.querySelectorAll('dialog[open]');
                    if (dialogs.length > 0) return true;
                    
                    // Check for common modal patterns
                    const modals = document.querySelectorAll(
                        '[role="dialog"], [role="alertdialog"], '
                        + '.modal.show, .modal.active, .modal.open, '
                        + '[class*="modal"][class*="visible"], '
                        + '[class*="overlay"][class*="active"], '
                        + '[class*="popup"][class*="show"]'
                    );
                    for (const m of modals) {
                        const rect = m.getBoundingClientRect();
                        const style = window.getComputedStyle(m);
                        if (rect.width > 0 && rect.height > 0 
                            && style.display !== 'none' 
                            && style.visibility !== 'hidden') {
                            return true;
                        }
                    }
                    return false;
                }
            """)
        except Exception:
            return False

    def _count_form_fields(self, page: Page) -> int:
        """Count visible form input fields."""
        try:
            return page.evaluate("""
                () => {
                    const fields = document.querySelectorAll(
                        'input:not([type="hidden"]), textarea, select'
                    );
                    let count = 0;
                    fields.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) count++;
                    });
                    return count;
                }
            """)
        except Exception:
            return 0


class ActionObserver:
    """
    Observes the effect of browser actions by comparing before/after page state.
    
    Usage:
        observer = ActionObserver()
        before = observer.snapshot(page)
        # ... execute action ...
        result = observer.observe(page, before, action_ref=13)
        
        if result.result_type == ResultType.NOOP:
            session.record_action(..., success=False, result_type="noop")
    """

    def __init__(self, settle_ms: int = 800):
        """
        Args:
            settle_ms: Milliseconds to wait after action before observing.
                       Allows AJAX/animations to complete.
        """
        self.settle_ms = settle_ms

    def snapshot(self, page: Page) -> PageSnapshot:
        """
        Take a snapshot of the current page state.
        
        Call this BEFORE executing an action.
        """
        return PageSnapshot(page)

    def observe(
        self,
        page: Page,
        before: PageSnapshot,
        action_ref: Optional[int] = None,
    ) -> ActionResult:
        """
        Observe what changed after an action by comparing snapshots.
        
        Call this AFTER executing an action (with settle time).
        
        Args:
            page: Current Playwright page
            before: Snapshot taken before the action
            action_ref: AX tree ref of the element that was acted on
            
        Returns:
            ActionResult describing what happened
        """
        # Wait for page to settle (AJAX, animations, redirects)
        time.sleep(self.settle_ms / 1000)

        after = PageSnapshot(page)

        # Priority 1: URL changed = navigation
        if after.url != before.url:
            logger.info(
                "Navigation detected: %s → %s",
                before.url[:60], after.url[:60],
            )
            return ActionResult(
                success=True,
                result_type=ResultType.NAVIGATION,
                details=f"URL changed: {before.url[:40]} → {after.url[:40]}",
                new_url=after.url,
                new_element_count=after.interactive_count,
            )

        # Priority 2: Modal appeared
        if after.has_modal and not before.has_modal:
            logger.info("Modal/dialog appeared after action")
            return ActionResult(
                success=True,
                result_type=ResultType.MODAL_APPEARED,
                details="Modal or dialog appeared",
                new_element_count=after.interactive_count,
            )

        # Priority 3: Form fields changed (new fields appeared or count changed)
        field_diff = after.form_field_count - before.form_field_count
        if abs(field_diff) >= 1:
            direction = "appeared" if field_diff > 0 else "removed"
            logger.info(
                "Form update: %d fields %s (before: %d, after: %d)",
                abs(field_diff), direction,
                before.form_field_count, after.form_field_count,
            )
            return ActionResult(
                success=True,
                result_type=ResultType.FORM_UPDATE,
                details=f"{abs(field_diff)} form fields {direction}",
                new_element_count=after.interactive_count,
            )

        # Priority 4: Interactive element count changed significantly
        element_diff = after.interactive_count - before.interactive_count
        if abs(element_diff) >= 3:
            logger.info(
                "Content change: %d element difference (before: %d, after: %d)",
                element_diff, before.interactive_count, after.interactive_count,
            )
            return ActionResult(
                success=True,
                result_type=ResultType.CONTENT_CHANGE,
                details=f"Element count changed by {element_diff}",
                new_element_count=after.interactive_count,
            )

        # Priority 5: Title changed (e.g., form step changed)
        if after.title != before.title:
            logger.info(
                "Title changed: '%s' → '%s'",
                before.title[:40], after.title[:40],
            )
            return ActionResult(
                success=True,
                result_type=ResultType.CONTENT_CHANGE,
                details=f"Title changed: {before.title[:30]} → {after.title[:30]}",
                new_element_count=after.interactive_count,
            )

        # Nothing changed = no-op
        logger.warning(
            "No-op detected: action on ref [%s] had no observable effect",
            action_ref or "N/A",
        )
        return ActionResult(
            success=False,
            result_type=ResultType.NOOP,
            details="No observable change after action",
            penalize_ref=action_ref,
            new_element_count=after.interactive_count,
        )

    def detect_blockers(self, page: Page) -> Dict[str, bool]:
        """
        Detect common blockers on the current page.
        
        Returns dict of detected blockers:
        - captcha: reCAPTCHA or similar challenge
        - login_wall: Login/register required
        - cookie_banner: Cookie consent overlay
        """
        try:
            return page.evaluate("""
                () => {
                    const body = document.body.innerText.toLowerCase();
                    const html = document.documentElement.innerHTML.toLowerCase();
                    
                    return {
                        captcha: (
                            html.includes('recaptcha') ||
                            html.includes('hcaptcha') ||
                            body.includes('verify you are human') ||
                            body.includes('i am not a robot') ||
                            html.includes('cloudflare')
                        ),
                        login_wall: (
                            body.includes('sign in to continue') ||
                            body.includes('log in to apply') ||
                            body.includes('create an account') ||
                            (document.querySelectorAll('input[type="password"]').length > 0 &&
                             !body.includes('application'))
                        ),
                        cookie_banner: (
                            document.querySelectorAll(
                                '[class*="cookie"], [id*="cookie"], [class*="consent"], '
                                + '[id*="consent"], [class*="gdpr"]'
                            ).length > 0
                        )
                    };
                }
            """)
        except Exception as e:
            logger.debug("Blocker detection failed: %s", e)
            return {"captcha": False, "login_wall": False, "cookie_banner": False}
