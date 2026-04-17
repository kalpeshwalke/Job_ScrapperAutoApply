"""
Career Page URL Validator

Validates career page URLs using HTTP checks and keyword matching.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Tuple, List
from urllib.parse import urlparse
from src.common.logger import get_logger
from src.ai_auto_apply.core.structured_logger import StructuredLogger

logger = get_logger("career_page_validator")


class CareerPageValidator:
    """Validates career page URLs using HTTP checks and keyword matching"""
    
    # Career-specific keywords to search for
    CAREER_KEYWORDS = {
        "career", "careers", "jobs", "job", "vacancies", 
        "openings", "apply", "employment", "opportunities", "hiring"
    }
    
    # Homepage indicators in URL paths
    HOMEPAGE_INDICATORS = {"", "index", "home", "index.html", "index.php", "index.htm"}
    
    def __init__(self, config: Dict):
        """
        Initialize validator with configuration.
        
        Args:
            config: Validation configuration from config.yaml
        """
        self.enabled = config.get("enabled", True)
        self.keyword_threshold = config.get("keyword_threshold", 2)
        self.timeout_seconds = config.get("timeout_seconds", 30)
        self.verify_company_name = config.get("verify_company_name", True)
        self.structured_logger = StructuredLogger("validator", config)
        
        logger.info(
            "CareerPageValidator initialized: enabled=%s, threshold=%d, timeout=%ds",
            self.enabled, self.keyword_threshold, self.timeout_seconds
        )
    
    def extract_url_path_keywords(self, url: str) -> List[str]:
        """
        Extract and normalize keywords from URL path.
        
        Args:
            url: URL to extract keywords from
            
        Returns:
            List of normalized path segments
        """
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/').lower()
            
            if not path:
                return []
            
            # Split path into segments and normalize
            segments = [seg for seg in path.split('/') if seg]
            
            # Extract keywords from segments (remove file extensions)
            keywords = []
            for segment in segments:
                # Remove common file extensions
                if '.' in segment:
                    segment = segment.rsplit('.', 1)[0]
                keywords.append(segment)
            
            return keywords
        except Exception as e:
            logger.warning("Failed to extract URL path keywords from %s: %s", url, e)
            return []
    
    def is_homepage_redirect(self, original_url: str, final_url: str) -> bool:
        """
        Check if URL redirected to homepage.
        
        Detects homepage redirects by:
        1. Comparing original URL path with final URL path
        2. Checking for homepage indicators (empty path, "/", "index", "home")
        3. Detecting when career keywords disappear from URL path
        
        Args:
            original_url: Original URL before redirects
            final_url: Final URL after following redirects
            
        Returns:
            True if redirected to homepage, False otherwise
        """
        try:
            # Parse URLs
            orig_parsed = urlparse(original_url)
            final_parsed = urlparse(final_url)
            
            # Normalize paths
            orig_path = orig_parsed.path.strip('/').lower()
            final_path = final_parsed.path.strip('/').lower()
            
            # Check if domains are different (external redirect)
            if orig_parsed.netloc != final_parsed.netloc:
                logger.debug("Different domains detected: %s -> %s", orig_parsed.netloc, final_parsed.netloc)
                return False
            
            # Check if paths are identical (no redirect)
            if orig_path == final_path:
                return False
            
            # Check if final path is a homepage indicator
            if final_path in self.HOMEPAGE_INDICATORS:
                logger.debug("Homepage indicator detected in final path: '%s'", final_path)
                return True
            
            # Check if original path had content but final path is empty
            if orig_path and not final_path:
                logger.debug("Redirected from path '%s' to root", orig_path)
                return True
            
            # Extract keywords from both paths
            orig_keywords = self.extract_url_path_keywords(original_url)
            final_keywords = self.extract_url_path_keywords(final_url)
            
            # Check if career keywords disappeared from path
            orig_has_career = any(
                any(career_kw in keyword for career_kw in self.CAREER_KEYWORDS)
                for keyword in orig_keywords
            )
            final_has_career = any(
                any(career_kw in keyword for career_kw in self.CAREER_KEYWORDS)
                for keyword in final_keywords
            )
            
            if orig_has_career and not final_has_career:
                logger.debug(
                    "Career keywords disappeared: %s -> %s",
                    orig_keywords, final_keywords
                )
                return True
            
            return False
            
        except Exception as e:
            logger.warning("Error checking homepage redirect: %s", e)
            return False
    
    def validate(self, url: str, company_name: str) -> Tuple[str, str]:
        """
        Validate a career page URL.
        
        Args:
            url: Career page URL to validate
            company_name: Company name to verify in page content
            
        Returns:
            Tuple of (validation_status, reason)
            validation_status: "Yes", "No", or "Unchecked"
            reason: Human-readable explanation
        """
        if not self.enabled:
            return ("Unchecked", "Validation disabled in config")
        
        if not url or not url.startswith("http"):
            return ("No", "Invalid URL format")
        
        try:
            # Step 1: HTTP Status Check with redirect following
            logger.debug("Validating URL: %s", url)
            response = requests.get(
                url, 
                timeout=self.timeout_seconds,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True  # Follow redirects
            )
            
            # Check for homepage redirect
            final_url = response.url
            if self.is_homepage_redirect(url, final_url):
                reason = "Homepage redirect detected - AI will navigate to careers page"
                logger.warning("Homepage redirect detected: %s -> %s", url, final_url)
                # Log with structured logger
                self.structured_logger.log_validation_result(
                    url=url,
                    company_name=company_name,
                    status="Yes",
                    reason=reason,
                    details={
                        "original_url": url,
                        "final_url": final_url,
                        "homepage_redirect": True
                    }
                )
                return ("Yes", reason)
            
            if response.status_code != 200:
                reason = f"HTTP {response.status_code}"
                logger.debug("Validation failed for %s: %s", url, reason)
                # Log with structured logger
                self.structured_logger.log_validation_result(
                    url=url,
                    company_name=company_name,
                    status="No",
                    reason=reason,
                    details={"status_code": response.status_code}
                )
                return ("No", reason)
            
            # Step 2: Keyword Matching
            soup = BeautifulSoup(response.text, 'html.parser')
            page_text = soup.get_text().lower()
            
            keyword_count = sum(
                1 for keyword in self.CAREER_KEYWORDS 
                if keyword in page_text
            )
            
            if keyword_count < self.keyword_threshold:
                reason = f"Only {keyword_count}/{self.keyword_threshold} keywords found"
                logger.debug("Validation failed for %s: %s", url, reason)
                # Log with structured logger
                self.structured_logger.log_validation_result(
                    url=url,
                    company_name=company_name,
                    status="No",
                    reason=reason,
                    details={"keyword_count": keyword_count, "threshold": self.keyword_threshold}
                )
                return ("No", reason)
            
            # Step 3: Company Name Verification (optional)
            if self.verify_company_name:
                company_lower = company_name.lower()
                # Check for company name or first word of company name
                company_first_word = company_lower.split()[0] if company_lower else ""
                
                if company_first_word and company_first_word not in page_text:
                    reason = f"Company name '{company_name}' not found in page"
                    logger.debug("Validation failed for %s: %s", url, reason)
                    # Log with structured logger
                    self.structured_logger.log_validation_result(
                        url=url,
                        company_name=company_name,
                        status="No",
                        reason=reason,
                        details={"company_first_word": company_first_word}
                    )
                    return ("No", reason)
            
            # All checks passed
            logger.info("Validation passed for %s (%d keywords found)", url, keyword_count)
            # Log with structured logger
            self.structured_logger.log_validation_result(
                url=url,
                company_name=company_name,
                status="Yes",
                reason=f"Valid ({keyword_count} keywords)",
                details={"keyword_count": keyword_count, "company_verified": self.verify_company_name}
            )
            return ("Yes", f"Valid ({keyword_count} keywords)")
            
        except requests.Timeout:
            reason = f"Timeout after {self.timeout_seconds}s"
            logger.warning("Validation timeout for %s", url)
            # Log with structured logger
            self.structured_logger.log_validation_result(
                url=url,
                company_name=company_name,
                status="Unchecked",
                reason=reason,
                details={"timeout_seconds": self.timeout_seconds}
            )
            return ("Unchecked", reason)
        
        except requests.RequestException as e:
            reason = f"Network error: {str(e)[:50]}"
            logger.warning("Validation network error for %s: %s", url, e)
            # Log with structured logger
            self.structured_logger.log_validation_result(
                url=url,
                company_name=company_name,
                status="Unchecked",
                reason=reason,
                details={"error_type": type(e).__name__}
            )
            return ("Unchecked", reason)
        
        except Exception as e:
            reason = f"Unexpected error: {str(e)[:50]}"
            logger.error("Validation unexpected error for %s: %s", url, e)
            # Log with structured logger
            self.structured_logger.log_validation_result(
                url=url,
                company_name=company_name,
                status="Unchecked",
                reason=reason,
                details={"error_type": type(e).__name__}
            )
            return ("Unchecked", reason)
    
    def validate_batch(self, jobs: list) -> Dict[str, Tuple[str, str]]:
        """
        Validate multiple career page URLs.
        
        Args:
            jobs: List of job dictionaries with 'link' and 'company' keys
            
        Returns:
            Dictionary mapping job links to (validation_status, reason) tuples
        """
        results = {}
        total = len(jobs)
        
        logger.info("Starting batch validation of %d career pages", total)
        
        for i, job in enumerate(jobs, 1):
            url = job.get("career_page_url", "")
            company = job.get("company", "")
            
            if i % 10 == 0:
                logger.info("Validation progress: %d/%d", i, total)
            
            status, reason = self.validate(url, company)
            results[url] = (status, reason)
        
        # Log summary
        valid_count = sum(1 for s, _ in results.values() if s == "Yes")
        invalid_count = sum(1 for s, _ in results.values() if s == "No")
        unchecked_count = sum(1 for s, _ in results.values() if s == "Unchecked")
        
        logger.info(
            "Batch validation complete: %d valid, %d invalid, %d unchecked",
            valid_count, invalid_count, unchecked_count
        )
        
        return results
