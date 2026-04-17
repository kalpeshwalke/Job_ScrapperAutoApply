"""
Create test Excel file with dummy jobs for testing Option 2 (Auto-Apply Mode).
"""

import pandas as pd
from datetime import datetime
import os

# Create test data
test_jobs = [
    {
        'title': 'Software Engineer',
        'company': 'Test Company Inc',
        'location': 'Remote',
        'experience': '2-4 years',
        'skills': 'Python, JavaScript, React',
        'salary': '$80-100k',
        'description': 'Test job description for software engineer role',
        'posted_date': '2024-01-15',
        'link': 'https://example.com/job1',
        'platform': 'LinkedIn',
        'easy_apply': 'No',
        'career_page_url': 'https://example.com/careers',
        'Career_Page_Valid': 'Yes',  # This job is valid for auto-apply
        'Applied': 'No',  # Not applied yet
        'Application Date': None,
        'Notes': '',
        'Run Status': 'Complete'
    },
    {
        'title': 'QA Engineer',
        'company': 'Testing Corp',
        'location': 'Bangalore',
        'experience': '3-5 years',
        'skills': 'Manual Testing, Selenium, API Testing',
        'salary': '₹8-12 LPA',
        'description': 'Test job description for QA engineer role',
        'posted_date': '2024-01-16',
        'link': 'https://example.com/job2',
        'platform': 'Naukri',
        'easy_apply': 'No',
        'career_page_url': 'https://testingcorp.com/careers',
        'Career_Page_Valid': 'Yes',  # This job is valid for auto-apply
        'Applied': 'No',  # Not applied yet
        'Application Date': None,
        'Notes': '',
        'Run Status': 'Complete'
    },
    {
        'title': 'Product Manager',
        'company': 'Product Co',
        'location': 'Mumbai',
        'experience': '5-7 years',
        'skills': 'Product Management, Agile, User Research',
        'salary': '₹15-20 LPA',
        'description': 'Test job description for product manager role',
        'posted_date': '2024-01-17',
        'link': 'https://example.com/job3',
        'platform': 'Indeed',
        'easy_apply': 'No',
        'career_page_url': 'https://productco.com/jobs',
        'Career_Page_Valid': 'No',  # This job is NOT valid (for testing filter)
        'Applied': 'No',
        'Application Date': None,
        'Notes': '',
        'Run Status': 'Complete'
    }
]

# Create DataFrame
df = pd.DataFrame(test_jobs)

# Save to Excel
output_path = 'test_dummy_jobs.xlsx'
df.to_excel(output_path, index=False)

print(f"[SUCCESS] Test Excel file created: {output_path}")
print(f"[DATA] Total jobs: {len(df)}")
print(f"[SUCCESS] Valid for auto-apply (Career_Page_Valid='Yes'): {len(df[df['Career_Page_Valid'] == 'Yes'])}")
print(f"[ERROR] Not valid for auto-apply: {len(df[df['Career_Page_Valid'] == 'No'])}")
print("\nJob details:")
for i, job in enumerate(test_jobs):
    print(f"  {i+1}. {job['title']} at {job['company']} - Valid: {job['Career_Page_Valid']}")
