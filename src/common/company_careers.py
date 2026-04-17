"""
Company careers page finder — searches for company career pages using Google.
"""

import re
import time
from typing import Optional

import requests
from src.common.logger import get_logger

logger = get_logger("company_careers")

# Cache to avoid repeated searches for the same company
_CAREER_PAGE_CACHE = {}


def find_company_career_page(company_name: str, driver=None) -> str:
    """
    Find the career/jobs page URL for a company.
    
    Args:
        company_name: Name of the company
        driver: Optional Selenium WebDriver instance (reuse existing browser)
        
    Returns:
        Career page URL or empty string if not found
    """
    if not company_name or not isinstance(company_name, str):
        return ""
    
    company_clean = company_name.strip()
    if not company_clean:
        return ""
    
    # Check cache first
    if company_clean in _CAREER_PAGE_CACHE:
        return _CAREER_PAGE_CACHE[company_clean]
    
    try:
        # Try to construct common career page patterns first (fast)
        career_url = _try_common_patterns(company_clean)
        if career_url:
            _CAREER_PAGE_CACHE[company_clean] = career_url
            return career_url
        
        # If we have a browser instance, use it for Google search
        if driver:
            logger.debug("Pattern matching failed for %s, trying Google search with existing browser...", company_clean)
            career_url = _search_via_google_with_browser(company_clean, driver)
            _CAREER_PAGE_CACHE[company_clean] = career_url
            return career_url
        
        # No browser available, return empty
        _CAREER_PAGE_CACHE[company_clean] = ""
        return ""
        
    except Exception as e:
        logger.debug("Failed to find career page for %s: %s", company_clean, e)
        _CAREER_PAGE_CACHE[company_clean] = ""
        return ""


def _try_common_patterns(company_name: str) -> str:
    """
    Try common career page URL patterns.
    
    Common patterns:
    - company.com/careers
    - company.com/jobs
    - careers.company.com
    - jobs.company.com
    """
    # Clean company name for domain
    domain_name = re.sub(r'[^a-zA-Z0-9]', '', company_name.lower())
    
    # Skip very short names (likely abbreviations)
    if len(domain_name) < 3:
        return ""
    
    # Common company domain mappings (manually curated for better accuracy)
    domain_mappings = {
        # Indian IT giants
        'tcs': 'tata.com',
        'infosys': 'infosys.com',
        'wipro': 'wipro.com',
        'hcl': 'hcltech.com',
        'hcltech': 'hcltech.com',
        'techm': 'techmahindra.com',
        'techmahindra': 'techmahindra.com',
        'ltimindtree': 'ltimindtree.com',
        'cognizant': 'cognizant.com',
        'mindtree': 'ltimindtree.com',
        'lti': 'ltimindtree.com',
        
        # Global companies
        'accenture': 'accenture.com',
        'ibm': 'ibm.com',
        'microsoft': 'microsoft.com',
        'amazon': 'amazon.jobs',
        'google': 'careers.google.com',
        'meta': 'metacareers.com',
        'facebook': 'metacareers.com',
        'apple': 'apple.com',
        'oracle': 'oracle.com',
        'sap': 'sap.com',
        'cisco': 'cisco.com',
        'intel': 'intel.com',
        'dell': 'dell.com',
        'hp': 'hp.com',
        'adobe': 'adobe.com',
        'salesforce': 'salesforce.com',
        'vmware': 'vmware.com',
        
        # Banks & Financial
        'barclays': 'barclays.com',
        'jpmorgan': 'jpmorgan.com',
        'goldmansachs': 'goldmansachs.com',
        'morganstanley': 'morganstanley.com',
        'citi': 'citi.com',
        'hsbc': 'hsbc.com',
        'standardchartered': 'sc.com',
        'deutschebank': 'db.com',
        
        # Consulting
        'deloitte': 'deloitte.com',
        'pwc': 'pwc.com',
        'ey': 'ey.com',
        'kpmg': 'kpmg.com',
        'capgemini': 'capgemini.com',
        
        # Others
        'rockwellautomation': 'rockwellautomation.com',
        'siemens': 'siemens.com',
        'bosch': 'bosch.com',
        'ge': 'ge.com',
        'honeywell': 'honeywell.com',
    }
    
    # Use mapping if available
    base_domain = domain_mappings.get(domain_name, f"{domain_name}.com")
    
    patterns = [
        f"https://{base_domain}/careers",
        f"https://{base_domain}/jobs",
        f"https://careers.{base_domain}",
        f"https://www.{base_domain}/careers",
        f"https://www.{base_domain}/jobs",
    ]
    
    # Try each pattern with a quick HEAD request
    for url in patterns:
        try:
            response = requests.head(url, timeout=2, allow_redirects=True)
            # Accept 200 (OK) or 403 (Forbidden - site exists but blocks HEAD requests)
            if response.status_code in [200, 403]:
                logger.debug("Found career page via pattern: %s", url)
                return url
        except Exception:
            continue
    
    return ""


def _search_via_google(company_name: str) -> str:
    """
    Search Google for company career page using DrissionPage.
    """
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
        
        options = ChromiumOptions()
        options.headless()
        options.set_argument('--disable-gpu')
        options.set_argument('--no-sandbox')
        options.set_argument('--disable-dev-shm-usage')
        
        page = None
        try:
            page = ChromiumPage(options)
            
            query = f'{company_name} career page'
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            page.get(search_url)
            
            page.wait.ele_loaded("css:div#search", timeout=5)
            
            result_links = []
            
            h3_elements = page.eles("tag:h3")
            for h3 in h3_elements:
                try:
                    parent_link = h3.parent()
                    if parent_link.tag.lower() == 'a':
                        result_links.append(parent_link)
                except Exception:
                    pass
            
            if not result_links:
                result_links = page.eles("css:div.g a[href^='http']")
            
            if not result_links:
                result_links = page.eles("css:div#search a[href^='http']")
            
            career_keywords = ['career', 'job', 'hiring', 'work-with-us', 'join-us', 'opportunities', 'recruitment']
            skip_domains = ['google.com', 'youtube.com', 'facebook.com', 'twitter.com', 'naukri.com', 'linkedin.com', 'indeed.com', 'glassdoor.com']
            
            for link in result_links[:10]:
                try:
                    url = link.attr('href')
                    if not url or not url.startswith('http'):
                        continue
                    
                    url_lower = url.lower()
                    
                    if any(domain in url_lower for domain in skip_domains):
                        continue
                    
                    if any(keyword in url_lower for keyword in career_keywords):
                        clean_url = url.split('#')[0].split('?')[0]
                        logger.debug("Found career page via Google (DrissionPage): %s", clean_url)
                        return clean_url
                        
                except Exception:
                    continue
            
            return ""
            
        finally:
            if page:
                try:
                    page.quit()
                except Exception:
                    pass
                    
    except Exception as e:
        logger.debug("Google search (DrissionPage) failed for %s: %s", company_name, e)
        return ""


def _search_via_google_with_browser(company_name: str, driver) -> str:
    """
    Search Google using an existing DrissionPage instance.
    Much faster than creating a new browser each time.
    """
    try:
        from DrissionPage import ChromiumPage
        
        tab = None
        try:
            query = f'{company_name} career page'
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            
            tab = driver.new_tab(search_url)
            
            time.sleep(2)
            
            result_links = []
            try:
                h3_elements = tab.eles("tag:h3")
                for h3 in h3_elements[:10]:
                    try:
                        parent_link = h3.parent()
                        if parent_link.tag.lower() == 'a':
                            result_links.append(parent_link)
                    except Exception:
                        pass
            except Exception:
                pass
            
            career_keywords = ['career', 'job', 'hiring', 'work-with-us', 'join-us', 'opportunities', 'recruitment']
            skip_domains = ['google.com', 'youtube.com', 'facebook.com', 'twitter.com', 'naukri.com', 'linkedin.com', 'indeed.com', 'glassdoor.com']
            
            for link in result_links:
                try:
                    url = link.attr('href')
                    if not url or not url.startswith('http'):
                        continue
                    
                    url_lower = url.lower()
                    
                    if any(domain in url_lower for domain in skip_domains):
                        continue
                    
                    if any(keyword in url_lower for keyword in career_keywords):
                        clean_url = url.split('#')[0].split('?')[0]
                        logger.debug("Found career page via Google (reused DrissionPage): %s", clean_url)
                        
                        tab.close()
                        return clean_url
                        
                except Exception:
                    continue
            
            tab.close()
            return ""
            
        except Exception as e:
            if tab:
                try:
                    tab.close()
                except Exception:
                    pass
            raise e
                    
    except Exception as e:
        logger.debug("Google search (reused DrissionPage) failed for %s: %s", company_name, e)
        return ""


def batch_find_career_pages(companies: list[str], delay: float = 1.0) -> dict[str, str]:
    """
    Find career pages for multiple companies with rate limiting.
    
    Args:
        companies: List of company names
        delay: Delay between searches in seconds
        
    Returns:
        Dictionary mapping company name to career page URL
    """
    results = {}
    
    for i, company in enumerate(companies):
        if not company:
            continue
            
        logger.info("Finding career page %d/%d: %s", i + 1, len(companies), company)
        career_url = find_company_career_page(company)
        results[company] = career_url
        
        # Rate limiting
        if i < len(companies) - 1:
            time.sleep(delay)
    
    return results
