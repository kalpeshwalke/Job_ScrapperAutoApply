"""
Session Memory

Per-application state tracker with explicit retry budgets.
Prevents infinite loops by enforcing hard limits on attempts per action type.

Every action result is recorded. The AI receives this as context so it
knows what was already tried and what failed.
"""

import time
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from src.common.logger import get_logger

logger = get_logger("session_memory")


class FSMState(Enum):
    """Explicit states for the application workflow."""
    NAVIGATE_TO_CAREERS = "navigate_to_careers"
    FIND_JOB = "find_job"
    JOB_DETAIL = "job_detail"
    CLICK_APPLY = "click_apply"
    FILL_FORM = "fill_form"
    SUBMIT = "submit"
    SUCCESS = "success"
    FAILED = "failed"


# Retry budgets: how many times each action type can fail before we give up.
# on_exhaust: what to do when budget is spent.
#   "SKIP_JOB"   → mark job as failed, move to next job
#   "SKIP_FIELD"  → leave field empty, continue with form
#   "ABORT"       → stop entire application
RETRY_BUDGETS: Dict[str, Dict[str, Any]] = {
    "find_careers_link":    {"max": 3, "on_exhaust": "SKIP_JOB"},
    "find_job_listing":     {"max": 3, "on_exhaust": "SKIP_JOB"},
    "click_apply":          {"max": 4, "on_exhaust": "SKIP_JOB"},
    "fill_field":           {"max": 2, "on_exhaust": "SKIP_FIELD"},
    "submit_form":          {"max": 2, "on_exhaust": "SKIP_JOB"},
    "dismiss_popup":        {"max": 3, "on_exhaust": "SKIP_FIELD"},
    "ai_call":              {"max": 5, "on_exhaust": "SKIP_JOB"},
    "total_actions":        {"max": 30, "on_exhaust": "ABORT"},
}


@dataclass
class ActionRecord:
    """Record of a single action taken during application."""
    action_type: str          # "click", "fill", "select", "navigate", etc.
    target_ref: Optional[int] # AX tree ref number if applicable
    target_text: str          # What we clicked/filled (for logging)
    success: bool
    result_type: str          # "navigation", "modal", "form_update", "noop"
    timestamp: float = field(default_factory=time.time)
    error: str = ""


class SessionMemory:
    """
    Tracks all state for a single job application attempt.
    
    Provides:
    - FSM state tracking
    - Action history with deduplication
    - Failed element tracking (penalize refs that produced no-ops)
    - Retry budget enforcement
    - Field completion tracking
    
    Usage:
        session = SessionMemory(company="Gururo", job_title="QA Engineer")
        session.transition_to(FSMState.NAVIGATE_TO_CAREERS)
        
        if session.can_attempt("find_careers_link"):
            # try the action
            session.record_attempt("find_careers_link", success=True)
        else:
            # budget exhausted, handle according to on_exhaust policy
            policy = session.get_exhaust_policy("find_careers_link")
    """

    def __init__(
        self,
        company: str,
        job_title: str,
        career_url: str = "",
        budgets: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.company = company
        self.job_title = job_title
        self.career_url = career_url
        self.start_time = time.time()

        # FSM state
        self.state = FSMState.NAVIGATE_TO_CAREERS
        self.previous_state: Optional[FSMState] = None

        # Action tracking
        self.actions: List[ActionRecord] = []
        self.attempt_counts: Dict[str, int] = {}
        self.total_actions = 0

        # Element tracking
        self.failed_refs: List[int] = []       # AX refs that produced no-ops
        self.clicked_refs: List[int] = []      # AX refs we already clicked

        # Form tracking
        self.fields_filled: Dict[str, str] = {}  # {label: value}
        self.fields_skipped: List[str] = []       # labels we couldn't fill
        self.resume_uploaded = False
        self.apply_clicked = False

        # Page tracking
        self.current_url = career_url
        self.pages_visited: List[str] = []

        # AI call tracking
        self.ai_calls_made = 0

        # Retry budgets (use custom or default)
        self.budgets = budgets or dict(RETRY_BUDGETS)

        logger.info(
            "Session started: %s @ %s (url: %s)",
            job_title, company, career_url[:60]
        )

    def transition_to(self, new_state: FSMState):
        """
        Transition to a new FSM state.
        
        Resets the per-state attempt counter.
        """
        self.previous_state = self.state
        self.state = new_state
        logger.info(
            "FSM: %s -> %s (total actions: %d)",
            self.previous_state.value if self.previous_state else "INIT",
            new_state.value,
            self.total_actions,
        )

    def can_attempt(self, action_type: str) -> bool:
        """
        Check if we still have budget for this action type.
        
        Args:
            action_type: Key in RETRY_BUDGETS (e.g. "find_careers_link")
            
        Returns:
            True if we can still try, False if budget exhausted
        """
        # Check total actions budget
        if self.total_actions >= self.budgets.get("total_actions", {}).get("max", 30):
            logger.warning(
                "Total action budget exhausted (%d/%d)",
                self.total_actions,
                self.budgets["total_actions"]["max"],
            )
            return False

        # Check specific action budget
        budget = self.budgets.get(action_type)
        if budget is None:
            return True  # No budget defined = unlimited

        count = self.attempt_counts.get(action_type, 0)
        if count >= budget["max"]:
            logger.warning(
                "Budget exhausted for '%s': %d/%d (policy: %s)",
                action_type, count, budget["max"], budget["on_exhaust"],
            )
            return False

        return True

    def record_attempt(self, action_type: str, success: bool):
        """
        Record an attempt for budget tracking.
        
        Increments the counter. Resets on success for retriable actions.
        """
        if not success:
            self.attempt_counts[action_type] = self.attempt_counts.get(action_type, 0) + 1
        else:
            # Reset counter on success
            self.attempt_counts[action_type] = 0

        self.total_actions += 1

    def get_exhaust_policy(self, action_type: str) -> str:
        """Get the on_exhaust policy for a given action type."""
        budget = self.budgets.get(action_type, {})
        return budget.get("on_exhaust", "SKIP_JOB")

    def record_action(
        self,
        action_type: str,
        target_ref: Optional[int],
        target_text: str,
        success: bool,
        result_type: str,
        error: str = "",
    ):
        """
        Record a full action with details.
        
        Args:
            action_type: "click", "fill", "select", "navigate", etc.
            target_ref: AX tree ref number
            target_text: Human-readable description
            success: Whether the action succeeded
            result_type: "navigation", "modal", "form_update", "noop"
            error: Error message if failed
        """
        record = ActionRecord(
            action_type=action_type,
            target_ref=target_ref,
            target_text=target_text,
            success=success,
            result_type=result_type,
            error=error,
        )
        self.actions.append(record)
        self.total_actions += 1

        # Track failed refs for penalization
        if not success and result_type == "noop" and target_ref is not None:
            if target_ref not in self.failed_refs:
                self.failed_refs.append(target_ref)
                logger.debug("Penalized ref [%d] (no-op)", target_ref)

        # Track clicked refs
        if target_ref is not None and target_ref not in self.clicked_refs:
            self.clicked_refs.append(target_ref)

        logger.debug(
            "Action recorded: %s [%s] %s → %s%s",
            action_type,
            target_ref or "N/A",
            target_text[:40],
            result_type,
            f" (ERROR: {error[:50]})" if error else "",
        )

    def record_field_filled(self, label: str, value: str):
        """Record a form field as filled."""
        self.fields_filled[label] = value

    def record_field_skipped(self, label: str):
        """Record a form field as skipped (couldn't fill)."""
        if label not in self.fields_skipped:
            self.fields_skipped.append(label)

    def is_field_filled(self, label: str) -> bool:
        """Check if a field was already filled."""
        return label in self.fields_filled

    def is_ref_failed(self, ref: int) -> bool:
        """Check if an AX ref previously produced a no-op."""
        return ref in self.failed_refs

    def is_ref_clicked(self, ref: int) -> bool:
        """Check if an AX ref was already clicked."""
        return ref in self.clicked_refs

    def record_ai_call(self):
        """Track AI call count for budget enforcement."""
        self.ai_calls_made += 1

    def update_url(self, url: str):
        """Update current URL and track navigation."""
        if url != self.current_url:
            self.current_url = url
            if url not in self.pages_visited:
                self.pages_visited.append(url)

    def get_action_summary(self) -> List[str]:
        """
        Get a compact summary of actions taken (for AI context).
        
        Returns last 10 actions as human-readable strings.
        """
        summaries = []
        for action in self.actions[-10:]:
            status = "OK" if action.success else "FAIL"
            summaries.append(
                f"[{status}] {action.action_type} [{action.target_ref or 'N/A'}] "
                f"'{action.target_text[:30]}' -> {action.result_type}"
            )
        return summaries

    def get_context_for_ai(self) -> Dict[str, Any]:
        """
        Get a compact context dict to include in narrow AI calls.
        
        Keeps the AI informed about what has been tried without
        sending the full action history.
        """
        return {
            "company": self.company,
            "job_title": self.job_title,
            "current_state": self.state.value,
            "total_actions": self.total_actions,
            "ai_calls": self.ai_calls_made,
            "fields_filled_count": len(self.fields_filled),
            "resume_uploaded": self.resume_uploaded,
            "apply_clicked": self.apply_clicked,
            "failed_refs": self.failed_refs[-5:],  # Last 5 only
            "recent_actions": self.get_action_summary()[-5:],  # Last 5 only
        }

    def get_elapsed_seconds(self) -> float:
        """Get elapsed time since session start."""
        return time.time() - self.start_time

    def get_final_report(self) -> Dict[str, Any]:
        """
        Generate final report for logging/Excel tracking.
        """
        return {
            "company": self.company,
            "job_title": self.job_title,
            "career_url": self.career_url,
            "final_state": self.state.value,
            "success": self.state == FSMState.SUCCESS,
            "total_actions": self.total_actions,
            "ai_calls": self.ai_calls_made,
            "fields_filled": len(self.fields_filled),
            "fields_skipped": len(self.fields_skipped),
            "resume_uploaded": self.resume_uploaded,
            "elapsed_seconds": round(self.get_elapsed_seconds(), 1),
            "pages_visited": len(self.pages_visited),
            "failed_refs_count": len(self.failed_refs),
        }

    def __repr__(self) -> str:
        return (
            f"Session({self.company}/{self.job_title}, "
            f"state={self.state.value}, "
            f"actions={self.total_actions}, "
            f"ai_calls={self.ai_calls_made})"
        )
