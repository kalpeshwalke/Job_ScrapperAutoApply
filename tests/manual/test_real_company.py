import sys
from pathlib import Path
import os
import pandas as pd
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import Config
from src.ai_auto_apply.core.orchestrator_v2 import FSMOrchestratorV2
from src.ai_auto_apply.providers.ai_provider import AIProviderFactory

print("\n" + "="*60)
print(" [*] LIVE REAL-WORLD TEST (SUBMIT DISABLED)")
print("="*60 + "\n")

# Load Config
config = Config.load()
auto_apply = config.auto_apply_config

# Force headless but disable strict validation and apply limits
auto_apply['browser'] = auto_apply.get('browser', {})
auto_apply['browser']['headless'] = False  # Let's show the user what's happening
auto_apply['validation'] = auto_apply.get('validation', {})
auto_apply['validation']['enabled'] = False

# Read Jobs
excel_path = config.master_file_path
print(f"[*] Reading jobs from: {excel_path}")

try:
    df = pd.read_excel(excel_path)
    # Filter identical to main.py
    df_valid = df[(df['Career_Page_Valid'] == 'Yes') & (df['Applied'] == 'No')].copy()
    
    # Map columns to ensure we don't hit Unknown mapping faults
    column_mapping = {
        'Job Title': 'title',
        'Job_Title': 'title',
        'Company Career Page': 'career_page_url',
        'Careers_URL': 'career_page_url',
        'company': 'company',
        'Company': 'company',
    }
    df_valid.rename(columns=column_mapping, inplace=True)
    
except Exception as e:
    print(f"[!] Failed to read Excel: {e}")
    sys.exit(1)

if len(df_valid) == 0:
    print("[!] No valid jobs found in Excel. Run Scraping Mode first.")
    sys.exit(1)

# Pick first 2 target jobs
target_jobs = df_valid.head(2)
print(f"[*] Found {len(df_valid)} valid jobs. Testing on first {len(target_jobs)}.\n")

# Provider init
provider = AIProviderFactory.create_provider(auto_apply)
print(f"[*] Provider created: {type(provider).__name__}")
print(f"[*] AI Model: {auto_apply.get('ai_model')}\n")

# Run Orchestrator
orchestrator = FSMOrchestratorV2(provider, auto_apply, excel_path)

try:
    for idx, row in target_jobs.iterrows():
        job_data = {
            'title': row.get('title', ''),
            'company': row.get('company', ''),
            'career_url': row.get('career_page_url', ''),
            'excel_index': idx,
            'user_details': auto_apply.get('user_details', {}),
            'resume_path': auto_apply.get('resume_path', '')
        }
        
        print("\n" + "="*60)
        print(f"Testing Job: {job_data['title']} at {job_data['company']}")
        print(f"URL: {job_data['career_url']}")
        print("="*60)
        
        result = orchestrator.apply_to_job(job_data)
        
        print("\n" + "-"*60)
        print(f"Job Test Result: {result.get('status').upper()}")
        print(f"Reason: {result.get('reason')}")
        print("-"*60 + "\n")
        
        time.sleep(2)

except KeyboardInterrupt:
    print("\n[!] Test interrupted by user.")
finally:
    print("[*] Closing browser session.")
    orchestrator.close_browser()
    print("[*] Test complete.")
