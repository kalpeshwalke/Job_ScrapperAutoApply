"""
Deduplication engine for identifying and removing duplicate jobs across platforms.

This module provides a DeduplicationEngine class that uses composite hashing
to identify duplicate jobs posted on multiple platforms and retains the most
complete job data.

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8
"""

import hashlib
import re
from typing import List, Dict, Any, Tuple

from src.common.logger import get_logger

logger = get_logger(__name__)


class DeduplicationEngine:
    """
    Deduplication engine using composite hash for cross-platform duplicate detection.
    
    Generates composite hashes from:
    - Lowercase company name
    - Alphanumeric-only job title
    - Normalized location (city extraction)
    - Experience range bucketing (0-2, 3-5, 6-10, 11+)
    
    Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8
    """
    
    # Experience range buckets
    EXPERIENCE_BUCKETS = {
        (0, 2): "0-2",
        (3, 5): "3-5",
        (6, 10): "6-10",
        (11, float('inf')): "11+"
    }
    
    def __init__(self):
        """Initialize the deduplication engine."""
        logger.info("DeduplicationEngine initialized")
    
    def generate_composite_hash(self, job: Dict[str, Any]) -> str:
        """
        Generate composite hash for a job.
        
        Hash components:
        1. Lowercase company name
        2. Alphanumeric-only job title (lowercase)
        3. Normalized location (city extraction, lowercase)
        4. Experience range bucket
        
        Args:
            job: Job data dictionary with company, title, location, experience fields
        
        Returns:
            SHA256 hash string
        
        Validates: Requirement 5.1
        """
        # Extract and normalize components
        company = self._normalize_company(job.get("company", ""))
        title = self._normalize_title(job.get("title", ""))
        location = self._normalize_location(job.get("location", ""))
        experience_range = self._bucket_experience(job.get("experience", ""))
        
        # Concatenate components
        composite_string = f"{company}|{title}|{location}|{experience_range}"
        
        # Generate SHA256 hash
        hash_obj = hashlib.sha256(composite_string.encode('utf-8'))
        composite_hash = hash_obj.hexdigest()
        
        logger.debug(f"Generated hash for: {composite_string} -> {composite_hash[:16]}...")
        
        return composite_hash
    
    def _normalize_company(self, company: str) -> str:
        """
        Normalize company name to lowercase.
        
        Args:
            company: Company name string
        
        Returns:
            Lowercase company name
        """
        return company.strip().lower()
    
    def _normalize_title(self, title: str) -> str:
        """
        Normalize job title to alphanumeric-only lowercase.
        
        Removes all non-alphanumeric characters and converts to lowercase.
        
        Args:
            title: Job title string
        
        Returns:
            Alphanumeric-only lowercase title
        """
        # Remove all non-alphanumeric characters (keep only letters, numbers, spaces)
        alphanumeric_only = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        # Convert to lowercase and strip whitespace
        return alphanumeric_only.strip().lower()
    
    def _normalize_location(self, location: str) -> str:
        """
        Normalize location by extracting city name and converting to lowercase.
        
        Handles formats like:
        - "Bangalore, Karnataka" -> "bangalore"
        - "Bengaluru, KA" -> "bengaluru"
        - "New York, NY" -> "new york"
        - "Remote" -> "remote"
        
        Args:
            location: Location string
        
        Returns:
            Normalized city name in lowercase
        
        Validates: Requirement 5.2
        """
        if not location:
            return ""
        
        # Split by comma and take the first part (city)
        parts = location.split(',')
        city = parts[0].strip().lower()
        
        return city
    
    def _bucket_experience(self, experience: str) -> str:
        """
        Bucket years of experience into ranges.
        
        Ranges:
        - 0-2 years
        - 3-5 years
        - 6-10 years
        - 11+ years
        
        Args:
            experience: Experience string (e.g., "2-5 years", "3 years", "5+")
        
        Returns:
            Experience range bucket string
        
        Validates: Requirement 5.3
        """
        if not experience:
            return "unknown"
        
        # Extract numeric values from experience string
        numbers = re.findall(r'\d+', experience)
        
        if not numbers:
            return "unknown"
        
        # Use the first number as the experience value
        # For ranges like "2-5", we use the lower bound
        years = int(numbers[0])
        
        # Find the appropriate bucket
        for (min_years, max_years), bucket_label in self.EXPERIENCE_BUCKETS.items():
            if min_years <= years <= max_years:
                return bucket_label
        
        return "unknown"
    
    def deduplicate(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate jobs using composite hash.
        
        When duplicates are detected:
        1. Group jobs by composite hash
        2. Retain the job with the most complete data (most non-empty fields)
        3. Preserve the Platform field
        
        Args:
            jobs: List of job dictionaries
        
        Returns:
            Deduplicated list of jobs
        
        Validates: Requirements 5.4, 5.5, 5.6
        """
        if not jobs:
            return []
        
        # Group jobs by composite hash
        hash_groups: Dict[str, List[Dict[str, Any]]] = {}
        
        for job in jobs:
            composite_hash = self.generate_composite_hash(job)
            
            if composite_hash not in hash_groups:
                hash_groups[composite_hash] = []
            
            hash_groups[composite_hash].append(job)
        
        # Resolve duplicates by retaining the most complete job
        deduplicated_jobs = []
        duplicate_count = 0
        
        for composite_hash, job_group in hash_groups.items():
            if len(job_group) == 1:
                # No duplicates for this hash
                deduplicated_jobs.append(job_group[0])
            else:
                # Duplicates detected - retain the most complete job
                duplicate_count += len(job_group) - 1
                most_complete_job = self._select_most_complete(job_group)
                deduplicated_jobs.append(most_complete_job)
                
                logger.debug(
                    f"Duplicate detected: {len(job_group)} jobs with hash {composite_hash[:16]}... "
                    f"Retained job from platform: {most_complete_job.get('platform', 'unknown')}"
                )
        
        logger.info(
            f"Deduplication complete: {len(jobs)} jobs -> {len(deduplicated_jobs)} unique jobs "
            f"({duplicate_count} duplicates removed)"
        )
        
        return deduplicated_jobs
    
    def _select_most_complete(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Select the most complete job from a list of duplicates.
        
        Completeness is measured by the number of non-empty fields.
        
        Args:
            jobs: List of duplicate job dictionaries
        
        Returns:
            The job with the most non-empty fields
        
        Validates: Requirement 5.5
        """
        if not jobs:
            raise ValueError("Cannot select from empty job list")
        
        if len(jobs) == 1:
            return jobs[0]
        
        # Calculate completeness score for each job
        def completeness_score(job: Dict[str, Any]) -> int:
            """Count non-empty fields in a job."""
            score = 0
            for key, value in job.items():
                if value and str(value).strip() and str(value).strip().lower() not in ["", "n/a", "none"]:
                    score += 1
            return score
        
        # Find the job with the highest completeness score
        most_complete_job = max(jobs, key=completeness_score)
        
        return most_complete_job
    
    def detect_duplicates(self, jobs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Detect duplicate jobs without removing them.
        
        Returns a dictionary mapping composite hashes to lists of duplicate jobs.
        
        Args:
            jobs: List of job dictionaries
        
        Returns:
            Dictionary mapping composite hash to list of duplicate jobs
        
        Validates: Requirement 5.4
        """
        hash_groups: Dict[str, List[Dict[str, Any]]] = {}
        
        for job in jobs:
            composite_hash = self.generate_composite_hash(job)
            
            if composite_hash not in hash_groups:
                hash_groups[composite_hash] = []
            
            hash_groups[composite_hash].append(job)
        
        # Filter to only include groups with duplicates
        duplicates = {
            hash_val: job_list
            for hash_val, job_list in hash_groups.items()
            if len(job_list) > 1
        }
        
        logger.info(f"Detected {len(duplicates)} duplicate groups across {len(jobs)} jobs")
        
        return duplicates
