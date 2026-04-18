"""
Deterministic Rule Engine

Handles 70-80% of all browser interactions WITHOUT any AI calls.
Uses ordered selector chains, regex field mapping, and element scoring
to make deterministic decisions.

The AI is only called when the rule engine cannot make a confident decision
(e.g., multiple equally-scored candidates, unknown field labels).

This is Layer 1 in the architecture:
    Rule Engine → (Narrow AI fallback) → DOMToolkit → Observer → Memory
"""

import re
import time
from typing import Dict, Any, List, Optional, Tuple
from playwright.sync_api import Page, Locator
from src.common.logger import get_logger
from src.ai_auto_apply.core.profile_store import ProfileStore
from src.ai_auto_apply.tools.dom_tools import DOMToolkit

logger = get_logger("rule_engine")


# ============================================================
#  SELECTOR CHAINS — Ordered fallback patterns for key actions
# ============================================================

# Careers / Jobs page link selectors (tried in order)
CAREERS_SELECTORS = [
    # Direct URL-based selectors (highest confidence)
    'a[href*="/careers"]',
    'a[href*="/jobs"]',
    'a[href*="/career"]',
    'a[href*="/join-us"]',
    'a[href*="/work-with-us"]',
    'a[href*="/openings"]',
    'a[href*="/opportunities"]',
    # Text-based selectors
    'a:text-matches("^Careers$", "i")',
    'a:text-matches("^Jobs$", "i")',
    'a:text-matches("^Join Us$", "i")',
    'a:text-matches("^Work With Us$", "i")',
    'a:text-matches("^Join Our Team$", "i")',
    'a:text-matches("^Openings$", "i")',
    'a:text-matches("^Opportunities$", "i")',
    # Broader text matches (lower confidence)
    'a:text-matches("careers|career", "i")',
    'button:text-matches("careers|career", "i")',
    'a:text-matches("jobs|job openings|search jobs|explore all jobs|explore jobs|view jobs", "i")',
    'button:text-matches("jobs|job openings|search jobs|explore all jobs|explore jobs|view jobs", "i")',
    '[role="button"]:text-matches("explore|search jobs|view all", "i")',
    'a:text-matches("hiring|we.*hiring", "i")',
]

# Apply button selectors (tried in order)
APPLY_SELECTORS = [
    # Direct apply buttons
    'button:text-matches("^Apply Now$", "i")',
    'a:text-matches("^Apply Now$", "i")',
    'button:text-matches("^Apply$", "i")',
    'a:text-matches("^Apply$", "i")',
    'button:text-matches("^Apply for this", "i")',
    'a:text-matches("^Apply for this", "i")',
    # Data attribute selectors
    '[data-automation*="apply" i]',
    '[data-testid*="apply" i]',
    '[id*="apply-button" i]',
    '[id*="applyButton" i]',
    '[class*="apply-btn" i]',
    '[class*="applyButton" i]',
    # Broader matches
    'button:text-matches("apply", "i")',
    'a:text-matches("apply", "i")',
    '[role="button"]:text-matches("apply", "i")',
]

# Submit / Next / Continue button selectors
SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:text-matches("^Submit$|^Submit Application$", "i")',
    'button:text-matches("^Next$|^Continue$|^Proceed$", "i")',
    'a:text-matches("^Next$|^Continue$|^Proceed$", "i")',
    'button:text-matches("^Save & Continue$|^Save and Continue$", "i")',
    'button:text-matches("^Review$|^Review Application$", "i")',
]

# Resume upload selectors
RESUME_SELECTORS = [
    'input[type="file"][accept*="pdf"]',
    'input[type="file"][accept*="doc"]',
    'input[type="file"][name*="resume" i]',
    'input[type="file"][id*="resume" i]',
    'input[type="file"][name*="cv" i]',
    'input[type="file"]',  # Last resort: any file input
]

# Negative patterns -- elements to NEVER click
NEVER_CLICK_PATTERNS = [
    r"sign\s*in|log\s*in|register|create\s*account",
    r"facebook|twitter|linkedin|google",   # Social login buttons
    r"subscribe|newsletter",
    r"download\s*app",
    r"chat|support|help",
    r"cookie|privacy|terms",
]

# ATS platform detection patterns (URL -> platform name)
ATS_PATTERNS = {
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "myworkdayjobs.com": "workday",
    "myworkday.com": "workday",
    "smartrecruiters.com": "smartrecruiters",
    "icims.com": "icims",
    "taleo.net": "taleo",
    "jobvite.com": "jobvite",
    "ashbyhq.com": "ashby",
    "bamboohr.com": "bamboohr",
    "applytojob.com": "bamboohr",
}

def detect_ats_platform(url: str) -> Optional[str]:
    """Detect which ATS platform a URL belongs to.
    
    Returns:
        Platform name string (e.g. 'greenhouse', 'lever') or None.
    """
    url_lower = url.lower()
    for pattern, platform in ATS_PATTERNS.items():
        if pattern in url_lower:
            return platform
    return None


class ScoredElement:
    """An element with a confidence score for ranking."""

    def __init__(
        self,
        locator: Locator,
        text: str,
        href: str,
        score: float,
        reason: str,
    ):
        self.locator = locator
        self.text = text
        self.href = href
        self.score = score
        self.reason = reason

    def __repr__(self):
        return f"ScoredElement('{self.text[:30]}', score={self.score:.1f})"


class RuleEngine:
    """
    Deterministic decision engine for browser automation.
    
    Provides three core capabilities:
    1. find_element() — Find the best matching element for a given action
    2. map_form_fields() — Map all form fields to profile values
    3. score_elements() — Score and rank elements for disambiguation
    
    Usage:
        engine = RuleEngine(page, profile_store)
        
        # Find careers link deterministically
        result = engine.find_careers_link()
        if result["confidence"] == "high":
            result["locator"].click()
        elif result["confidence"] == "ambiguous":
            # Send result["candidates"] to narrow AI for disambiguation
            pass
        else:
            # No match found
            pass
    """

    def __init__(self, page: Page, profile: ProfileStore):
        """
        Args:
            page: Playwright Page instance
            profile: Loaded ProfileStore instance
        """
        self.page = page
        self.profile = profile

    # ============================================================
    #  CAREERS LINK DETECTION
    # ============================================================

    def find_careers_link(
        self,
        failed_refs: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Find the careers/jobs page link using deterministic selector chains.
        
        Returns:
            {
                "confidence": "high" | "ambiguous" | "none",
                "locator": Locator | None,   # Best match (if high confidence)
                "candidates": List[ScoredElement],  # All matches (for AI disambiguation)
                "reason": str,
            }
        """
        candidates = []
        current_domain = self._get_domain()

        for selector in CAREERS_SELECTORS:
            try:
                elements = self.page.locator(selector).all()
                for el in elements:
                    if not self._is_visible(el):
                        continue

                    text = self._safe_text(el)
                    href = el.get_attribute("href") or ""

                    # Skip social media and external links
                    if self._is_external_noise(href, text, current_domain):
                        continue

                    # Score the element
                    score = self._score_careers_link(text, href, el, current_domain)

                    if score > 0:
                        candidates.append(ScoredElement(
                            locator=el,
                            text=text,
                            href=href,
                            score=score,
                            reason=f"selector: {selector[:40]}",
                        ))
            except Exception as e:
                logger.debug("Selector failed: %s — %s", selector[:40], e)
                continue

        # Deduplicate by href
        candidates = self._dedupe_by_href(candidates)

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)

        if not candidates:
            logger.info("No careers link found by rule engine")
            return {"confidence": "none", "locator": None, "candidates": [], "reason": "No matching elements"}

        best = candidates[0]

        # High confidence: clear winner with big margin OR absolute strong score
        if best.score >= 35:
            # Absolute floor: strong URL + exact text match = always high
            logger.info(
                "Careers link found (HIGH/absolute): '%s' -> %s (score: %.1f)",
                best.text[:40], best.href[:60], best.score,
            )
            return {
                "confidence": "high",
                "locator": best.locator,
                "candidates": candidates[:3],
                "reason": f"Clear winner: '{best.text[:30]}' (score: {best.score:.0f})",
            }

        if best.score >= 20 and (len(candidates) == 1 or best.score > candidates[1].score * 1.3):
            logger.info(
                "Careers link found (HIGH): '%s' -> %s (score: %.1f)",
                best.text[:40], best.href[:60], best.score,
            )
            return {
                "confidence": "high",
                "locator": best.locator,
                "candidates": candidates[:3],
                "reason": f"Clear winner: '{best.text[:30]}' (score: {best.score:.0f})",
            }

        # Ambiguous: multiple close candidates — needs AI
        logger.info(
            "Careers link ambiguous: %d candidates (top: '%s' score=%.1f, #2: '%s' score=%.1f)",
            len(candidates),
            best.text[:30], best.score,
            candidates[1].text[:30] if len(candidates) > 1 else "N/A",
            candidates[1].score if len(candidates) > 1 else 0,
        )
        return {
            "confidence": "ambiguous",
            "locator": None,
            "candidates": candidates[:5],
            "reason": f"{len(candidates)} ambiguous candidates",
        }

    def _score_careers_link(
        self,
        text: str,
        href: str,
        el: Locator,
        current_domain: str,
    ) -> float:
        """Score a potential careers link. Higher = more likely careers page."""
        score = 0.0
        text_lower = text.lower().strip()
        href_lower = href.lower()

        # Exact text matches (strongest signal)
        exact_matches = {"careers", "jobs", "career", "join us", "join our team", "work with us", "openings"}
        if text_lower in exact_matches:
            score += 40

        # URL path matches
        careers_url_patterns = ["/careers", "/jobs", "/career", "/join-us", "/work-with-us"]
        for pattern in careers_url_patterns:
            if pattern in href_lower:
                score += 20
                break

        # Keyword in text (partial)
        text_keywords = ["career", "job", "hiring", "opening", "opportunit", "join", "work with"]
        for kw in text_keywords:
            if kw in text_lower:
                score += 8
                break

        # Same domain boost
        if current_domain and self._is_same_domain(href, current_domain):
            score *= 1.5

        # Navigation element boost
        try:
            in_nav = el.evaluate("""
                el => {
                    let node = el;
                    for (let i = 0; i < 6; i++) {
                        node = node.parentElement;
                        if (!node) return false;
                        const tag = node.tagName.toLowerCase();
                        if (tag === 'nav' || tag === 'header') return true;
                    }
                    return false;
                }
            """)
            if in_nav:
                score *= 1.3
        except Exception:
            pass

        # Penalties
        penalty_keywords = ["blog", "course", "product", "pricing", "mock", "interview prep", "login", "sign"]
        for pk in penalty_keywords:
            if pk in text_lower or pk in href_lower:
                score -= 50

        return max(score, 0)

    # ============================================================
    #  APPLY BUTTON DETECTION
    # ============================================================

    def find_apply_button(
        self,
        failed_refs: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Find the apply button on a job detail page.
        
        Returns same format as find_careers_link().
        """
        candidates = []

        for selector in APPLY_SELECTORS:
            try:
                elements = self.page.locator(selector).all()
                for el in elements:
                    if not self._is_visible(el):
                        continue

                    text = self._safe_text(el)

                    # Skip obvious non-apply buttons
                    if self._is_never_click(text):
                        continue

                    score = self._score_apply_button(text, el)
                    if score > 0:
                        candidates.append(ScoredElement(
                            locator=el, text=text, href="",
                            score=score, reason=f"selector: {selector[:40]}",
                        ))
            except Exception as e:
                logger.debug("Apply selector failed: %s — %s", selector[:40], e)

        # Deduplicate and sort
        candidates = self._dedupe_by_text(candidates)
        candidates.sort(key=lambda c: c.score, reverse=True)

        if not candidates:
            return {"confidence": "none", "locator": None, "candidates": [], "reason": "No apply button found"}

        best = candidates[0]

        if best.score >= 15 and (len(candidates) == 1 or best.score > candidates[1].score * 1.5):
            logger.info("Apply button found (HIGH): '%s' (score: %.1f)", best.text[:40], best.score)
            return {
                "confidence": "high",
                "locator": best.locator,
                "candidates": candidates[:3],
                "reason": f"Clear winner: '{best.text[:30]}'",
            }

        logger.info("Apply button ambiguous: %d candidates", len(candidates))
        return {
            "confidence": "ambiguous",
            "locator": None,
            "candidates": candidates[:5],
            "reason": f"{len(candidates)} ambiguous candidates",
        }

    def _score_apply_button(self, text: str, el: Locator) -> float:
        """Score a potential apply button."""
        score = 0.0
        text_lower = text.lower().strip()

        # Exact matches
        if text_lower in {"apply now", "apply", "apply for this job", "apply for this position"}:
            score += 30

        # Partial keyword
        if "apply" in text_lower:
            score += 15

        # Penalties for non-apply actions
        filters = ["filter", "save", "share", "bookmark", "print", "email", "alert"]
        for f in filters:
            if f in text_lower:
                score -= 30

        # Prominent position (larger buttons)
        try:
            box = el.bounding_box()
            if box and box["width"] > 100:
                score += 5
        except Exception:
            pass

        return max(score, 0)

    # ============================================================
    #  SUBMIT / NEXT BUTTON DETECTION
    # ============================================================

    def find_submit_button(self) -> Dict[str, Any]:
        """Find the submit/next/continue button on a form page."""
        candidates = []

        for selector in SUBMIT_SELECTORS:
            try:
                elements = self.page.locator(selector).all()
                for el in elements:
                    if not self._is_visible(el):
                        continue
                    text = self._safe_text(el)
                    if self._is_never_click(text):
                        continue
                    score = 10.0
                    tl = text.lower().strip()
                    if tl in {"submit", "submit application", "apply"}:
                        score += 20
                    elif tl in {"next", "continue", "proceed", "save & continue", "save and continue"}:
                        score += 15
                    elif tl in {"review", "review application"}:
                        score += 12
                    candidates.append(ScoredElement(locator=el, text=text, href="", score=score, reason=selector[:30]))
            except Exception:
                continue

        candidates = self._dedupe_by_text(candidates)
        candidates.sort(key=lambda c: c.score, reverse=True)

        if not candidates:
            return {"confidence": "none", "locator": None, "candidates": [], "reason": "No submit button found"}

        best = candidates[0]
        if best.score >= 20:
            return {"confidence": "high", "locator": best.locator, "candidates": candidates[:3], "reason": best.text}

        return {"confidence": "ambiguous", "locator": None, "candidates": candidates[:5], "reason": "ambiguous"}

    # ============================================================
    #  FORM FIELD MAPPING
    # ============================================================

    def map_form_fields(
        self,
        dom_toolkit: DOMToolkit,
        already_filled: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Map all visible form fields to profile values using deterministic regex.
        
        Returns a list of field mappings:
        [
            {
                "ref": 5,           # AX tree ref
                "label": "Email",   # Field label
                "value": "user@...",# Value to fill (from profile)
                "confidence": "high" | "needs_ai",
                "action": "fill" | "select" | "upload" | "skip",
            }
        ]
        
        Fields that don't match any pattern get confidence="needs_ai"
        so the orchestrator knows to ask the narrow AI.
        """
        already_filled = already_filled or {}
        mappings = []

        # Get AX tree elements
        ax_elements = dom_toolkit._ax_elements

        if not ax_elements:
            # Refresh AX tree
            dom_toolkit.get_accessibility_snapshot(depth=7)
            ax_elements = dom_toolkit._ax_elements

        for ref_id, el_info in ax_elements.items():
            role = el_info.get("role", "")
            name = el_info.get("name", "")
            value = el_info.get("value", "")

            # Skip non-input elements
            if role not in {"textbox", "combobox", "searchbox", "spinbutton", "checkbox", "radio"}:
                continue

            # Skip already-filled fields
            if name and name in already_filled:
                continue

            # Try to match to profile
            profile_value = self.profile.match_field(name)

            if profile_value is not None:
                mappings.append({
                    "ref": ref_id,
                    "label": name,
                    "value": str(profile_value),
                    "confidence": "high",
                    "action": "fill",
                    "role": role,
                })
            else:
                # No match — AI will need to handle this
                mappings.append({
                    "ref": ref_id,
                    "label": name,
                    "value": None,
                    "confidence": "needs_ai",
                    "action": "fill",
                    "role": role,
                })

        # Check for file upload (resume)
        resume_path = self.profile.get_resume_path()
        if resume_path:
            try:
                file_inputs = self.page.locator('input[type="file"]').all()
                for fi in file_inputs:
                    if self._is_visible(fi):
                        mappings.append({
                            "ref": None,
                            "label": "Resume Upload",
                            "value": resume_path,
                            "confidence": "high",
                            "action": "upload",
                            "role": "file_input",
                            "locator": fi,
                        })
                        break
            except Exception:
                pass

        high_count = sum(1 for m in mappings if m["confidence"] == "high")
        ai_count = sum(1 for m in mappings if m["confidence"] == "needs_ai")
        logger.info(
            "Form mapping: %d fields total (%d auto-fill, %d need AI)",
            len(mappings), high_count, ai_count,
        )

        return mappings

    def find_resume_upload(self) -> Optional[Locator]:
        """Find resume/CV file upload input."""
        for selector in RESUME_SELECTORS:
            try:
                el = self.page.locator(selector).first
                if el and self._is_visible(el):
                    logger.info("Resume upload found: %s", selector[:40])
                    return el
            except Exception:
                continue
        return None

    # ============================================================
    #  HELPERS
    # ============================================================

    def _get_domain(self) -> str:
        """Get current page domain."""
        try:
            from urllib.parse import urlparse
            return urlparse(self.page.url).netloc.lower()
        except Exception:
            return ""

    def _is_same_domain(self, href: str, current_domain: str) -> bool:
        """Check if href is on the same domain."""
        if not href or href.startswith("/") or href.startswith("#"):
            return True
        try:
            from urllib.parse import urlparse
            link_domain = urlparse(href).netloc.lower()
            return (
                link_domain == current_domain
                or link_domain.endswith("." + current_domain)
                or current_domain.endswith("." + link_domain)
                or not link_domain  # Relative URL
            )
        except Exception:
            return False

    def _is_visible(self, el: Locator) -> bool:
        """Check if element is visible on page."""
        try:
            return el.is_visible(timeout=1000)
        except Exception:
            return False

    def _safe_text(self, el: Locator) -> str:
        """Get element text safely, truncated."""
        try:
            text = el.inner_text(timeout=1000)
            return text.strip()[:100] if text else ""
        except Exception:
            return ""

    def _is_external_noise(self, href: str, text: str, current_domain: str) -> bool:
        """Check if link is social media or other noise."""
        href_lower = href.lower()
        social_domains = [
            "facebook.com", "twitter.com", "x.com", "linkedin.com",
            "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
        ]
        for sd in social_domains:
            if sd in href_lower:
                return True

        # Skip anchors and javascript links
        if href_lower.startswith("javascript:") or href_lower.startswith("mailto:"):
            return True

        return False

    def _is_never_click(self, text: str) -> bool:
        """Check if text matches a never-click pattern."""
        text_lower = text.lower()
        for pattern in NEVER_CLICK_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False

    def _dedupe_by_href(self, candidates: List[ScoredElement]) -> List[ScoredElement]:
        """Deduplicate candidates by href, keeping highest score."""
        seen = {}
        for c in candidates:
            # Normalize: resolve relative URLs to absolute using current domain
            href = c.href.rstrip("/").lower()
            if href and not href.startswith("http"):
                # Relative URL -- prepend domain for dedup purposes
                domain = self._get_domain()
                if href.startswith("/"):
                    href = f"https://{domain}{href}"
                else:
                    href = f"https://{domain}/{href}"
                href = href.rstrip("/")
            if href not in seen or c.score > seen[href].score:
                seen[href] = c
        return list(seen.values())

    def _dedupe_by_text(self, candidates: List[ScoredElement]) -> List[ScoredElement]:
        """Deduplicate candidates by text, keeping highest score."""
        seen = {}
        for c in candidates:
            text_key = c.text.lower().strip()
            if text_key not in seen or c.score > seen[text_key].score:
                seen[text_key] = c
        return list(seen.values())
