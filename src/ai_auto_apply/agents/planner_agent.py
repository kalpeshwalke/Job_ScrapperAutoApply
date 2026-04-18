"""
Planner Agent

High-level planning agent that decomposes application goals into sequential steps.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher
from src.common.logger import get_logger
from src.ai_auto_apply.core.structured_logger import StructuredLogger
from src.ai_auto_apply.core.mcp_client import MCPClient

logger = get_logger("planner_agent")


class PageStructureType(Enum):
    """Types of career page structures"""
    HOMEPAGE = "homepage"
    JOB_BOARD = "job_board"
    DIRECT_FORM = "direct_form"
    SEARCH_BASED = "search_based"
    UNKNOWN = "unknown"


@dataclass
class PageStructure:
    """Page structure classification result"""
    type: PageStructureType
    confidence: float  # 0.0 to 1.0
    indicators: List[str]  # What led to this classification
    recommended_strategy: str


class PlannerAgent:
    """High-level planning agent that decomposes application goals into steps"""
    
    SYSTEM_PROMPT_BASE = """You are an intelligent job application agent. Your goal is to navigate career pages and apply for jobs.

You will receive:
1. Job details (title, company, location, experience)
2. Current DOM state (ALL interactive elements: links, buttons, inputs, etc.)
3. Iteration number and actions taken so far

Your task is to intelligently navigate and decide the next step. Respond with JSON in this exact format:
{
    "next_step": "Brief description of what to do next",
    "reasoning": "Why this step makes sense",
    "status": "in_progress" | "success" | "failed"
}

Status meanings:
- "in_progress": Continue with the next step
- "success": Application has been successfully submitted
- "failed": Application cannot be completed (genuine blocker, not just different page structure)

CRITICAL EDGE CASE RULES (OBEY STRICTLY):

1. **TALENT COMMUNITY TRAP**: If you land on a page that says "Join our Talent Network", "Talent Pool", or "General Application", DO NOT APPLY. Mark status as "failed" with reason: "Expired job redirect to Talent Community".
2. **LOGIN WALLS**: If the page requires you to "Create Account", "Sign In", or enter a password to see the application (e.g. Workday/Taleo), mark as "failed" with reason: "Authentication Wall".
3. **EEO Protected Class**: For demographic questions legally asking for Race, Gender, Veteran status, or Disability, ALWAYS select 'Prefer not to answer' or 'Decline to self-identify'. Never hallucinate these answers.
4. **MANDATORY MISSING DATA**: If a mandatory field asks a highly specific subjective question (e.g. "Will you relocate?") and you have no profile data for it, default to 'No' or 'N/A' rather than hallucinating 'Yes'.
5. **ANTI-BOT BLOCKS**: If you see "Verify you are human", "Cloudflare", or "reCAPTCHA", DO NOT try to click it endlessly. Mark as "failed" with reason: "CAPTCHA Block".
6. **AUTOFILL FIRST**: Always look for an "Autofill with Resume", "Parse Resume", or "Upload Resume" button and execute that BEFORE attempting to manually type into dozens of fields.
7. **ROLE VERIFICATION**: NEVER apply blindly. Check the page text and header. If the form is for a DIFFERENT role than the target job (e.g. intended 'Software Engineer' but page says 'Sales'), DO NOT APPLY. Navigate back and use Search.

IMPORTANT NAVIGATION STRATEGIES:

1. **Job Listings Page**: If you see multiple job links, search for the specific job title and click it
2. **Pagination**: If you don't see the job, look for "Next", "Load More", or page numbers to navigate
3. **Search Functionality**: Use search boxes to find the specific job role
4. **Multi-step Forms**: Navigate through "Next", "Continue" buttons across multiple pages
5. **Different Page Structures**: Adapt to any career page layout - some have job boards, some have direct forms
6. **Role Selection**: If there are multiple roles listed, click on the one matching the job title

BE ADAPTIVE: Every career page is different. Use the DOM elements to understand the page structure and navigate intelligently. Don't fail just because the page doesn't have a form immediately - it might be a job listings page that needs navigation first.

BROWSER AGENT TOOLS AVAILABLE:
The Browser Agent can execute these 6 tools to interact with web pages:
- click_element(mmid): Click buttons, links, and other interactive elements
- enter_text(mmid, text): Fill input fields with text
- select_option(mmid, value): Select options from dropdown menus
- upload_file(mmid, file_path): Upload files (e.g., resume, cover letter)
- press_key(key): Press keyboard keys (e.g., Enter, Tab)
- navigate(url): Navigate to a specific URL

When planning steps, ensure each step can be executed using these tools.

HALLUCINATION WARNING:
- Do NOT invent tool names that don't exist
- Do NOT assume tools like 'apply_for_job', 'search_jobs', 'autofill_form' exist
- Only reference the 6 Browser Agent tools listed above"""
    
    MCP_TOOLS_DESCRIPTION = """

AVAILABLE MCP TOOLS:
You have access to Playwright MCP tools for direct browser interaction:
- playwright_navigate: Navigate to a URL
- playwright_click: Click an element by selector
- playwright_fill: Fill an input field
- playwright_screenshot: Capture a screenshot
- playwright_evaluate: Execute JavaScript on the page

Use these tools to query page state and make informed decisions."""
    
    def __init__(self, provider, config: Dict[str, Any], mcp_client: Optional[MCPClient] = None):
        """
        Initialize Planner Agent.
        
        Args:
            provider: AIProvider instance
            config: auto_apply configuration
            mcp_client: Optional MCP client for direct browser control
        """
        self.provider = provider
        self.config = config
        self.mcp_client = mcp_client
        self.mcp_enabled = mcp_client is not None and config.get("mcp", {}).get("enabled", False)
        self.log_decisions = config.get("logging", {}).get("log_ai_decisions", True)
        self.structured_logger = StructuredLogger("planner", config.get("logging", {}))
        
        # Build system prompt based on MCP availability
        self.system_prompt = self._build_system_prompt()
        
        logger.info(f"PlannerAgent initialized with MCP {'enabled' if self.mcp_enabled else 'disabled'}")
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with optional MCP tool descriptions"""
        prompt = self.SYSTEM_PROMPT_BASE
        if self.mcp_enabled:
            prompt += self.MCP_TOOLS_DESCRIPTION
        return prompt
    
    # ----------------------------------------------------------------
    # Accessibility Tree-based navigation (industry-standard approach)
    # ----------------------------------------------------------------
    
    def find_careers_link_from_ax_tree(
        self, 
        ax_snapshot: str, 
        current_url: str, 
        company: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Find the careers/jobs link from an accessibility tree snapshot.
        
        This is the primary navigation method, replacing the old regex-based
        analyze_page_with_ai(). It sends the compact AX tree (~500-2000 chars)
        to the AI instead of extracting links from raw HTML (~1.3M chars).
        
        Token usage: ~700 tokens (vs ~5000 for old approach)
        
        Args:
            ax_snapshot: Formatted accessibility tree text with [N] references
            current_url: Current page URL
            company: Company name for context
            
        Returns:
            Dict with action instructions:
            {"action": "click_ref", "ref": 3, "reasoning": "..."}
            {"action": "navigate_url", "url": "https://...", "reasoning": "..."}
            {"action": "click_text", "text": "Careers", "reasoning": "..."}
            Or None if no careers link found.
        """
        prompt = f"""You are navigating {company}'s website to find their careers/jobs page.

Current URL: {current_url}

Below is the accessibility tree of the current page. Interactive elements are marked with [N] numbers.

{ax_snapshot}

TASK: Find the link that leads to the careers, jobs, or "join us" page.

RULES:
1. Look for links labeled "Careers", "Jobs", "Join Us", "Work With Us", "Openings" etc.
2. Navigation bar and footer links are most reliable
3. IGNORE product pages, courses, blog posts, pricing pages
4. If you see a direct careers URL, prefer navigate_url action

Respond with JSON:
{{
    "action": "click_ref" | "navigate_url" | "click_text" | "not_found",
    "ref": <element number if click_ref>,
    "url": "<URL if navigate_url>",
    "text": "<link text if click_text>",
    "reasoning": "Why this is the careers link"
}}"""

        try:
            response = self.provider.generate_planner_response(
                prompt=prompt,
                context={}
            )
            
            # Log token usage
            if response.usage:
                tokens = response.usage.get("total_tokens", 0)
                logger.info(f"AX tree navigation: {tokens} tokens used")
                self.structured_logger.log_api_usage(
                    provider=self.provider.get_provider_name(),
                    model=self.provider.model,
                    endpoint="find_careers_link_ax_tree",
                    tokens_used=tokens
                )
            
            # Parse response
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            import json
            result = json.loads(content)
            
            action = result.get("action", "not_found")
            if action == "not_found":
                logger.warning(f"AI found no careers link. Reasoning: {result.get('reasoning', 'N/A')}")
                return None
            
            # Ensure ref is an int if present
            if "ref" in result and result["ref"] is not None:
                result["ref"] = int(result["ref"])
            
            logger.info(f"AI navigation decision: {action} - {result.get('reasoning', 'N/A')}")
            return result
            
        except Exception as e:
            logger.error(f"AX tree navigation failed: {e}", exc_info=True)
            return None
    
    def find_popup_dismiss_action(
        self, 
        ax_snapshot: str, 
        current_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find the action to dismiss a cookie banner or modal popup.
        
        Args:
            ax_snapshot: Formatted accessibility tree text with [N] references
            current_url: Current page URL
            
        Returns:
            Dict with action instructions:
            {"action": "click_ref", "ref": 3, "reasoning": "..."}
            Or None if no obvious popup/cookie banner exists.
        """
        prompt = f"""You are analyzing a web page which might have a cookie consent banner, newsletter popup, or overlay modal that blocks the UI.

Current URL: {current_url}

Below is the accessibility tree of the page. Interactive elements are marked with [N] numbers.

{ax_snapshot}

TASK: Find the button or link that will dismiss any intrusive popups.

RULES:
1. Look for cookie consent options: "Accept All Cookies", "Accept", "Reject All", "Decline", "Got it", "Allow All". PREFER rejecting if available, otherwise accept.
2. Look for newsletter/modal dismissals: "Close", "X", "Dismiss", "No thanks", "Maybe later".
3. ONLY return an action if you are highly confident it's a popup dismiss button. DO NOT return main navigation links or standard page buttons.
4. If you don't confidently see a popup/cookie banner dismissal element, return "action": "not_found".

Respond with JSON:
{{
    "action": "click_ref" | "not_found",
    "ref": <element number to click if click_ref>,
    "reasoning": "Why this is the correct dismiss button"
}}"""

        try:
            response = self.provider.generate_planner_response(
                prompt=prompt,
                context={}
            )
            
            # Parse response
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            import json
            result = json.loads(content)
            
            action = result.get("action", "not_found")
            if action == "not_found":
                logger.debug(f"AI found no popup to dismiss. Reasoning: {result.get('reasoning', 'N/A')}")
                return None
            
            # Ensure ref is an int if present
            if "ref" in result and result["ref"] is not None:
                result["ref"] = int(result["ref"])
            
            logger.info(f"AI popup dismiss decision: {action} - {result.get('reasoning', 'N/A')}")
            return result
            
        except Exception as e:
            logger.error(f"Popup dismiss detection failed: {e}", exc_info=True)
            return None
    
    def analyze_page_with_ai(self, page_html: str, current_url: str) -> Dict[str, Any]:
        """
        Analyze page structure using AI to find careers links.
        
        OPTIMIZED APPROACH: Use Playwright locators to find career-related links,
        then send only the link data (not HTML) to AI for selection.
        
        This reduces token usage by 99% compared to sending HTML.
        
        Args:
            page_html: HTML content of the page (not used in optimized version)
            current_url: Current page URL
            
        Returns:
            Dictionary with page analysis:
            {
                "careers_links": List[Dict] - Links related to careers/jobs
                "reasoning": str - AI's reasoning for selections
            }
        """
        try:
            # OPTIMIZATION: Use Playwright to find links directly instead of sending HTML to AI
            from playwright.sync_api import sync_playwright
            
            # Get page from orchestrator (passed via context)
            # For now, we'll extract links from HTML using regex as fallback
            # In production, this should use the actual Playwright page object
            
            import re
            
            # Strategy 1: Find links with career-related keywords in text or href
            # Removed generic 'work' and added 'work with us'
            career_keywords = ['career', 'careers', 'job', 'jobs', 'hiring', 'join', 'work with us', 'opportunity', 'opportunities', 'talent', 'recruit', 'employ', 'opening', 'position']
            penalty_keywords = ['product', 'course', 'mock test', 'interview', 'blog', 'article', 'pricing', 'support', 'login', 'register']
            
            careers_links = []
            
            # Extract all <a> tags with href
            link_pattern = r'<a\s+(?:[^>]*?\s+)?href=["\'](.*?)["\'](?:[^>]*?)>(.*?)</a>'
            matches = re.finditer(link_pattern, page_html, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                href = match.group(1)
                text = re.sub(r'<[^>]+>', '', match.group(2)).strip()  # Remove HTML tags from text
                
                # Check if link is career-related
                text_lower = text.lower()
                href_lower = href.lower()
                
                # Calculate relevance score
                relevance_score = 0
                matched_keywords = []
                
                # Strict word boundary matching for text to prevent false positives
                for keyword in career_keywords:
                    # Exact or word boundary match in text
                    if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                        relevance_score += 15
                        matched_keywords.append(keyword)
                    # For href, substring is okay but lower score
                    if keyword in href_lower:
                        relevance_score += 5
                        if keyword not in matched_keywords:
                            matched_keywords.append(keyword)
                
                # Exact match boost - massively increased to ensure they win over noisy product pages
                if text_lower in ['careers', 'jobs', 'career', 'job openings', 'join us', 'join our team']:
                    relevance_score += 80
                    matched_keywords.append("exact_match_boost")
                
                # Penalize irrelevant links - massively increased to kill false positives
                for penalty in penalty_keywords:
                    if penalty in text_lower or penalty in href_lower:
                        relevance_score -= 100
                
                # Only include links with positive relevance
                if relevance_score > 0:
                    # Determine confidence based on score
                    if relevance_score >= 15:
                        confidence = "high"
                    elif relevance_score >= 8:
                        confidence = "medium"
                    else:
                        confidence = "low"
                    
                    # Determine location (simplified)
                    location = "body"
                    if "nav" in page_html[max(0, match.start()-500):match.start()].lower():
                        location = "nav"
                    elif "footer" in page_html[max(0, match.start()-500):match.start()].lower():
                        location = "footer"
                    elif "header" in page_html[max(0, match.start()-500):match.start()].lower():
                        location = "header"
                    
                    careers_links.append({
                        "text": text[:100],  # Limit text length
                        "href": href,
                        "location": location,
                        "confidence": confidence,
                        "reasoning": f"Contains keywords: {', '.join(matched_keywords)}",
                        "score": relevance_score
                    })
            
            # Sort by relevance score (highest first)
            careers_links.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            # Limit to top 10 most relevant links
            careers_links = careers_links[:10]
            
            # Log results
            logger.info(f"Locator-based analysis found {len(careers_links)} careers links (no AI call needed)")
            for link in careers_links[:3]:  # Log first 3
                logger.info(f"  - {link.get('text')} ({link.get('confidence')}, score: {link.get('score')}) -> {link.get('href')}")
            
            # Calculate token savings
            original_html_size = len(page_html)
            data_sent_size = sum(len(str(link)) for link in careers_links)
            reduction_pct = ((original_html_size - data_sent_size) / original_html_size * 100) if original_html_size > 0 else 0
            logger.info(f"Token optimization: {original_html_size} -> {data_sent_size} chars ({reduction_pct:.1f} percent reduction, NO AI CALL)")
            
            return {
                "careers_links": careers_links,
                "reasoning": f"Found {len(careers_links)} career-related links using keyword matching (no AI needed)"
            }
        
        except Exception as e:
            logger.error(f"Locator-based page analysis failed: {e}", exc_info=True)
            return {"careers_links": [], "reasoning": f"Error: {str(e)}"}
    
    def select_best_careers_link(self, careers_links: List[Dict]) -> Optional[Dict]:
        """
        Select the best careers link, using AI only when needed.
        
        OPTIMIZED 3-TIER APPROACH:
        1. If only 1 link found -> return it (no AI call)
        2. If an obvious exact-match exists -> return it (no AI call)
        3. If ambiguous -> ask AI to pick the best one (~500 tokens)
        
        Args:
            careers_links: List of career link dictionaries from locator analysis
            
        Returns:
            Best careers link or None
        """
        if not careers_links:
            return None
        
        # Tier 1: Only one link, return it
        if len(careers_links) == 1:
            logger.info(f"Only one careers link found, selecting it: {careers_links[0].get('text')}")
            return careers_links[0]
        
        # Tier 2: Check for an obvious exact-match (skip AI call entirely)
        exact_match_texts = {'careers', 'career', 'jobs', 'job openings', 'join us', 'join our team', 'work with us'}
        for link in careers_links:
            text_lower = link.get("text", "").strip().lower()
            href_lower = link.get("href", "").lower()
            # Strong signal: text is an exact career keyword
            if text_lower in exact_match_texts:
                logger.info(f"Exact-match career link found (no AI needed): '{link.get('text')}' -> {link.get('href')}")
                return link
            # Strong signal: href ends with /careers or /jobs
            if href_lower.rstrip('/').endswith(('/careers', '/jobs', '/career')):
                logger.info(f"URL-match career link found (no AI needed): '{link.get('text')}' -> {link.get('href')}")
                return link
        
        try:
            # Prepare compact link data for AI (only essential fields)
            link_data = []
            for i, link in enumerate(careers_links):
                link_data.append({
                    "index": i,
                    "text": link.get("text", "")[:100],  # Limit text length
                    "href": link.get("href", ""),
                    "location": link.get("location", "body"),
                    "confidence": link.get("confidence", "unknown")
                })
            
            # AI prompt for link selection
            prompt = """You are analyzing a homepage to find the careers page link.

Below are candidate links found using keyword matching. Your task is to select the BEST link that leads to the careers/jobs page.

CRITICAL RULES:
1. Prioritize links with "careers", "jobs", "join us" in text or URL
2. AVOID product pages, course pages, blog posts, or interview/test pages
3. Footer and navigation links are usually more reliable than body content
4. Shorter, cleaner link text is usually better than long descriptions

Candidate links:
"""
            for link in link_data:
                prompt += f"\n{link['index']}. Text: \"{link['text']}\"\n   URL: {link['href']}\n   Location: {link['location']}, Confidence: {link['confidence']}\n"
            
            prompt += """\nRespond with JSON in this format:
{
    "selected_index": <index of best link>,
    "reasoning": "Why this link is the best choice"
}"""
            
            # Call AI provider
            from google.genai import types
            response = self.provider.generate_planner_response(
                prompt=prompt,
                context={}
            )
            
            # Parse AI response
            import json
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            decision = json.loads(content)
            selected_index = decision.get("selected_index")
            
            # Validate selected_index
            if selected_index is None or not isinstance(selected_index, int):
                logger.warning(f"AI returned invalid selected_index: {selected_index}, using first link")
                selected_index = 0
            elif selected_index < 0 or selected_index >= len(careers_links):
                logger.warning(f"AI returned out-of-range index {selected_index}, using first link")
                selected_index = 0
            
            reasoning = decision.get("reasoning", "No reasoning provided")
            
            # Log AI decision
            if self.log_decisions:
                self.structured_logger.log_ai_decision(
                    decision_type="careers_link_selection",
                    data={
                        "selected_index": selected_index,
                        "selected_text": careers_links[selected_index].get("text", ""),
                        "selected_href": careers_links[selected_index].get("href", ""),
                        "total_candidates": len(careers_links)
                    },
                    reasoning=reasoning
                )
            
            logger.info(f"AI selected link {selected_index}: '{careers_links[selected_index].get('text')}'")
            logger.info(f"AI reasoning: {reasoning}")
            
            # Log token usage
            if response.usage:
                tokens_used = response.usage.get("total_tokens", 0)
                logger.info(f"Token usage for link selection: {tokens_used} tokens")
                
                self.structured_logger.log_api_usage(
                    provider=self.provider.get_provider_name(),
                    model=self.provider.model,
                    endpoint="select_best_careers_link",
                    tokens_used=tokens_used
                )
            
            return careers_links[selected_index]
        
        except Exception as e:
            logger.error(f"AI link selection failed: {e}", exc_info=True)
            logger.warning("Falling back to first link")
            return careers_links[0]
    
    def plan_next_step(
        self, 
        job_data: Dict[str, Any],
        dom_state: Dict[str, Any],
        iteration: int,
        actions_taken: List[str]
    ) -> Dict[str, Any]:
        """
        Plan the next step in the application process.
        
        Args:
            job_data: Job details (title, company, etc.)
            dom_state: Current DOM state with interactive elements
            iteration: Current iteration number
            actions_taken: List of actions taken so far
            
        Returns:
            Dictionary with next_step, reasoning, and status
        """
        # Use AX tree as primary context if available (much more token-efficient)
        ax_snapshot = dom_state.get("ax_snapshot")
        
        if ax_snapshot:
            # Primary path: Use compact AX tree for AI context
            # This is ~5-10x more token-efficient than the categorized DOM state
            context = {
                "job_title": job_data["title"],
                "company": job_data["company"],
                "location": job_data.get("location", ""),
                "experience": job_data.get("experience", ""),
                "user_details": job_data.get("user_details", {}),
                "iteration": iteration,
                "actions_taken": actions_taken,
                "page_url": dom_state.get("url", ""),
                "page_title": dom_state.get("title", ""),
                "accessibility_tree": ax_snapshot
            }
        else:
            # Fallback: Use categorized DOM state (old approach)
            categorized_state = self._categorize_elements(dom_state)
            context = {
                "job_title": job_data["title"],
                "company": job_data["company"],
                "location": job_data.get("location", ""),
                "experience": job_data.get("experience", ""),
                "user_details": job_data.get("user_details", {}),
                "iteration": iteration,
                "actions_taken": actions_taken,
                "dom_state": categorized_state
            }
        
        try:
            response = self.provider.generate_planner_response(
                prompt=self.system_prompt,
                context=context
            )
            
            # Parse JSON response
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            decision = json.loads(content)
            
            # Log API usage
            if response.usage:
                self.structured_logger.log_api_usage(
                    provider=self.provider.get_provider_name(),
                    model=self.provider.model,
                    endpoint="generate_planner_response",
                    tokens_used=response.usage.get("total_tokens")
                )
            
            if self.log_decisions:
                # Log with structured logger
                self.structured_logger.log_ai_decision(
                    decision_type="planner_next_step",
                    data={
                        "iteration": iteration,
                        "next_step": decision.get("next_step", ""),
                        "status": decision.get("status", ""),
                        "job_title": job_data["title"],
                        "company": job_data["company"]
                    },
                    reasoning=decision.get("reasoning", "")
                )
                
                # Also log with traditional logger for backward compatibility
                logger.info(
                    "Planner decision (iteration %d): %s | Status: %s | Reasoning: %s",
                    iteration,
                    decision.get("next_step", ""),
                    decision.get("status", ""),
                    decision.get("reasoning", "")
                )
            
            return decision
        
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Planner response as JSON: %s", e)
            return {
                "next_step": "Error: Invalid response format",
                "reasoning": f"JSON parse error: {str(e)}",
                "status": "failed"
            }
        
        except Exception as e:
            logger.error("Planner error: %s", e, exc_info=True)
            return {
                "next_step": "Error: Planner failed",
                "reasoning": f"Error: {str(e)}",
                "status": "failed"
            }
    
    def detect_page_structure(self, current_url: str, dom_state: Dict[str, Any]) -> PageStructure:
        """
        Detect and classify the page structure using MCP tools.
        
        Args:
            current_url: Current page URL
            dom_state: Current DOM state with elements
            
        Returns:
            PageStructure with classification and confidence
        """
        indicators = []
        confidence = 0.0
        page_type = PageStructureType.UNKNOWN
        strategy = "adaptive_exploration"
        
        # Use MCP to query page elements if available
        if self.mcp_enabled and self.mcp_client:
            try:
                # Query for job listing indicators
                job_links = self._count_elements_with_keywords(
                    dom_state, 
                    ["job", "position", "role", "opening", "career"]
                )
                
                # Query for form indicators
                form_inputs = self._count_form_elements(dom_state)
                
                # Query for search indicators
                search_elements = self._count_elements_with_keywords(
                    dom_state,
                    ["search", "find", "filter"]
                )
                
                # Query for pagination indicators
                pagination_elements = self._count_elements_with_keywords(
                    dom_state,
                    ["next", "previous", "page", "load more"]
                )
                
                # Classify based on indicators
                if job_links >= 5:
                    page_type = PageStructureType.JOB_BOARD
                    confidence = min(0.7 + (job_links * 0.05), 1.0)
                    indicators.append(f"Found {job_links} job-related links")
                    strategy = "job_board_navigation"
                    
                    if pagination_elements > 0:
                        indicators.append(f"Found {pagination_elements} pagination elements")
                        confidence = min(confidence + 0.1, 1.0)
                
                elif form_inputs >= 3:
                    page_type = PageStructureType.DIRECT_FORM
                    confidence = min(0.6 + (form_inputs * 0.08), 1.0)
                    indicators.append(f"Found {form_inputs} form input fields")
                    strategy = "form_filling"
                
                elif search_elements >= 2:
                    page_type = PageStructureType.SEARCH_BASED
                    confidence = 0.7
                    indicators.append(f"Found {search_elements} search elements")
                    strategy = "search_and_apply"
                
                # Check for homepage indicators
                url_lower = current_url.lower()
                if any(indicator in url_lower for indicator in ['/', 'index', 'home']) and \
                   not any(keyword in url_lower for keyword in ['career', 'job', 'hiring']):
                    page_type = PageStructureType.HOMEPAGE
                    confidence = 0.8
                    indicators.append("URL suggests homepage")
                    strategy = "homepage_navigation"
                
            except Exception as e:
                logger.error(f"Error detecting page structure with MCP: {e}")
                indicators.append(f"MCP detection error: {str(e)}")
        
        else:
            # Fallback to DOM state analysis without MCP
            # DOMToolkit returns {"elements": [...]} with each element having tag, type, text, etc.
            elements = dom_state.get("elements", [])
            
            # Classify elements by tag type
            links = [el for el in elements if el.get("tag") == "a"]
            inputs = [el for el in elements if el.get("tag") in ("input", "textarea", "select")]
            buttons = [el for el in elements if el.get("tag") == "button"]
            
            job_links = sum(1 for link in links if any(
                kw in link.get("text", "").lower() 
                for kw in ["job", "position", "role", "opening", "career"]
            ))
            
            if job_links >= 5:
                page_type = PageStructureType.JOB_BOARD
                confidence = 0.7
                indicators.append(f"Found {job_links} job-related links")
                strategy = "job_board_navigation"
            elif len(inputs) >= 3:
                page_type = PageStructureType.DIRECT_FORM
                confidence = 0.6
                indicators.append(f"Found {len(inputs)} form inputs")
                strategy = "form_filling"
        
        # Log the classification decision
        if self.log_decisions:
            self.structured_logger.log_ai_decision(
                decision_type="page_structure_classification",
                data={
                    "page_type": page_type.value,
                    "confidence": confidence,
                    "indicators": indicators,
                    "url": current_url
                },
                reasoning=f"Classified as {page_type.value} with {confidence:.2f} confidence"
            )
        
        return PageStructure(
            type=page_type,
            confidence=confidence,
            indicators=indicators,
            recommended_strategy=strategy
        )
    
    def _count_elements_with_keywords(self, dom_state: Dict[str, Any], keywords: List[str]) -> int:
        """Count elements containing any of the keywords"""
        count = 0
        elements = dom_state.get("elements", [])
        for element in elements:
            text = element.get("text", "").lower()
            href = element.get("href", "").lower()
            placeholder = element.get("placeholder", "").lower()
            if any(kw in text or kw in href or kw in placeholder for kw in keywords):
                count += 1
        return count
    
    def _count_form_elements(self, dom_state: Dict[str, Any]) -> int:
        """Count form input elements"""
        elements = dom_state.get("elements", [])
        return sum(1 for el in elements if el.get("tag") in ("input", "textarea", "select"))
    
    def _categorize_elements(self, dom_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Categorize flat elements list into links, buttons, and inputs for easier processing.
        
        OPTIMIZED: Filters out non-essential elements and limits data sent to AI.
        
        Args:
            dom_state: Original dom_state with "elements" list
            
        Returns:
            Dictionary with categorized elements (optimized for token usage)
        """
        elements = dom_state.get("elements", [])
        categorized = {
            "url": dom_state.get("url", ""),
            "title": dom_state.get("title", ""),
            "links": [],
            "buttons": [],
            "inputs": []
        }
        
        # OPTIMIZATION: Only include essential fields to reduce tokens
        def compact_element(el: Dict[str, Any]) -> Dict[str, Any]:
            """Extract only essential fields from element"""
            compact = {
                "text": el.get("text", "")[:100],  # Limit text to 100 chars
                "mmid": el.get("mmid", "")
            }
            
            # Add type-specific fields
            if el.get("tag") == "a":
                compact["href"] = el.get("href", "")
            elif el.get("tag") in ("input", "textarea", "select"):
                compact["type"] = el.get("type", "")
                compact["name"] = el.get("name", "")
                compact["placeholder"] = el.get("placeholder", "")[:50]  # Limit placeholder
                compact["required"] = el.get("required", False)
            
            return compact
        
        for el in elements:
            tag = el.get("tag", "").lower()
            el_type = el.get("type", "").lower()
            
            # Simple categorization logic
            if tag == "a" or el.get("role") == "link":
                categorized["links"].append(compact_element(el))
            elif tag == "button" or el_type in ("button", "submit") or el.get("role") == "button":
                categorized["buttons"].append(compact_element(el))
            elif tag in ("input", "textarea", "select") or el.get("role") in ("textbox", "checkbox", "combobox"):
                categorized["inputs"].append(compact_element(el))
        
        # OPTIMIZATION: Limit number of elements to reduce tokens
        max_elements_per_type = 50  # Configurable limit
        categorized["links"] = categorized["links"][:max_elements_per_type]
        categorized["buttons"] = categorized["buttons"][:max_elements_per_type]
        categorized["inputs"] = categorized["inputs"][:max_elements_per_type]
        
        # Log optimization stats
        total_original = len(elements)
        total_kept = len(categorized["links"]) + len(categorized["buttons"]) + len(categorized["inputs"])
        logger.debug(f"DOM optimization: {total_original} → {total_kept} elements ({total_kept/total_original*100:.1f}% kept)")
        
        return categorized

    def _plan_job_board_navigation(
        self, 
        job_data: Dict[str, Any], 
        dom_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Plan navigation strategy for job board pages.
        
        Args:
            job_data: Job details
            dom_state: Current DOM state
            
        Returns:
            Next step decision
        """
        job_title = job_data.get("title", "").lower()
        
        # Look for job title in links
        links = dom_state.get("links", [])
        matching_links = []
        
        for link in links:
            link_text = link.get("text", "").lower()
            similarity = SequenceMatcher(None, job_title, link_text).ratio()
            if similarity > 0.5 or any(word in link_text for word in job_title.split()):
                matching_links.append((link, similarity))
        
        if matching_links:
            # Sort by similarity and select best match
            matching_links.sort(key=lambda x: x[1], reverse=True)
            best_link = matching_links[0][0]
            
            self._log_strategy_decision(
                "job_board_navigation",
                f"Found matching job link: {best_link.get('text')}",
                {"similarity": matching_links[0][1]}
            )
            
            return {
                "next_step": f"Click on job listing: {best_link.get('text')}",
                "reasoning": f"Found job link matching '{job_title}' with {matching_links[0][1]:.2f} similarity",
                "status": "in_progress"
            }
        
        # Look for pagination or search
        buttons = dom_state.get("buttons", [])
        for button in buttons:
            button_text = button.get("text", "").lower()
            if any(kw in button_text for kw in ["next", "load more", "show more"]):
                self._log_strategy_decision(
                    "job_board_navigation",
                    "No matching job found, trying pagination",
                    {"button": button_text}
                )
                return {
                    "next_step": f"Click pagination button: {button.get('text')}",
                    "reasoning": "Job not found on current page, navigating to next page",
                    "status": "in_progress"
                }
        
        return {
            "next_step": "Search for job using search functionality",
            "reasoning": "Could not find job in listings, will try search",
            "status": "in_progress"
        }
    
    def _plan_form_filling(
        self, 
        job_data: Dict[str, Any], 
        dom_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Plan strategy for direct application form pages.
        
        Args:
            job_data: Job details
            dom_state: Current DOM state
            
        Returns:
            Next step decision
        """
        inputs = dom_state.get("inputs", [])
        
        # Identify unfilled required fields
        unfilled_fields = []
        for input_elem in inputs:
            if not input_elem.get("value") and input_elem.get("required", False):
                unfilled_fields.append(input_elem)
        
        if unfilled_fields:
            self._log_strategy_decision(
                "form_filling",
                f"Found {len(unfilled_fields)} unfilled required fields",
                {"fields": [f.get("name", f.get("id", "unknown")) for f in unfilled_fields]}
            )
            
            return {
                "next_step": f"Fill required form fields ({len(unfilled_fields)} remaining)",
                "reasoning": "Application form detected, filling required fields",
                "status": "in_progress"
            }
        
        # Look for submit button
        buttons = dom_state.get("buttons", [])
        for button in buttons:
            button_text = button.get("text", "").lower()
            if any(kw in button_text for kw in ["submit", "apply", "send"]):
                self._log_strategy_decision(
                    "form_filling",
                    "All fields filled, ready to submit",
                    {"submit_button": button_text}
                )
                return {
                    "next_step": f"Click submit button: {button.get('text')}",
                    "reasoning": "Form filled, submitting application",
                    "status": "in_progress"
                }
        
        return {
            "next_step": "Continue filling form",
            "reasoning": "Form partially filled, continuing",
            "status": "in_progress"
        }
    
    def _plan_search_and_apply(
        self, 
        job_data: Dict[str, Any], 
        dom_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Plan strategy for search-based career pages.
        
        Args:
            job_data: Job details
            dom_state: Current DOM state
            
        Returns:
            Next step decision
        """
        job_title = job_data.get("title", "")
        inputs = dom_state.get("inputs", [])
        
        # Look for search input
        search_input = None
        for input_elem in inputs:
            input_type = input_elem.get("type", "").lower()
            input_name = input_elem.get("name", "").lower()
            input_placeholder = input_elem.get("placeholder", "").lower()
            
            if input_type == "search" or "search" in input_name or "search" in input_placeholder:
                search_input = input_elem
                break
        
        if search_input:
            self._log_strategy_decision(
                "search_and_apply",
                f"Using search to find job: {job_title}",
                {"search_field": search_input.get("name", "unknown")}
            )
            
            return {
                "next_step": f"Search for job title: {job_title}",
                "reasoning": "Using search functionality to find specific job",
                "status": "in_progress"
            }
        
        return {
            "next_step": "Look for job in available listings",
            "reasoning": "Search not available, browsing listings",
            "status": "in_progress"
        }
    
    def _plan_adaptive_exploration(self) -> Dict[str, Any]:
        """
        Fallback adaptive exploration strategy.
        
        Returns:
            Next step decision
        """
        self._log_strategy_decision(
            "adaptive_exploration",
            "Using adaptive exploration as fallback",
            {}
        )
        
        return {
            "next_step": "Explore page to understand structure",
            "reasoning": "Page structure unclear, exploring adaptively",
            "status": "in_progress"
        }
    
    def select_best_element(
        self,
        candidates: List[Dict[str, Any]],
        target_text: str,
        context: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Select the best element from candidates using context-aware matching.
        
        Args:
            candidates: List of candidate elements
            target_text: Text to match against
            context: Additional context for selection
            
        Returns:
            Best matching element or None
        """
        if not candidates:
            return None
        
        scored_candidates = []
        target_lower = target_text.lower()
        
        for candidate in candidates:
            score = 0.0
            element_text = candidate.get("text", "").lower()
            element_type = candidate.get("type", "")
            is_visible = candidate.get("visible", True)
            
            # Fuzzy matching with 80% threshold
            similarity = SequenceMatcher(None, target_lower, element_text).ratio()
            if similarity >= 0.8:
                score += similarity * 10  # High weight for exact matches
            elif similarity >= 0.5:
                score += similarity * 5   # Medium weight for partial matches
            
            # Keyword matching
            target_words = set(target_lower.split())
            element_words = set(element_text.split())
            common_words = target_words & element_words
            if common_words:
                score += len(common_words) * 2
            
            # Prioritize visible elements
            if is_visible:
                score *= 1.5
            else:
                score *= 0.5
            
            # Element type bonus
            if element_type in ["button", "link"]:
                score *= 1.2
            
            scored_candidates.append((candidate, score, similarity))
        
        if not scored_candidates:
            return None
        
        # Sort by score and select best
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        best_candidate, best_score, best_similarity = scored_candidates[0]
        
        # Log selection reasoning
        if self.log_decisions:
            self.structured_logger.log_ai_decision(
                decision_type="element_selection",
                data={
                    "target_text": target_text,
                    "selected_text": best_candidate.get("text", ""),
                    "score": best_score,
                    "similarity": best_similarity,
                    "visible": best_candidate.get("visible", True),
                    "context": context
                },
                reasoning=f"Selected element with score {best_score:.2f} and similarity {best_similarity:.2f}"
            )
        
        return best_candidate
    
    def _log_strategy_decision(self, strategy: str, decision: str, data: Dict[str, Any]):
        """Log strategy selection decision"""
        if self.log_decisions:
            self.structured_logger.log_ai_decision(
                decision_type="strategy_selection",
                data={
                    "strategy": strategy,
                    "decision": decision,
                    **data
                },
                reasoning=f"Selected {strategy} strategy: {decision}"
            )
