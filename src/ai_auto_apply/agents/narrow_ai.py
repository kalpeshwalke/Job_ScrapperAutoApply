"""
Narrow AI — 5 Constrained Call Types

The model is NEVER asked to pick tools or actions.
It only picks targets (ref numbers) or generates short text.

Every prompt is under 500 tokens. Every response is constrained JSON.
If JSON parsing fails -> retry once -> fallback to deterministic choice.

Call Types:
    1. disambiguate_link — "Which of these links goes to careers?"
    2. disambiguate_button — "Which of these buttons is Apply?"
    3. answer_unknown_field — "What value should go in this field?"
    4. answer_free_text — "Write a 2-sentence answer to this question"
    5. score_job_relevance — "Is this job relevant to the candidate?"
"""

import json
import re
from typing import Dict, Any, List, Optional
from src.common.logger import get_logger

logger = get_logger("narrow_ai")


# Minimum confidence score to act on AI disambiguation results.
# Below this threshold, the result is treated as no-decision.
MIN_CONFIDENCE = 0.6


class NarrowAI:
    """
    Constrained AI caller for ambiguous decisions only.
    
    The model receives tiny, schema-constrained prompts and returns
    simple JSON. No tool names, no action selection, no open-ended planning.
    
    Usage:
        ai = NarrowAI(provider)
        result = ai.disambiguate_link(candidates, context)
        # result = {"ref": 3, "confidence": 0.85}
    """

    def __init__(self, provider, profile_data: Dict[str, Any] = None):
        """
        Args:
            provider: AIProvider instance (Ollama, Gemini, etc.)
            profile_data: Optional profile context for AI calls
        """
        self.provider = provider
        self.profile_data = profile_data or {}
        self._retry_on_parse_fail = True

    # ================================================================
    #  CALL TYPE 1: Disambiguate Link
    # ================================================================

    def disambiguate_link(
        self,
        candidates: List[Dict[str, Any]],
        goal: str = "careers/jobs page",
        company: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Ask AI to pick the best link from ambiguous candidates.
        
        Used when the rule engine finds 2+ potential careers links
        and can't confidently pick one.
        
        Args:
            candidates: List of {text, href, score} dicts
            goal: What we're looking for (e.g., "careers/jobs page")
            company: Company name for context
            
        Returns:
            {"index": 0, "confidence": 0.85} or None on failure
        """
        if not candidates:
            return None

        # Build compact candidate list
        candidate_lines = []
        for i, c in enumerate(candidates):
            candidate_lines.append(
                f'{i}. text: "{c.get("text", "")[:60]}" | url: {c.get("href", "")[:80]}'
            )
        candidates_text = "\n".join(candidate_lines)

        prompt = f"""Pick the link most likely to lead to the {goal}.
Company: {company}

Links:
{candidates_text}

Rules:
- Prefer links with "careers", "jobs" in text or URL
- Ignore blog posts, courses, products
- Navigation/footer links are more reliable

JSON only:
{{"index": <number>, "confidence": <0.0-1.0>}}"""

        result = self._call_ai(prompt, expected_keys=["index"])
        if result is None:
            return None

        # Validate index
        idx = result.get("index")
        if idx is None or not isinstance(idx, (int, float)):
            logger.warning("AI returned invalid index: %s", idx)
            return None

        idx = int(idx)
        if idx < 0 or idx >= len(candidates):
            logger.warning("AI returned out-of-range index: %d (max: %d)", idx, len(candidates) - 1)
            return None

        confidence = float(result.get("confidence", 0.5))
        logger.info(
            "AI disambiguated link: index=%d '%s' (confidence: %.2f)",
            idx, candidates[idx].get("text", "")[:30], confidence,
        )
        if confidence < MIN_CONFIDENCE:
            logger.warning(
                "AI confidence %.2f below threshold %.2f, treating as no-decision",
                confidence, MIN_CONFIDENCE,
            )
            return None
        return {"index": idx, "confidence": confidence}

    # ================================================================
    #  CALL TYPE 2: Disambiguate Button
    # ================================================================

    def disambiguate_button(
        self,
        candidates: List[Dict[str, Any]],
        goal: str = "apply for the job",
    ) -> Optional[Dict[str, Any]]:
        """
        Ask AI to pick the correct button from ambiguous candidates.
        
        Args:
            candidates: List of {text, ref} dicts
            goal: What the button should do
            
        Returns:
            {"index": 0, "confidence": 0.91} or None
        """
        if not candidates:
            return None

        candidate_lines = []
        for i, c in enumerate(candidates):
            candidate_lines.append(
                f'{i}. text: "{c.get("text", "")[:60]}" | ref: [{c.get("ref", "?")}]'
            )
        candidates_text = "\n".join(candidate_lines)

        prompt = f"""Which button should be clicked to {goal}?

Buttons:
{candidates_text}

Rules:
- Pick the button that directly triggers the desired action
- Ignore "Save", "Share", "Filter", "Alert" buttons
- "Apply Now" > "Apply" > "Apply with LinkedIn"

JSON only:
{{"index": <number>, "confidence": <0.0-1.0>}}"""

        result = self._call_ai(prompt, expected_keys=["index"])
        if result is None:
            return None

        idx = result.get("index")
        if idx is None or not isinstance(idx, (int, float)):
            return None

        idx = int(idx)
        if idx < 0 or idx >= len(candidates):
            return None

        confidence = float(result.get("confidence", 0.5))
        logger.info(
            "AI disambiguated button: index=%d '%s' (confidence: %.2f)",
            idx, candidates[idx].get("text", "")[:30], confidence,
        )
        if confidence < MIN_CONFIDENCE:
            logger.warning(
                "AI confidence %.2f below threshold %.2f, treating as no-decision",
                confidence, MIN_CONFIDENCE,
            )
            return None
        return {"index": idx, "confidence": confidence}

    # ================================================================
    #  CALL TYPE 3: Answer Unknown Field
    # ================================================================

    def answer_unknown_field(
        self,
        field_label: str,
        field_type: str = "text",
        options: Optional[List[str]] = None,
        company: str = "",
        job_title: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Ask AI what value to put in a form field the rule engine couldn't match.
        
        Args:
            field_label: The form field label text
            field_type: "text", "select", "checkbox", "radio"
            options: Available options (for select/radio)
            company: Company name
            job_title: Job title
            
        Returns:
            {"value": "...", "action": "fill"|"select"|"skip"} or None
        """
        # Build profile context (compact)
        profile_snippet = ""
        if self.profile_data:
            p = self.profile_data
            profile_snippet = f"""
Candidate: {p.get('personal', {}).get('full_name', 'N/A')}
Title: {p.get('professional', {}).get('current_title', 'N/A')}
Experience: {p.get('professional', {}).get('years_experience', 'N/A')} years
Location: {p.get('personal', {}).get('location', 'N/A')}
Notice: {p.get('professional', {}).get('notice_period', 'N/A')}
CTC: {p.get('professional', {}).get('current_ctc', 'N/A')}"""

        options_text = ""
        if options:
            options_text = "\nOptions: " + " | ".join(str(o)[:40] for o in options[:10])

        prompt = f"""Map this form field to a value from the candidate profile, or generate a short answer.

Field: "{field_label}"
Type: {field_type}{options_text}
Job: {job_title} at {company}
{profile_snippet}

Rules:
- Use profile data when possible
- For demographics (gender, race, disability): always "Prefer not to answer" or "Decline"
- For yes/no unknowns: default "No"
- If field is genuinely impossible to answer: action="skip"

JSON only:
{{"value": "<answer>", "action": "fill" | "select" | "skip"}}"""

        result = self._call_ai(prompt, expected_keys=["value", "action"])
        if result is None:
            return None

        action = result.get("action", "fill")
        value = result.get("value", "")

        if action not in {"fill", "select", "skip"}:
            action = "fill"

        logger.info(
            "AI field answer: '%s' -> action=%s, value='%s'",
            field_label[:30], action, str(value)[:30],
        )
        return {"value": str(value), "action": action}

    # ================================================================
    #  CALL TYPE 4: Answer Free Text Question
    # ================================================================

    def answer_free_text(
        self,
        question: str,
        company: str = "",
        job_title: str = "",
        max_sentences: int = 3,
    ) -> Optional[str]:
        """
        Generate a short answer for a free-text application question.
        
        Args:
            question: The question text
            company: Company name
            job_title: Job title
            max_sentences: Maximum sentences in answer
            
        Returns:
            Answer text string, or None on failure
        """
        skills = ""
        experience = ""
        if self.profile_data:
            p = self.profile_data
            skills_list = p.get("skills", {}).get("primary", [])
            skills = ", ".join(skills_list[:5]) if skills_list else "testing, automation"
            experience = str(p.get("professional", {}).get("years_experience", "3"))

        prompt = f"""Write a concise {max_sentences}-sentence answer for this job application question.
Be specific, professional, do not over-sell or be generic.

Question: "{question}"
Company: {company}
Role: {job_title}
Candidate skills: {skills}
Experience: {experience} years

JSON only:
{{"answer": "<your answer here>"}}"""

        result = self._call_ai(prompt, expected_keys=["answer"])
        if result is None:
            return None

        answer = result.get("answer", "")
        if not answer:
            return None

        logger.info(
            "AI free-text answer: '%s' -> '%s'",
            question[:30], answer[:50],
        )
        return str(answer)

    # ================================================================
    #  CALL TYPE 5: Score Job Relevance
    # ================================================================

    def score_job_relevance(
        self,
        job_title: str,
        job_snippet: str = "",
    ) -> float:
        """
        Rate how relevant a job is to the candidate profile.
        
        Args:
            job_title: Job title text
            job_snippet: Short description snippet
            
        Returns:
            Relevance score 0.0 to 1.0 (default 0.5 on failure)
        """
        target_roles = []
        skills = []
        if self.profile_data:
            target_roles = self.profile_data.get("preferences", {}).get("target_roles", [])
            skills = self.profile_data.get("skills", {}).get("primary", [])

        prompt = f"""Rate job relevance 0.0-1.0 for this candidate.

Target roles: {', '.join(target_roles[:5])}
Skills: {', '.join(skills[:5])}

Job title: "{job_title}"
Snippet: "{job_snippet[:150]}"

JSON only:
{{"score": <0.0-1.0>, "reason": "<brief reason>"}}"""

        result = self._call_ai(prompt, expected_keys=["score"])
        if result is None:
            return 0.5

        score = result.get("score", 0.5)
        try:
            score = float(score)
            score = max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            score = 0.5

        logger.info("Job relevance: '%s' -> %.2f", job_title[:30], score)
        return score

    # ================================================================
    #  INTERNAL: AI CALL WITH JSON PARSING + RETRY
    # ================================================================

    def _call_ai(
        self,
        prompt: str,
        expected_keys: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Make a constrained AI call and parse JSON response.
        
        Retries once on JSON parse failure. Returns None on total failure.
        
        Args:
            prompt: The full prompt text (should be < 500 tokens)
            expected_keys: Keys that must be present in response JSON
            
        Returns:
            Parsed JSON dict, or None on failure
        """
        for attempt in range(2):  # Try twice max
            try:
                response = self.provider.generate_completion(
                    prompt=prompt,
                )

                content = response.content.strip()

                # Strip markdown code fences
                content = self._strip_code_fences(content)

                # Try to extract JSON from response
                parsed = self._extract_json(content)

                if parsed is None:
                    logger.warning(
                        "AI response not valid JSON (attempt %d): '%s'",
                        attempt + 1, content[:100],
                    )
                    if attempt == 0 and self._retry_on_parse_fail:
                        continue
                    return None

                # Validate expected keys
                missing = [k for k in expected_keys if k not in parsed]
                if missing:
                    logger.warning(
                        "AI response missing keys %s (attempt %d): %s",
                        missing, attempt + 1, parsed,
                    )
                    if attempt == 0 and self._retry_on_parse_fail:
                        continue
                    return None

                # Log token usage
                if response.usage:
                    tokens = response.usage.get("total_tokens", 0)
                    logger.debug("Narrow AI call: %d tokens used", tokens)

                return parsed

            except Exception as e:
                logger.error(
                    "Narrow AI call failed (attempt %d): %s",
                    attempt + 1, e,
                )
                if attempt == 0:
                    continue
                return None

        return None

    def _strip_code_fences(self, text: str) -> str:
        """Remove ```json ... ``` wrappers from AI response."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON object from text, handling common AI quirks.
        
        Tries:
        1. Direct parse
        2. Find first { ... } block
        3. Give up
        """
        # Attempt 1: Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Attempt 2: Find JSON block in text
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Attempt 3: Try to find nested JSON (for more complex responses)
        match = re.search(r'\{[^}]*\{[^}]*\}[^}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None
