"""
Homepage Navigator

Specialized component for navigating from company homepage to careers page.
Implements intelligent careers link detection and navigation.
"""

from typing import Dict, Any, List, Optional
from playwright.sync_api import Page
from src.common.logger import get_logger

logger = get_logger("homepage_navigator")


class HomepageNavigator:
    """
    Navigates from company homepage to careers page by detecting and clicking
    careers-related navigation links.
    
    Validates Requirements: 1.5, 1.6, 16.1, 16.2
    """
    
    # Career keywords with priority weights for scoring links
    # Higher weight = stronger indicator of careers page
    CAREER_KEYWORDS = {
        "careers": 10,
        "jobs": 10,
        "opportunities": 8,
        "join us": 7,
        "join our team": 7,
        "work with us": 6,
        "hiring": 5,
        "openings": 5,
        "employment": 5,
        "vacancies": 5,
        "positions": 4,
        "apply": 4,
        "talent": 3,
        "team": 2,
    }
    
    def __init__(self, page: Page, config: Dict[str, Any]):
        """
        Initialize Homepage Navigator.
        
        Args:
            page: Playwright Page instance for browser interactions
            config: Configuration dictionary with homepage navigation settings
        """
        self.page = page
        self.config = config
        
        # Extract homepage navigation config with defaults
        homepage_config = config.get("auto_apply", {}).get("homepage_navigation", {})
        self.enabled = homepage_config.get("enabled", True)
        self.max_attempts = homepage_config.get("max_attempts", 3)
        
        # Copy class-level keywords to instance level to avoid mutating shared state
        self.career_keywords = dict(self.CAREER_KEYWORDS)
        
        # Get career keywords from config or use defaults
        custom_keywords = homepage_config.get("career_keywords", [])
        if custom_keywords:
            # If custom keywords provided, add them with default weight
            for keyword in custom_keywords:
                if keyword.lower() not in self.career_keywords:
                    self.career_keywords[keyword.lower()] = 5
        
        logger.info(
            "HomepageNavigator initialized (enabled=%s, max_attempts=%d, keywords=%d)",
            self.enabled,
            self.max_attempts,
            len(self.career_keywords)
        )
    
    def find_careers_link(self) -> Optional[Dict[str, Any]]:
        """
        Find careers navigation link on current page.
        
        Implements intelligent link detection by:
        1. Querying all links with href attributes
        2. Scoring links based on text and href keyword matches
        3. Boosting score for navigation elements (header, footer, nav)
        4. Returning highest scoring link
        
        Validates Requirements: 1.5, 16.2, 16.3, 16.4
        
        Returns:
            Dictionary with link details (text, href, selector) or None if no careers link found
        """
        try:
            logger.info("Searching for careers navigation link on page")
            
            # Step 1: Get all links with href attributes
            links = self.page.locator("a[href]").all()
            
            if not links:
                logger.warning("No links found on page")
                return None
            
            logger.info(f"Found {len(links)} links on page, analyzing...")
            
            # Step 2: Score each link
            scored_links = []
            
            for link in links:
                try:
                    # Get link properties
                    text = link.inner_text().lower().strip()
                    href = link.get_attribute("href") or ""
                    href_lower = href.lower()
                    
                    # Skip empty links
                    if not text and not href:
                        continue
                    
                    # Calculate base score from keyword matches
                    score = 0
                    matched_keywords = []
                    
                    for keyword, weight in self.career_keywords.items():
                        # Text match is stronger (2x weight)
                        if keyword in text:
                            score += weight * 2
                            matched_keywords.append(f"text:{keyword}")
                        
                        # Href match
                        if keyword in href_lower:
                            score += weight
                            matched_keywords.append(f"href:{keyword}")
                    
                    # Skip links with no career-related keywords
                    if score == 0:
                        continue
                    
                    # Step 3: Boost score for navigation elements
                    # Check if link is in header, footer, or nav element
                    is_in_navigation = False
                    try:
                        # Check parent elements for navigation containers
                        parent_tags = []
                        current = link
                        for _ in range(5):  # Check up to 5 levels up
                            parent = current.locator("xpath=..").first
                            if parent:
                                tag_name = parent.evaluate("el => el.tagName.toLowerCase()")
                                parent_tags.append(tag_name)
                                if tag_name in ["header", "footer", "nav"]:
                                    is_in_navigation = True
                                    break
                                current = parent
                            else:
                                break
                    except Exception as e:
                        logger.debug(f"Could not check parent elements: {e}")
                    
                    if is_in_navigation:
                        score = int(score * 1.5)  # 50% boost for navigation elements
                        logger.debug(f"Navigation boost applied to link: {text[:50]}")
                    
                    # Store scored link
                    scored_links.append({
                        "link": link,
                        "text": text,
                        "href": href,
                        "score": score,
                        "in_navigation": is_in_navigation,
                        "matched_keywords": matched_keywords
                    })
                    
                    logger.debug(
                        f"Link scored: text='{text[:50]}', href='{href[:50]}', "
                        f"score={score}, nav={is_in_navigation}, keywords={matched_keywords}"
                    )
                    
                except Exception as e:
                    logger.debug(f"Error processing link: {e}")
                    continue
            
            # Step 4: Return highest scoring link
            if not scored_links:
                logger.warning("No careers-related links found on page")
                return None
            
            # Sort by score (highest first)
            scored_links.sort(key=lambda x: x["score"], reverse=True)
            
            best_link = scored_links[0]
            logger.info(
                f"Best careers link found: text='{best_link['text'][:50]}', "
                f"href='{best_link['href'][:50]}', score={best_link['score']}, "
                f"in_navigation={best_link['in_navigation']}"
            )
            
            # Log top 3 candidates for debugging
            if len(scored_links) > 1:
                logger.debug("Top 3 candidates:")
                for i, candidate in enumerate(scored_links[:3], 1):
                    logger.debug(
                        f"  {i}. text='{candidate['text'][:40]}', "
                        f"score={candidate['score']}, keywords={candidate['matched_keywords']}"
                    )
            
            return {
                "text": best_link["text"],
                "href": best_link["href"],
                "locator": best_link["link"],
                "score": best_link["score"],
                "in_navigation": best_link["in_navigation"]
            }
            
        except Exception as e:
            logger.error(f"Error finding careers link: {e}", exc_info=True)
            return None
    
    def navigate_to_careers(self) -> bool:
        """
        Navigate from homepage to careers page.
        
        Executes the navigation by:
        1. Finding the best careers link using find_careers_link()
        2. Clicking the identified link
        3. Waiting for page load (networkidle)
        4. Verifying navigation success
        
        Validates Requirements: 1.6, 16.5, 16.6
        
        Returns:
            True if navigation successful, False otherwise
        """
        try:
            logger.info("Starting navigation from homepage to careers page")
            
            # Step 1: Find careers link
            careers_link = self.find_careers_link()
            
            if not careers_link:
                logger.warning("No careers link found, cannot navigate")
                return False
            
            # Store current URL for comparison
            current_url = self.page.url
            logger.info(f"Current URL before navigation: {current_url}")
            
            # Step 2: Click the careers link
            logger.info(
                f"Clicking careers link: text='{careers_link['text'][:50]}', "
                f"href='{careers_link['href'][:50]}'"
            )
            
            try:
                # Click and wait for navigation
                locator = careers_link["locator"]
                
                # Use expect_navigation context manager to wait for navigation
                with self.page.expect_navigation(timeout=30000):
                    locator.click()
                
                logger.info("Click executed, navigation completed")
                
            except Exception as e:
                logger.error(f"Error clicking careers link: {e}", exc_info=True)
                return False
            
            # Step 3: Wait for page load
            try:
                # Wait for network to be idle (no more than 2 network connections for at least 500ms)
                self.page.wait_for_load_state("networkidle", timeout=10000)
                logger.info("Page load completed (networkidle)")
            except Exception as e:
                # Network idle timeout is not critical, log and continue
                logger.warning(f"Network idle timeout (non-critical): {e}")
            
            # Get new URL after navigation
            new_url = self.page.url
            logger.info(f"New URL after navigation: {new_url}")
            
            # Step 4: Verify navigation success
            if new_url == current_url:
                logger.warning("URL did not change after clicking careers link")
                return False
            
            logger.info(
                f"Navigation successful: {current_url} -> {new_url}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error navigating to careers page: {e}", exc_info=True)
            return False
    
    def verify_on_careers_page(self) -> bool:
        """
        Verify that the current page is a careers page.
        
        Performs verification by:
        1. Checking URL for career-related keywords
        2. Checking page content for job listings indicators
        3. Returning boolean verification result
        
        Validates Requirements: 1.6, 16.6
        
        Returns:
            True if on careers page, False otherwise
        """
        try:
            logger.info("Verifying current page is a careers page")
            
            # Get current URL
            current_url = self.page.url.lower()
            logger.debug(f"Current URL: {current_url}")
            
            # Step 1: Check URL for career keywords
            url_has_career_keywords = False
            matched_url_keywords = []
            
            for keyword in self.career_keywords.keys():
                if keyword in current_url:
                    url_has_career_keywords = True
                    matched_url_keywords.append(keyword)
            
            if url_has_career_keywords:
                logger.info(f"URL contains career keywords: {matched_url_keywords}")
            else:
                logger.debug("URL does not contain career keywords")
            
            # Step 2: Check page content for job listings indicators
            page_has_job_listings = False
            job_listing_indicators = []
            
            try:
                # Look for common job listing indicators
                # Check for multiple job title links (indicates job board)
                job_links = self.page.locator("a[href*='job'], a[href*='position'], a[href*='opening']").count()
                if job_links >= 3:
                    page_has_job_listings = True
                    job_listing_indicators.append(f"{job_links} job links")
                    logger.debug(f"Found {job_links} job-related links")
                
                # Check for job title headings
                job_headings = self.page.locator("h1, h2, h3, h4").filter(
                    has_text="job"
                ).or_(
                    self.page.locator("h1, h2, h3, h4").filter(has_text="position")
                ).or_(
                    self.page.locator("h1, h2, h3, h4").filter(has_text="career")
                ).or_(
                    self.page.locator("h1, h2, h3, h4").filter(has_text="opening")
                ).count()
                
                if job_headings > 0:
                    page_has_job_listings = True
                    job_listing_indicators.append(f"{job_headings} job headings")
                    logger.debug(f"Found {job_headings} job-related headings")
                
                # Check for job cards or listings (common class names)
                job_cards = self.page.locator(
                    "[class*='job'], [class*='position'], [class*='opening'], [class*='career']"
                ).count()
                
                if job_cards >= 3:
                    page_has_job_listings = True
                    job_listing_indicators.append(f"{job_cards} job elements")
                    logger.debug(f"Found {job_cards} job-related elements")
                
                # Check for application form fields (indicates direct application page)
                form_fields = self.page.locator(
                    "input[type='text'], input[type='email'], input[type='file'], textarea"
                ).count()
                
                if form_fields >= 3:
                    page_has_job_listings = True
                    job_listing_indicators.append(f"{form_fields} form fields")
                    logger.debug(f"Found {form_fields} form fields (application form)")
                
            except Exception as e:
                logger.debug(f"Error checking page content: {e}")
            
            if page_has_job_listings:
                logger.info(f"Page contains job listing indicators: {job_listing_indicators}")
            else:
                logger.debug("Page does not contain job listing indicators")
            
            # Step 3: Return verification result
            # Page is verified as careers page if EITHER URL has keywords OR page has job listings
            is_careers_page = url_has_career_keywords or page_has_job_listings
            
            if is_careers_page:
                logger.info(
                    f"[OK] Verified on careers page (URL keywords: {url_has_career_keywords}, "
                    f"Job listings: {page_has_job_listings})"
                )
            else:
                logger.warning(
                    "[FAIL] Not on careers page (no URL keywords and no job listings found)"
                )
            
            return is_careers_page
            
        except Exception as e:
            logger.error(f"Error verifying careers page: {e}", exc_info=True)
            return False
