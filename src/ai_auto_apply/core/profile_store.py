"""
Profile Store

Single source of truth for all candidate data used in form filling.
Loads structured profile from config/profile.json and provides
field lookup with regex-based label matching.

Zero AI calls for standard fields.
"""

import json
import re
import os
from typing import Dict, Any, Optional, List
from src.common.logger import get_logger

logger = get_logger("profile_store")


# Regex patterns mapping form field labels -> profile JSON paths
# Order matters: more specific patterns first
# Combined patterns MUST come before individual patterns
FIELD_PATTERNS = [
    # Name fields
    (r"full\s*name|your\s*name|candidate\s*name|applicant\s*name", "personal.full_name"),
    (r"first\s*name|given\s*name|fname", "personal.first_name"),
    (r"last\s*name|surname|family\s*name|lname", "personal.last_name"),

    # Contact
    (r"e[\-\s]?mail|email\s*address", "personal.email"),
    (r"phone|mobile|cell|contact\s*number|telephone", "personal.phone"),

    # Location — combined pattern BEFORE individual city/state
    (r"\bcity[,\s/]+state\b", "personal.location"),
    (r"\bcity\b", "personal.city"),
    (r"\bstate\b|\bprovince\b", "personal.state"),
    (r"\bcountry\b", "personal.country"),
    (r"pin\s*code|zip\s*code|postal\s*code", "personal.pincode"),
    (r"\blocation\b|\baddress\b|current\s*location", "personal.location"),

    # Links
    (r"linkedin", "personal.linkedin"),
    (r"portfolio|website|personal\s*site", "personal.portfolio"),
    (r"github|git\s*hub", "personal.github"),

    # Professional
    (r"current\s*title|job\s*title|designation|current\s*role", "professional.current_title"),
    (r"years?\s*(of)?\s*experience|total\s*experience|experience\s*\(years?\)", "professional.years_experience"),
    (r"current\s*(company|employer|organization)", "professional.current_company"),
    (r"current\s*(ctc|salary|compensation|package)", "professional.current_ctc"),
    (r"expected\s*(ctc|salary|compensation|package)", "professional.expected_ctc"),
    (r"notice\s*period|notice|serving\s*notice", "professional.notice_period"),
    (r"work\s*auth|visa|legally\s*auth|right\s*to\s*work|citizenship", "professional.work_authorization"),
    (r"relocat", "default_answers.willing_to_relocate"),
    (r"education|degree|qualification|highest\s*education", "professional.highest_education"),
    (r"university|college|institution|school", "professional.university"),
    (r"graduation|passing\s*year|year\s*of\s*completion", "professional.graduation_year"),

    # EEO / Demographics
    (r"gender|sex", "eeo_responses.gender"),
    (r"race|ethnicity|ethnic", "eeo_responses.race_ethnicity"),
    (r"veteran|military", "eeo_responses.veteran_status"),
    (r"disabilit", "eeo_responses.disability_status"),

    # Common application questions
    (r"sponsorship|visa\s*sponsor", "default_answers.sponsorship_required"),
    (r"legally\s*authorized|authorized\s*to\s*work", "default_answers.legally_authorized"),
    (r"start\s*date|available\s*from|join(ing)?\s*date|earliest\s*(start|join)", "default_answers.available_start_date"),
    (r"reason\s*(for)?\s*(change|leaving|looking)", "default_answers.reason_for_change"),
    (r"cover\s*letter", "default_answers.cover_letter_template"),
]


class ProfileStore:
    """
    Loads and serves candidate profile data for form filling.

    Usage:
        store = ProfileStore("config/profile.json")
        email = store.get("personal.email")           # Direct key lookup
        value = store.match_field("Your Email Address") # Regex label matching
    """

    def __init__(self, profile_path: str = "config/profile.json"):
        """
        Load profile from JSON file.

        Args:
            profile_path: Path to profile JSON file
        """
        self.profile_path = profile_path
        self.data: Dict[str, Any] = {}
        self._load_profile()

    def _load_profile(self):
        """Load profile data from JSON file."""
        if not os.path.exists(self.profile_path):
            logger.warning("Profile file not found: %s", self.profile_path)
            return

        try:
            with open(self.profile_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            logger.info(
                "Profile loaded: %s (%d top-level keys)",
                self.profile_path, len(self.data)
            )
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in profile file %s: %s", self.profile_path, e)
        except Exception as e:
            logger.error("Failed to load profile from %s: %s", self.profile_path, e)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """
        Get a value by dotted key path (e.g. 'personal.email').

        Args:
            dotted_key: Dot-separated path into the profile JSON
            default: Value to return if key not found

        Returns:
            The value at the path, or default if not found
        """
        keys = dotted_key.split(".")
        current = self.data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def match_field(self, label: str) -> Optional[str]:
        """
        Match a form field label to a profile value using regex patterns.

        This is the core method the Rule Engine calls. It takes a field label
        like "Your Email Address" and returns the profile value "user@example.com".

        Args:
            label: The form field label text (from DOM or AX tree)

        Returns:
            The matching profile value as string, or None if no match
        """
        if not label:
            return None

        label_clean = label.strip().lower()

        for pattern, profile_key in FIELD_PATTERNS:
            if re.search(pattern, label_clean, re.IGNORECASE):
                value = self.get(profile_key)
                if value is not None and str(value).strip():
                    result = str(value)
                    logger.debug(
                        "Field matched: '%s' -> %s = '%s'",
                        label[:50], profile_key, result[:30]
                    )
                    return result
                else:
                    logger.debug(
                        "Field pattern matched but no value: '%s' -> %s",
                        label[:50], profile_key
                    )
                    return None

        logger.debug("No field match for label: '%s'", label[:60])
        return None

    def get_resume_path(self) -> Optional[str]:
        """Get resume file path if configured and file exists."""
        path = self.get("resume_path", "")
        if path and os.path.exists(path):
            return path
        return None

    def get_skills_text(self) -> str:
        """Get comma-separated skills string for prompts."""
        primary = self.get("skills.primary", [])
        secondary = self.get("skills.secondary", [])
        all_skills = primary + secondary
        return ", ".join(all_skills) if all_skills else ""

    def get_target_roles(self) -> List[str]:
        """Get list of target role titles."""
        return self.get("preferences.target_roles", [])

    def render_cover_letter(self, company: str, role: str) -> str:
        """
        Render cover letter template with profile data.

        Args:
            company: Company name
            role: Job role title

        Returns:
            Rendered cover letter text
        """
        template = self.get("default_answers.cover_letter_template", "")
        if not template:
            return ""

        return template.format(
            name=self.get("personal.full_name", ""),
            role=role,
            company=company,
            experience=self.get("professional.years_experience", ""),
            skills=self.get_skills_text(),
        )

    def get_field_count(self) -> int:
        """Return count of matchable field patterns."""
        return len(FIELD_PATTERNS)

    def __repr__(self) -> str:
        name = self.get("personal.full_name", "Unknown")
        return f"ProfileStore(name='{name}', patterns={len(FIELD_PATTERNS)})"
