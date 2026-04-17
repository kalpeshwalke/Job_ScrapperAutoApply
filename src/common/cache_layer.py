"""
Cache layer with SQLite for persistent job data storage.

This module provides a CacheLayer class that stores job data persistently
across daily runs to reduce redundant requests and improve performance.

Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from src.common.logger import get_logger

logger = get_logger(__name__)


class CacheLayer:
    """
    Persistent cache layer using SQLite for job data storage.
    
    Stores job IDs, URLs, composite hashes, and full job data with TTL support.
    Validates: Requirements 6.1, 6.2, 6.3, 6.4
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the cache layer with SQLite database.
        
        Args:
            db_path: Path to SQLite database file. Defaults to data/cache.db
        """
        if db_path is None:
            # Default to data/cache.db in project root
            project_root = Path(__file__).resolve().parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "cache.db"
        
        self.db_path = db_path
        self._init_database()
        logger.info(f"CacheLayer initialized with database: {self.db_path}")
    
    def _init_database(self):
        """Create the jobs table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create jobs table with schema:
        # id, url, composite_hash, data_json, created_at, ttl
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                composite_hash TEXT,
                data_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                ttl INTEGER NOT NULL
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_url ON jobs(url)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_composite_hash ON jobs(composite_hash)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at)
        """)
        
        conn.commit()
        conn.close()
        logger.debug("Database schema initialized")
    
    def store(self, job: Dict[str, Any], ttl: int = 3600, composite_hash: Optional[str] = None):
        """
        Store a job in the cache with TTL.
        
        Args:
            job: Job data dictionary (must contain 'link' field)
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)
            composite_hash: Optional composite hash for deduplication
        
        Raises:
            ValueError: If job doesn't contain 'link' field
        """
        if "link" not in job:
            raise ValueError("Job must contain 'link' field")
        
        url = job["link"]
        data_json = json.dumps(job)
        created_at = time.time()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Use INSERT OR REPLACE to handle duplicates
            cursor.execute("""
                INSERT OR REPLACE INTO jobs (url, composite_hash, data_json, created_at, ttl)
                VALUES (?, ?, ?, ?, ?)
            """, (url, composite_hash, data_json, created_at, ttl))
            
            conn.commit()
            logger.debug(f"Stored job in cache: {url} (TTL: {ttl}s)")
        except sqlite3.Error as e:
            logger.error(f"Failed to store job in cache: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def query_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Query cache by job URL.
        
        Args:
            url: Job URL to query
        
        Returns:
            Job data dictionary if found and not expired, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT data_json, created_at, ttl FROM jobs WHERE url = ?
        """, (url,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            logger.debug(f"Cache miss for URL: {url}")
            return None
        
        data_json, created_at, ttl = result
        
        # Check if entry is expired
        if self._is_expired_entry(created_at, ttl):
            logger.debug(f"Cache entry expired for URL: {url}")
            return None
        
        logger.debug(f"Cache hit for URL: {url}")
        return json.loads(data_json)
    
    def query_by_hash(self, composite_hash: str) -> List[Dict[str, Any]]:
        """
        Query cache by composite hash.
        
        Args:
            composite_hash: Composite hash to query
        
        Returns:
            List of job data dictionaries (non-expired entries only)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT data_json, created_at, ttl FROM jobs WHERE composite_hash = ?
        """, (composite_hash,))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            logger.debug(f"Cache miss for hash: {composite_hash}")
            return []
        
        # Filter out expired entries
        jobs = []
        for data_json, created_at, ttl in results:
            if not self._is_expired_entry(created_at, ttl):
                jobs.append(json.loads(data_json))
        
        if jobs:
            logger.debug(f"Cache hit for hash: {composite_hash} ({len(jobs)} jobs)")
        else:
            logger.debug(f"All cache entries expired for hash: {composite_hash}")
        
        return jobs
    
    def is_expired(self, entry: Dict[str, Any]) -> bool:
        """
        Check if a cache entry is expired.
        
        Args:
            entry: Cache entry dictionary with 'created_at' and 'ttl' fields
        
        Returns:
            True if expired, False otherwise
        """
        if "created_at" not in entry or "ttl" not in entry:
            logger.warning("Cache entry missing created_at or ttl fields")
            return True
        
        return self._is_expired_entry(entry["created_at"], entry["ttl"])
    
    def _is_expired_entry(self, created_at: float, ttl: int) -> bool:
        """
        Internal method to check if an entry is expired.
        
        Args:
            created_at: Unix timestamp when entry was created (float for precision)
            ttl: Time-to-live in seconds
        
        Returns:
            True if expired, False otherwise
        """
        current_time = time.time()
        expiration_time = created_at + ttl
        return current_time > expiration_time
    
    def clear_expired(self) -> int:
        """
        Remove all expired entries from the cache.
        
        Returns:
            Number of entries removed
        """
        current_time = time.time()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete entries where created_at + ttl <= current_time
        cursor.execute("""
            DELETE FROM jobs WHERE (created_at + ttl) <= ?
        """, (current_time,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            logger.info(f"Cleared {deleted_count} expired cache entries")
        
        return deleted_count
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics (total_entries, expired_entries)
        """
        current_time = time.time()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total entries
        cursor.execute("SELECT COUNT(*) FROM jobs")
        total_entries = cursor.fetchone()[0]
        
        # Expired entries
        cursor.execute("""
            SELECT COUNT(*) FROM jobs WHERE (created_at + ttl) <= ?
        """, (current_time,))
        expired_entries = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "active_entries": total_entries - expired_entries
        }
    
    def clear_all(self):
        """Clear all entries from the cache (for testing purposes)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs")
        conn.commit()
        conn.close()
        logger.info("Cleared all cache entries")
