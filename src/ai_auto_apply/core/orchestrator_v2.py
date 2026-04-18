"""
FSM Orchestrator v2 — Deterministic State Machine + Narrow AI

Replaces the old Planner->BrowserAgent dual-LLM loop with:
    Rule Engine -> (Narrow AI if ambiguous) -> DOMToolkit -> Observer -> Memory

The LLM is no longer called every iteration. It is called only when
the rule engine encounters ambiguity (multiple candidates, unknown fields).

Typical LLM calls per application: 4-8 (vs 20-40 in v1)
"""

import os
import re
import time
from typing import Dict, Any, Optional, List
from src.common.logger import get_logger
from src.ai_auto_apply.tools.dom_tools import DOMToolkit
from src.ai_auto_apply.core.anti_spam_tracker import AntiSpamTracker
from src.ai_auto_apply.core.structured_logger import StructuredLogger
from src.ai_auto_apply.core.career_page_validator import CareerPageValidator
from src.ai_auto_apply.core.mcp_client import MCPClient
from src.ai_auto_apply.core.profile_store import ProfileStore
from src.ai_auto_apply.core.rule_engine import RuleEngine
from src.ai_auto_apply.core.session_memory import SessionMemory, FSMState
from src.ai_auto_apply.core.observer import ActionObserver, ResultType
from src.ai_auto_apply.agents.narrow_ai import NarrowAI
from src.ai_auto_apply.agents.browser_agent import BrowserAgent
from playwright.sync_api import sync_playwright

logger = get_logger("fsm_orchestrator_v2")

# Minimum relevance score for a job to be worth applying to.
# Jobs scoring below this are skipped.
MIN_RELEVANCE_SCORE = 0.3


class FSMOrchestratorV2:
    """
    Deterministic FSM orchestrator for AI auto-apply.

    States:
        NAVIGATE_TO_CAREERS -> FIND_JOB -> CLICK_APPLY
        -> FILL_FORM -> SUBMIT -> SUCCESS / FAILED

    Each state transition:
        1. Rule engine attempts action (selectors, field map)
        2. If high confidence -> execute via DOMToolkit
        3. If ambiguous -> narrow AI call for disambiguation
        4. Observer checks result
        5. Session memory updated, budget checked
    """

    def __init__(self, provider, config: Dict[str, Any], excel_path: str):
        """
        Initialize FSM orchestrator v2.

        Args:
            provider: AIProvider instance
            config: auto_apply configuration dictionary
            excel_path: Path to master Excel file
        """
        self.provider = provider
        self.config = config
        self.page_load_timeout = config.get("fsm", {}).get("page_load_timeout", 30)

        # Load profile
        profile_path = config.get("profile_path", "config/profile.json")
        self.profile = ProfileStore(profile_path)

        # Initialize narrow AI with profile context
        self.narrow_ai = NarrowAI(provider, profile_data=self.profile.data)

        # Initialize MCP client (optional)
        self.mcp_client = self._initialize_mcp_client()

        # Initialize browser agent (simplified -- screenshots + network only)
        self.browser_agent = BrowserAgent(provider, config, mcp_client=self.mcp_client)

        # Initialize tracker
        self.tracker = AntiSpamTracker(excel_path)

        # Initialize career page validator
        self.validator = CareerPageValidator(config.get("validation", {}))

        # Initialize structured logger
        self.structured_logger = StructuredLogger("orchestrator_v2", config.get("logging", {}))

        # Initialize observer
        self.observer = ActionObserver(settle_ms=800)

        # Persistent browser session (reused across jobs)
        self.page = None
        self.playwright_instance = None
        self.browser_instance = None

        # Run screenshot cleanup
        self._cleanup_old_screenshots()

        logger.info("FSMOrchestratorV2 initialized (profile: %s)", self.profile)

    # ================================================================
    #  MAIN ENTRY POINT
    # ================================================================

    def apply_to_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply to a single job using the deterministic FSM.

        Args:
            job_data: {title, company, career_url, excel_index, user_details, ...}

        Returns:
            {status: "success"|"failed"|"skipped", reason: str, ...}
        """
        career_url = job_data["career_url"]
        excel_index = job_data["excel_index"]

        logger.info(
            "=== Starting application: %s at %s ===",
            job_data["title"], job_data["company"],
        )

        # STEP 1: Validate career URL
        validation_status, validation_reason = self.validator.validate(
            url=career_url, company_name=job_data["company"]
        )
        # Accept "Yes" and "Unchecked" (disabled validation); reject "No"
        is_homepage_redirect = getattr(self.validator, '_last_homepage_redirect', False)
        # Also detect from reason string as fallback for backward compat
        if not is_homepage_redirect:
            is_homepage_redirect = "homepage redirect" in validation_reason.lower()

        if validation_status == "No":
            return self._fail(
                job_data, excel_index,
                f"Invalid career page: {validation_reason}",
                failure_type="validation_failure",
            )

        # STEP 1.5: Score job relevance before investing browser time
        relevance = self.narrow_ai.score_job_relevance(
            job_title=job_data.get("title", ""),
            job_snippet=job_data.get("description", "")[:200],
        )
        if relevance < MIN_RELEVANCE_SCORE:
            logger.info(
                "Job relevance %.2f below threshold %.2f, skipping",
                relevance, MIN_RELEVANCE_SCORE,
            )
            return self._fail(
                job_data, excel_index,
                f"Low job relevance ({relevance:.2f})",
                failure_type="low_relevance",
            )

        # Initialize session memory
        session = SessionMemory(
            company=job_data["company"],
            job_title=job_data["title"],
            career_url=career_url,
        )

        try:
            # STEP 2: Launch browser (or reuse persistent session)
            self._ensure_browser_page(career_url)

            # STEP 3: Detect blockers FIRST (before popup dismissal)
            blockers = self.observer.detect_blockers(self.page)
            if blockers.get("captcha"):
                return self._fail(
                    job_data, excel_index,
                    "CAPTCHA block detected",
                    failure_type="captcha_block",
                    session=session,
                )
            if blockers.get("login_wall"):
                return self._fail(
                    job_data, excel_index,
                    "Login/authentication wall",
                    failure_type="login_wall",
                    session=session,
                )

            # STEP 3.5: Close popups AFTER blocker detection
            self._close_popups_deterministic()

            # Initialize DOM toolkit
            dom = DOMToolkit(self.page)
            rule_engine = RuleEngine(self.page, self.profile)

            # STEP 4: Handle homepage redirect -> navigate to careers
            if is_homepage_redirect:
                session.transition_to(FSMState.NAVIGATE_TO_CAREERS)
                nav_success = self._state_navigate_to_careers(
                    dom, rule_engine, session, job_data
                )
                if not nav_success:
                    return self._fail(
                        job_data, excel_index,
                        "Cannot navigate to careers page",
                        failure_type="homepage_navigation_failure",
                        session=session,
                    )

            # STEP 5: Find the specific job if on a job listing page
            session.transition_to(FSMState.FIND_JOB)
            self._state_find_job(dom, rule_engine, session, job_data)
            # find_job is best-effort: if the page already has an Apply
            # button visible, we skip directly to CLICK_APPLY

            # STEP 6: Find and click Apply button
            session.transition_to(FSMState.CLICK_APPLY)
            apply_success = self._state_click_apply(dom, rule_engine, session)
            if not apply_success:
                return self._fail(
                    job_data, excel_index,
                    "Cannot find or click Apply button",
                    failure_type="apply_button_failure",
                    session=session,
                )

            # STEP 7: Fill application form
            session.transition_to(FSMState.FILL_FORM)
            fill_success = self._state_fill_form(
                dom, rule_engine, session, job_data
            )
            # fill_success can be partial -- we continue even if some fields skipped

            # STEP 8: Submit
            session.transition_to(FSMState.SUBMIT)
            submit_success = self._state_submit(dom, rule_engine, session)

            if submit_success:
                session.transition_to(FSMState.SUCCESS)
                return self._succeed(job_data, excel_index, session)
            else:
                return self._fail(
                    job_data, excel_index,
                    "Cannot submit application form",
                    failure_type="submit_failure",
                    session=session,
                )

        except Exception as e:
            logger.error("FSM error: %s", e, exc_info=True)
            self._capture_screenshot("exception", job_data)
            return self._fail(
                job_data, excel_index,
                f"Exception: {str(e)[:100]}",
                failure_type="exception",
                session=session,
            )
        finally:
            # Close the tab, not the entire browser
            self._close_page()

    # ================================================================
    #  FSM STATE: Navigate to Careers
    # ================================================================

    def _state_navigate_to_careers(
        self,
        dom: DOMToolkit,
        rule_engine: RuleEngine,
        session: SessionMemory,
        job_data: Dict[str, Any],
    ) -> bool:
        """
        Navigate from homepage to careers page.

        Strategy:
        1. Rule engine tries selector chains (no AI)
        2. If ambiguous -> narrow AI disambiguates
        3. Observer verifies navigation worked
        """
        for attempt in range(3):
            if not session.can_attempt("find_careers_link"):
                return False

            logger.info("Navigate to careers: attempt %d/3", attempt + 1)

            # Close any popups first
            self._close_popups_deterministic()

            # Rule engine tries first
            result = rule_engine.find_careers_link(
                failed_refs=session.failed_refs
            )

            if result["confidence"] == "none":
                # Try AX tree + narrow AI as fallback
                ax_snapshot = dom.get_accessibility_snapshot(depth=4)
                if ax_snapshot:
                    candidates = self._ax_links_to_candidates(ax_snapshot, dom)
                    if candidates:
                        ai_result = self.narrow_ai.disambiguate_link(
                            candidates=candidates,
                            goal="careers/jobs page",
                            company=job_data.get("company", ""),
                        )
                        session.record_ai_call()
                        if ai_result and ai_result.get("index") is not None:
                            idx = ai_result["index"]
                            if idx < len(candidates):
                                ref = candidates[idx].get("ref")
                                if ref:
                                    before = self.observer.snapshot(self.page)
                                    try:
                                        dom.click_by_ref(ref)
                                        time.sleep(2)
                                    except Exception as e:
                                        logger.warning("Click failed: %s", e)
                                        session.record_attempt("find_careers_link", False)
                                        continue
                                    obs = self.observer.observe(self.page, before, ref)
                                    if obs.result_type != ResultType.NOOP:
                                        session.update_url(self.page.url)
                                        if self._verify_careers_page():
                                            session.record_attempt("find_careers_link", True)
                                            return True

                session.record_attempt("find_careers_link", False)
                continue

            if result["confidence"] == "high":
                # Confident match -- click directly
                locator = result["locator"]
                before = self.observer.snapshot(self.page)
                try:
                    locator.scroll_into_view_if_needed()
                    locator.click(timeout=5000)
                    time.sleep(2)
                except Exception as e:
                    logger.warning("Careers link click failed: %s", e)
                    session.record_attempt("find_careers_link", False)
                    continue

                obs = self.observer.observe(self.page, before)
                if obs.result_type != ResultType.NOOP:
                    session.update_url(self.page.url)
                    if self._verify_careers_page():
                        session.record_attempt("find_careers_link", True)
                        return True

                session.record_attempt("find_careers_link", False)

            elif result["confidence"] == "ambiguous":
                # Multiple candidates -- ask narrow AI
                candidates = [
                    {"text": c.text, "href": c.href, "score": c.score}
                    for c in result["candidates"]
                ]
                ai_result = self.narrow_ai.disambiguate_link(
                    candidates=candidates,
                    goal="careers/jobs page",
                    company=job_data.get("company", ""),
                )
                session.record_ai_call()

                if ai_result and ai_result.get("index") is not None:
                    idx = ai_result["index"]
                    if idx < len(result["candidates"]):
                        chosen = result["candidates"][idx]
                        before = self.observer.snapshot(self.page)
                        try:
                            chosen.locator.scroll_into_view_if_needed()
                            chosen.locator.click(timeout=5000)
                            time.sleep(2)
                        except Exception as e:
                            logger.warning("AI-chosen link click failed: %s", e)
                            session.record_attempt("find_careers_link", False)
                            continue

                        obs = self.observer.observe(self.page, before)
                        if obs.result_type != ResultType.NOOP:
                            session.update_url(self.page.url)
                            if self._verify_careers_page():
                                session.record_attempt("find_careers_link", True)
                                return True

                session.record_attempt("find_careers_link", False)

        return False

    # ================================================================
    #  FSM STATE: Find Job (on listing pages)
    # ================================================================

    def _state_find_job(
        self,
        dom: DOMToolkit,
        rule_engine: RuleEngine,
        session: SessionMemory,
        job_data: Dict[str, Any],
    ) -> bool:
        """
        On a job listings page, find and click into the specific job.

        If we can already see an Apply button, skip this state.

        Strategy: Scan ALL links once, score each by word overlap with
        the job title, click the single best match. No per-word loop.
        """
        # Quick check: if Apply is already visible, we're on a detail page
        apply_check = rule_engine.find_apply_button(failed_refs=session.failed_refs)
        if apply_check["confidence"] != "none":
            logger.info("Apply button already visible, skipping FIND_JOB state")
            return True

        job_title = job_data.get("title", "").lower().strip()
        if not job_title:
            logger.info("No job title provided, skipping FIND_JOB state")
            return True

        logger.info("Looking for job listing: '%s'", job_title[:50])

        words = [w for w in job_title.split() if len(w) > 2][:4]
        if not words:
            return True

        # Single pass: scan all links, find best match
        best_link = None
        best_match_count = 0

        try:
            all_links = self.page.locator("a").all()
            for link in all_links:
                try:
                    link_text = link.inner_text(timeout=500).lower().strip()
                except Exception:
                    continue

                if not link_text or len(link_text) < 3:
                    continue

                try:
                    if not link.is_visible(timeout=300):
                        continue
                except Exception:
                    continue

                matching_words = sum(1 for w in words if w in link_text)
                if matching_words > best_match_count:
                    best_match_count = matching_words
                    best_link = link

            # Require at least 2 words to match (or all if only 1-2 words)
            min_required = min(2, len(words))

            if best_link and best_match_count >= min_required:
                logger.info(
                    "Best job link match: %d/%d words",
                    best_match_count, len(words),
                )
                before = self.observer.snapshot(self.page)
                try:
                    best_link.scroll_into_view_if_needed()
                    best_link.click(timeout=5000)
                    time.sleep(2)
                except Exception as e:
                    logger.warning("Job link click failed: %s", e)
                    return True  # Best-effort, proceed anyway

                obs = self.observer.observe(self.page, before)
                if obs.result_type != ResultType.NOOP:
                    session.update_url(self.page.url)
                    logger.info("Navigated to job detail page")
                    return True

        except Exception as e:
            logger.warning("FIND_JOB state error: %s", e)

        logger.info("Could not find specific job listing, proceeding with current page")
        return True  # Best-effort; proceed to CLICK_APPLY anyway

    # ================================================================
    #  FSM STATE: Click Apply
    # ================================================================

    def _state_click_apply(
        self,
        dom: DOMToolkit,
        rule_engine: RuleEngine,
        session: SessionMemory,
    ) -> bool:
        """Find and click the Apply button."""
        for attempt in range(4):
            if not session.can_attempt("click_apply"):
                return False

            logger.info("Click Apply: attempt %d/4", attempt + 1)

            # Refresh AX tree and re-inject mmids
            dom.inject_mmids()
            self._close_popups_deterministic()

            result = rule_engine.find_apply_button(
                failed_refs=session.failed_refs
            )

            target_locator = None

            if result["confidence"] == "high":
                target_locator = result["locator"]

            elif result["confidence"] == "ambiguous":
                candidates = [
                    {"text": c.text, "ref": i}
                    for i, c in enumerate(result["candidates"])
                ]
                ai_result = self.narrow_ai.disambiguate_button(
                    candidates=candidates,
                    goal="apply for the job",
                )
                session.record_ai_call()

                if ai_result and ai_result.get("index") is not None:
                    idx = ai_result["index"]
                    if idx < len(result["candidates"]):
                        target_locator = result["candidates"][idx].locator

            if target_locator is None:
                session.record_attempt("click_apply", False)
                time.sleep(1)
                continue

            # Execute click
            before = self.observer.snapshot(self.page)
            try:
                target_locator.scroll_into_view_if_needed()
                target_locator.click(timeout=5000)
                time.sleep(2)
            except Exception as e:
                logger.warning("Apply button click failed: %s", e)
                session.record_attempt("click_apply", False)
                continue

            obs = self.observer.observe(self.page, before)
            if obs.result_type != ResultType.NOOP:
                session.apply_clicked = True
                session.update_url(self.page.url)
                session.record_attempt("click_apply", True)
                logger.info("Apply button clicked successfully")
                return True

            session.record_attempt("click_apply", False)

        return False

    # ================================================================
    #  FSM STATE: Fill Form  (FIXED multi-page loop)
    # ================================================================

    def _state_fill_form(
        self,
        dom: DOMToolkit,
        rule_engine: RuleEngine,
        session: SessionMemory,
        job_data: Dict[str, Any],
    ) -> bool:
        """
        Fill application form fields.

        Uses profile store for standard fields, narrow AI for unknowns.
        Routes textarea (free-text) questions to answer_free_text().
        Handles multi-page forms by detecting "Next"/"Continue" buttons.
        """
        max_form_pages = 5  # Support up to 5 pages of form
        page_num = 0

        while page_num < max_form_pages:
            page_num += 1
            logger.info("Form page %d/%d", page_num, max_form_pages)

            # Refresh AX tree
            dom.inject_mmids()
            dom.get_accessibility_snapshot(depth=7)

            # Map fields to profile values
            field_mappings = rule_engine.map_form_fields(
                dom_toolkit=dom,
                already_filled=session.fields_filled,
            )

            if not field_mappings:
                logger.info("No form fields found on this page")
                break

            # Fill each field
            for field_map in field_mappings:
                ref = field_map.get("ref")
                label = field_map.get("label", "")
                value = field_map.get("value")
                confidence = field_map.get("confidence")
                action = field_map.get("action")
                role = field_map.get("role", "")

                if session.is_field_filled(label):
                    continue

                # ---- Resume upload ----
                if action == "upload" and field_map.get("locator"):
                    try:
                        field_map["locator"].set_input_files(value, timeout=5000)
                        session.resume_uploaded = True
                        session.record_field_filled(label, value)
                        logger.info("Resume uploaded: %s", value)
                        _fname = str(value).split('/')[-1] if '/' in str(value) else str(value).split('\\')[-1]
                        print(f"   📄 [Upload] Attached resume: {_fname}")
                    except Exception as e:
                        logger.warning("Resume upload failed: %s", e)
                        print(f"   ❌ [Upload Error] Failed to attach resume")
                    continue

                # ---- High-confidence deterministic fill ----
                if confidence == "high" and value and ref:
                    try:
                        dom.fill_by_ref(ref, value)
                        session.record_field_filled(label, value)
                        logger.info("Filled [%d] '%s' = '%s'", ref, label[:30], str(value)[:30])
                        print(f"   ▶️ [Fill] {label[:40]} = '{str(value)[:40]}'")
                    except Exception as e:
                        logger.warning("Fill failed [%d] '%s': %s", ref, label[:30], e)
                        print(f"   ❌ [Fill Error] Failed on '{label[:40]}'")
                        session.record_field_skipped(label)

                # ---- Needs AI ----
                elif confidence == "needs_ai" and ref:
                    if not session.can_attempt("ai_call"):
                        session.record_field_skipped(label)
                        continue

                    # Route textareas / long-form fields to answer_free_text
                    if role in ("textarea",) or self._is_free_text_question(label):
                        ai_answer = self.narrow_ai.answer_free_text(
                            question=label,
                            company=job_data.get("company", ""),
                            job_title=job_data.get("title", ""),
                        )
                        session.record_ai_call()
                        if ai_answer:
                            try:
                                dom.fill_by_ref(ref, ai_answer)
                                session.record_field_filled(label, ai_answer)
                                logger.info(
                                    "AI free-text [%d] '%s' -> '%s'",
                                    ref, label[:30], ai_answer[:30],
                                )
                                print(f"   🤖 [AI Generate] {label[:40]} = '{str(ai_answer)[:40]}...'")
                            except Exception as e:
                                logger.warning("AI free-text fill failed: %s", e)
                                print(f"   ❌ [AI Generate Error] Failed on '{label[:40]}'")
                                session.record_field_skipped(label)
                        else:
                            session.record_field_skipped(label)
                    else:
                        # Standard unknown field
                        ai_answer = self.narrow_ai.answer_unknown_field(
                            field_label=label,
                            field_type=role,
                            company=job_data.get("company", ""),
                            job_title=job_data.get("title", ""),
                        )
                        session.record_ai_call()

                        if ai_answer and ai_answer.get("action") != "skip":
                            fill_value = ai_answer.get("value", "")
                            if fill_value:
                                try:
                                    dom.fill_by_ref(ref, fill_value)
                                    session.record_field_filled(label, fill_value)
                                    logger.info(
                                        "AI filled [%d] '%s' = '%s'",
                                        ref, label[:30], fill_value[:30],
                                    )
                                    print(f"   🤖 [AI Suggest] {label[:40]} = '{str(fill_value)[:40]}'")
                                except Exception as e:
                                    logger.warning("AI fill failed: %s", e)
                                    print(f"   ❌ [AI Suggest Error] Failed on '{label[:40]}'")
                                    session.record_field_skipped(label)
                            else:
                                session.record_field_skipped(label)
                        else:
                            session.record_field_skipped(label)
                else:
                    session.record_field_skipped(label)

            # Check for Next/Continue button (multi-page form)
            found_next = False
            next_result = rule_engine.find_submit_button()
            if next_result["confidence"] != "none":
                locator = next_result.get("locator")
                if not locator and next_result["candidates"]:
                    locator = next_result["candidates"][0].locator

                if locator:
                    text = ""
                    try:
                        text = locator.inner_text(timeout=1000).lower().strip()
                    except Exception:
                        pass

                    # If it's "Next"/"Continue" (not final Submit), click and loop
                    if text in {"next", "continue", "proceed", "save & continue", "save and continue"}:
                        before = self.observer.snapshot(self.page)
                        try:
                            locator.click(timeout=5000)
                            time.sleep(2)
                        except Exception as e:
                            logger.warning("Next button click failed: %s", e)
                            break  # Can't advance, stop

                        obs = self.observer.observe(self.page, before)
                        if obs.result_type != ResultType.NOOP:
                            logger.info("Moved to next form page")
                            print("   ⏭️ [Navigation] Clicked Next/Continue to open next form page")
                            found_next = True
                        # else: click was a noop, stop
                    # else: this is the final Submit button, stop looping

            if not found_next:
                break  # Either no Next button, or it's the final Submit

        fields_total = len(session.fields_filled) + len(session.fields_skipped)
        logger.info(
            "Form fill complete: %d filled, %d skipped (of %d total)",
            len(session.fields_filled), len(session.fields_skipped), fields_total,
        )
        return True

    # ================================================================
    #  FSM STATE: Submit  (FIXED false-positive verification)
    # ================================================================

    def _state_submit(
        self,
        dom: DOMToolkit,
        rule_engine: RuleEngine,
        session: SessionMemory,
    ) -> bool:
        """Find and click the submit button. Verify actual success."""
        for attempt in range(2):
            if not session.can_attempt("submit_form"):
                return False

            logger.info("Submit: attempt %d/2", attempt + 1)
            dom.inject_mmids()

            result = rule_engine.find_submit_button()

            locator = None
            if result["confidence"] == "high":
                locator = result["locator"]
            elif result["candidates"]:
                locator = result["candidates"][0].locator

            if locator is None:
                session.record_attempt("submit_form", False)
                continue

            before = self.observer.snapshot(self.page)
            try:
                locator.scroll_into_view_if_needed()
                locator.click(timeout=5000)
                time.sleep(3)
            except Exception as e:
                logger.warning("Submit click failed: %s", e)
                session.record_attempt("submit_form", False)
                continue

            obs = self.observer.observe(self.page, before)

            # Check for form submission via network
            submission = self.browser_agent.detect_form_submission()
            if submission and submission.get("success"):
                logger.info("Form submission confirmed via network (POST %d)", submission["status_code"])
                session.record_attempt("submit_form", True)
                return True

            # URL change or content change after submit
            if obs.result_type in {ResultType.NAVIGATION, ResultType.CONTENT_CHANGE}:
                # MUST verify the new page contains success indicators
                try:
                    page_text = self.page.inner_text("body").lower()
                    success_indicators = [
                        "thank you", "application submitted", "successfully",
                        "received your application", "application complete",
                        "we will review", "been submitted",
                    ]
                    failure_indicators = [
                        "error", "failed", "invalid", "required field",
                        "please correct", "you already applied", "login",
                        "sign in", "create account",
                    ]

                    has_success = any(ind in page_text for ind in success_indicators)
                    has_failure = any(ind in page_text for ind in failure_indicators)

                    if has_success and not has_failure:
                        logger.info("Submission success confirmed via page content")
                        session.record_attempt("submit_form", True)
                        return True
                    elif has_failure:
                        logger.warning("Submission failure detected via page content")
                        session.record_attempt("submit_form", False)
                        continue
                    else:
                        # Navigation happened but no clear signal either way.
                        # Do NOT blindly treat as success.
                        logger.warning(
                            "Submit caused navigation but no success/failure indicators found. "
                            "Treating as uncertain failure."
                        )
                        session.record_attempt("submit_form", False)
                        continue

                except Exception:
                    pass

            session.record_attempt("submit_form", False)

        return False

    # ================================================================
    #  HELPERS
    # ================================================================

    def _ensure_browser_page(self, url: str):
        """
        Navigate to URL using persistent browser session.
        Reuses the Playwright browser instance across jobs (new tab per job).
        """
        # Launch browser if not yet started
        if self.playwright_instance is None:
            self.playwright_instance = sync_playwright().start()
            headless = self.config.get("browser", {}).get("headless", False)
            self.browser_instance = self.playwright_instance.chromium.launch(headless=headless)
            logger.info("Persistent browser launched (headless=%s)", headless)

        # Open a new page (tab) for this job
        self.page = self.browser_instance.new_page()
        self.page.set_default_timeout(self.page_load_timeout * 1000)

        # Wire up browser agent for screenshots/network
        self.browser_agent.set_page(self.page)

        logger.info("Browser launched, navigating to %s", url[:80])
        self.page.goto(url, wait_until="domcontentloaded")

        wait_sec = self.config.get("browser", {}).get("page_load_wait_seconds", 5)
        time.sleep(wait_sec)

    def _close_page(self):
        """Close the current page/tab, keep the browser running."""
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None

    def close_browser(self):
        """Fully close the persistent browser session. Call when done with all jobs."""
        self._close_page()
        if self.browser_instance:
            try:
                self.browser_instance.close()
            except Exception:
                pass
            self.browser_instance = None
        if self.playwright_instance:
            try:
                self.playwright_instance.stop()
            except Exception:
                pass
            self.playwright_instance = None
        logger.info("Persistent browser session closed")

    def _close_popups_deterministic(self):
        """Close cookie/popup overlays using deterministic selectors first."""
        popup_selectors = [
            'button:text-matches("accept all|accept cookies|got it|allow all", "i")',
            'button:text-matches("reject all|decline|deny", "i")',
            'button:text-matches("close|dismiss|no thanks", "i")',
            '[id*="cookie"] button',
            '[class*="cookie"] button',
            '[id*="consent"] button',
        ]
        for selector in popup_selectors:
            try:
                el = self.page.locator(selector).first
                if el and el.is_visible(timeout=500):
                    el.click(timeout=2000)
                    time.sleep(0.5)
                    logger.info("Popup dismissed: %s", selector[:40])
                    return
            except Exception:
                continue

    def _verify_careers_page(self) -> bool:
        """Check if current page is a careers/jobs page."""
        try:
            url = self.page.url.lower()
            if any(kw in url for kw in ["career", "job", "opening", "position"]):
                return True
            body = self.page.inner_text("body").lower()[:3000]
            indicators = ["job", "position", "career", "apply", "opening", "opportunity"]
            return sum(1 for kw in indicators if kw in body) >= 3
        except Exception:
            return False

    def _is_free_text_question(self, label: str) -> bool:
        """Detect if a field label is a free-text question (not a simple input)."""
        label_lower = label.lower().strip()
        # Questions typically contain question words or end with ?
        question_patterns = [
            r"\bwhy\b", r"\bhow\b", r"\bwhat\b", r"\bdescribe\b",
            r"\bexplain\b", r"\btell us\b", r"\bcover letter\b",
            r"\bmotivation\b", r"\?$",
        ]
        return any(re.search(p, label_lower) for p in question_patterns)

    def _ax_links_to_candidates(
        self, ax_snapshot: str, dom: DOMToolkit
    ) -> List[Dict[str, Any]]:
        """Extract link candidates from AX tree for narrow AI."""
        candidates = []
        for match in re.finditer(r'\[(\d+)\]\s+link\s+"([^"]+)"', ax_snapshot):
            ref = int(match.group(1))
            text = match.group(2)
            candidates.append({"ref": ref, "text": text, "href": ""})
        return candidates[:10]

    def _capture_screenshot(self, reason: str, job_data: Dict[str, Any]):
        """Capture debug screenshot."""
        try:
            job_id = f"{job_data['company']}_{job_data['title']}".replace(" ", "_")[:50]
            self.browser_agent.capture_screenshot(reason, job_id)
        except Exception:
            pass

    def _succeed(
        self,
        job_data: Dict[str, Any],
        excel_index: int,
        session: SessionMemory,
    ) -> Dict[str, Any]:
        """Log and return success result."""
        report = session.get_final_report()

        self.tracker.mark_applied(
            excel_index=excel_index,
            status="success",
            notes=f"Applied via FSMv2. AI calls: {report['ai_calls']}, Fields: {report['fields_filled']}",
        )

        self.structured_logger.log_application_result(
            job_title=job_data["title"],
            company=job_data["company"],
            status="success",
            reason="Application submitted successfully",
            metrics=report,
        )

        logger.info(
            "=== SUCCESS: %s at %s (actions: %d, AI: %d, time: %.0fs) ===",
            job_data["title"], job_data["company"],
            report["total_actions"], report["ai_calls"], report["elapsed_seconds"],
        )

        return {
            "status": "success",
            "reason": "Application submitted",
            "iterations": report["total_actions"],
            "actions_taken": session.get_action_summary(),
            **report,
        }

    def _fail(
        self,
        job_data: Dict[str, Any],
        excel_index: int,
        reason: str,
        failure_type: str = "unknown",
        session: Optional[SessionMemory] = None,
    ) -> Dict[str, Any]:
        """Log and return failure result."""
        report = session.get_final_report() if session else {}

        self.tracker.mark_failed(
            excel_index=excel_index,
            reason=reason[:200],
        )

        self.structured_logger.log_application_result(
            job_title=job_data["title"],
            company=job_data["company"],
            status="failed",
            reason=reason,
            metrics={
                "failure_type": failure_type,
                "career_url": job_data.get("career_url", ""),
                **report,
            },
        )

        logger.warning(
            "=== FAILED: %s at %s (%s) ===",
            job_data["title"], job_data["company"], reason[:80],
        )

        return {
            "status": "failed",
            "reason": reason,
            "iterations": report.get("total_actions", 0),
            "actions_taken": session.get_action_summary() if session else [],
            **report,
        }

    # ================================================================
    #  INFRASTRUCTURE (preserved from v1)
    # ================================================================

    def _initialize_mcp_client(self) -> Optional[MCPClient]:
        """Initialize MCP client from configuration."""
        mcp_config = self.config.get("mcp", {})
        if not mcp_config.get("enabled", False):
            return None
        is_valid, error = MCPClient.validate_config(mcp_config)
        if not is_valid:
            logger.error("MCP validation failed: %s", error)
            return None
        try:
            client = MCPClient(mcp_config)
            if client.connect():
                logger.info("MCP client connected")
                return client
        except Exception as e:
            logger.error("MCP init failed: %s", e)
        return None

    def _cleanup_old_screenshots(self):
        """Delete screenshots older than retention period."""
        try:
            screenshot_config = self.config.get("screenshots", {})
            retention_days = screenshot_config.get("retention_days", 30)
            screenshot_dir = screenshot_config.get("directory", "logs/screenshots")
            if not os.path.exists(screenshot_dir):
                return
            cutoff = time.time() - (retention_days * 86400)
            deleted = 0
            for root, dirs, files in os.walk(screenshot_dir):
                for f in files:
                    if f.endswith(".png"):
                        path = os.path.join(root, f)
                        if os.path.getmtime(path) < cutoff:
                            os.remove(path)
                            deleted += 1
            if deleted:
                logger.info("Screenshot cleanup: deleted %d old files", deleted)
        except Exception as e:
            logger.error("Screenshot cleanup failed: %s", e)
