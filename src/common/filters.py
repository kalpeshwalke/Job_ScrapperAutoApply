"""
Filters module — job filtering engine with a robust experience parser.
Handles messy experience formats from Naukri and LinkedIn.
"""

import math
import re
from typing import Optional

from src.common.logger import get_logger

logger = get_logger("filters")


# ---------------------------------------------------------------------------
# Experience Parser
# ---------------------------------------------------------------------------
def parse_experience(raw: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse messy experience strings into (min_years, max_years).

    Returns (None, None) for unparseable strings — benefit of the doubt.

    Examples:
        "2-4 yrs"          → (2, 4)
        "3+ years"         → (3, None)     # open-ended upper bound
        "2 to 5 years"     → (2, 5)
        "5 yrs max"        → (0, 5)
        "3 years"          → (3, 3)
        "Fresher"          → (0, 0)
        "1.5 - 3 years"    → (1, 3)        # floor decimals
        "0-1 years"        → (0, 1)
        ""                 → (None, None)   # don't filter
        None               → (None, None)
    """
    if not raw or not isinstance(raw, str):
        return (None, None)

    text = raw.strip().lower()

    # Handle "fresher" / "entry level"
    if "fresher" in text or "entry" in text or "intern" in text:
        return (0, 0)

    # Extract all numbers (int or float)
    numbers = re.findall(r"(\d+\.?\d*)", text)
    if not numbers:
        return (None, None)

    nums = [float(n) for n in numbers]

    # "max" pattern: "5 yrs max" → (0, 5)
    if "max" in text:
        return (0, math.floor(nums[-1]))

    # "+" pattern: "3+ years" → (3, None)
    if "+" in text:
        return (math.floor(nums[0]), None)

    # Two numbers: "2-4 yrs", "2 to 5 years"
    if len(nums) >= 2:
        return (math.floor(min(nums[0], nums[1])), math.floor(max(nums[0], nums[1])))

    # Single number: "3 years"
    return (math.floor(nums[0]), math.floor(nums[0]))


def _experience_matches(
    job_exp_raw: str,
    config_min: int,
    config_max: int,
    max_exp_years: int,
) -> tuple[bool, str]:
    """
    Check if parsed job experience is compatible with config range.

    Returns (is_match, reason).
    """
    job_min, job_max = parse_experience(job_exp_raw)

    # Unparseable → benefit of the doubt
    if job_min is None and job_max is None:
        return (True, "")

    # If job requires more than our absolute max → reject
    if job_min is not None and job_min > max_exp_years:
        return (False, f"requires {job_min}+ years (our max: {max_exp_years})")

    # If job's max is below our profile min → reject (underqualified role)
    if job_max is not None and job_max < config_min:
        return (False, f"max {job_max} years (below our min: {config_min})")

    return (True, "")


# ---------------------------------------------------------------------------
# Title / Role Filters
# ---------------------------------------------------------------------------
def _title_matches(
    title: str,
    exclude_title_kw: list[str],
    exclude_role_kw: list[str],
) -> tuple[bool, str]:
    """Check if job title should be excluded. Returns (keep, reason)."""
    title_lower = title.lower()

    for kw in exclude_title_kw:
        if kw.lower() in title_lower:
            return (False, f"title contains '{kw}'")

    for kw in exclude_role_kw:
        if kw.lower() in title_lower:
            return (False, f"title matches excluded role '{kw}'")

    return (True, "")


# ---------------------------------------------------------------------------
# Skills Filter
# ---------------------------------------------------------------------------
def _skills_match(
    title: str,
    skills: str,
    description: str,
    required_any: list[str],
) -> tuple[bool, str]:
    """
    Check if job mentions at least one required skill.
    Searches across title, skills tags, AND description to maximize matches.
    """
    # Combine all text fields for searching
    combined = f"{title} {skills} {description}".strip()

    if not combined:
        # No data at all — benefit of the doubt
        return (True, "")

    combined_lower = combined.lower()
    for skill in required_any:
        if skill.lower() in combined_lower:
            return (True, "")

    return (False, "no required skills found in title/skills/description")


# ---------------------------------------------------------------------------
# Main filter function
# ---------------------------------------------------------------------------
def filter_jobs(
    jobs: list[dict],
    required_skills_any: list[str],
    exclude_title_keywords: list[str],
    exclude_role_keywords: list[str],
    experience_range: dict,
    max_experience_years: int,
) -> list[dict]:
    """
    Apply all filter rules to a list of raw job dicts.

    Args:
        jobs: List of job dicts with keys like 'title', 'experience', 'description'.
        required_skills_any: At least one must appear in description.
        exclude_title_keywords: Reject if title contains any.
        exclude_role_keywords: Reject if title contains any.
        experience_range: {"min": int, "max": int} from config.
        max_experience_years: Absolute max experience to accept.

    Returns:
        Filtered list of job dicts.
    """
    config_min = experience_range.get("min", 0)
    config_max = experience_range.get("max", 99)

    kept = []
    rejected_count = 0

    for job in jobs:
        title = job.get("title", "")
        company = job.get("company", "")
        experience = job.get("experience", "")
        skills = job.get("skills", "")
        description = job.get("description", "")
        label = f"{title} @ {company}"

        # 1. Title exclusion
        ok, reason = _title_matches(title, exclude_title_keywords, exclude_role_keywords)
        if not ok:
            logger.debug("REJECTED [%s]: %s", label, reason)
            rejected_count += 1
            continue

        # 2. Experience check
        ok, reason = _experience_matches(experience, config_min, config_max, max_experience_years)
        if not ok:
            logger.debug("REJECTED [%s]: %s", label, reason)
            rejected_count += 1
            continue

        # 3. Required skills (checks title + skills + description)
        ok, reason = _skills_match(title, skills, description, required_skills_any)
        if not ok:
            logger.debug("REJECTED [%s]: %s", label, reason)
            rejected_count += 1
            continue

        kept.append(job)

    logger.info(
        "Filter results: %d kept, %d rejected (out of %d total)",
        len(kept), rejected_count, len(jobs),
    )
    return kept
