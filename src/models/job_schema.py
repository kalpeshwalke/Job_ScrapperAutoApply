"""
Unified job data schema for all platform scrapers.

This module defines the JobSchema Pydantic model that enforces
consistent data structure across all scraping platforms.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class JobSchema(BaseModel):
    """
    Unified job data schema enforced across all platform scrapers.
    
    All scrapers must return job data conforming to this schema.
    Validates: Requirements 4.1, 4.2, 4.3, 4.4
    """
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    # Required fields
    title: str = Field(..., min_length=1, description="Job title")
    company: str = Field(..., min_length=1, description="Company name")
    location: str = Field(..., min_length=1, description="Job location")
    description: str = Field(default="", description="Job description")
    platform: str = Field(..., min_length=1, description="Source platform (e.g., Naukri, LinkedIn, Indeed)")
    link: str = Field(..., min_length=1, description="Job posting URL")
    posted_date: str = Field(default="", description="Date job was posted")
    
    # Optional fields
    experience: str = Field(default="", description="Required experience (e.g., '2-5 years')")
    skills: str = Field(default="", description="Required skills (comma-separated)")
    salary: str = Field(default="", description="Salary information")
    easy_apply: str = Field(default="N/A", description="Easy apply availability")
    
    @field_validator("title", "company", "location", "platform", "link")
    @classmethod
    def validate_required_not_empty(cls, v: str, info) -> str:
        """Validate that required string fields are not empty after stripping."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v.strip()
    
    @field_validator("link")
    @classmethod
    def validate_link_format(cls, v: str) -> str:
        """Validate that link is a valid URL."""
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("link must be a valid HTTP/HTTPS URL")
        return v
    
    @field_validator("platform")
    @classmethod
    def validate_platform_name(cls, v: str) -> str:
        """Validate and normalize platform name."""
        v = v.strip()
        # Normalize common platform names
        platform_map = {
            "naukri": "Naukri",
            "linkedin": "LinkedIn",
            "indeed": "Indeed",
            "foundit": "Foundit",
            "monster": "Foundit",  # Monster India is now Foundit
        }
        return platform_map.get(v.lower(), v)
    
    def to_dict(self) -> dict:
        """Convert JobSchema to dictionary format for backward compatibility."""
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "experience": self.experience,
            "skills": self.skills,
            "salary": self.salary,
            "description": self.description,
            "posted_date": self.posted_date,
            "link": self.link,
            "platform": self.platform,
            "easy_apply": self.easy_apply,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "JobSchema":
        """Create JobSchema from dictionary, handling missing optional fields."""
        return cls(
            title=data.get("title", ""),
            company=data.get("company", ""),
            location=data.get("location", ""),
            description=data.get("description", ""),
            platform=data.get("platform", ""),
            link=data.get("link", ""),
            posted_date=data.get("posted_date", ""),
            experience=data.get("experience", ""),
            skills=data.get("skills", ""),
            salary=data.get("salary", ""),
            easy_apply=data.get("easy_apply", "N/A"),
        )
