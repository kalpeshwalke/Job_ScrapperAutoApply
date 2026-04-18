"""Quick test of auto-apply with Gururo"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import Config
from src.ai_auto_apply.core.orchestrator_v2 import FSMOrchestratorV2
from src.ai_auto_apply.providers.ai_provider import AIProviderFactory

import os
dummy_path = os.path.abspath(os.path.join(Path(__file__).parent, "dummy.html"))
job = {
    "company": "Dummy Corp",
    "title": "QA Automation Engineer",
    "career_url": f"file:///{dummy_path.replace(chr(92), '/')}",
    "Location": "Local",
    "excel_index": 0
}

print(f"\n{'='*60}")
print(f"Testing: {job['company']} - {job['title']}")
print(f"URL: {job['career_url']}")
print(f"{'='*60}\n")

# Load config
config = Config.load()
auto_apply = config.auto_apply_config
print(f"AI Provider: {auto_apply.get('ai_provider')}")
print(f"AI Model: {auto_apply.get('ai_model')}\n")

# Force headless for testing
auto_apply['browser'] = auto_apply.get('browser', {})
auto_apply['browser']['headless'] = True

# Disable validation for local testing
auto_apply['validation'] = auto_apply.get('validation', {})
auto_apply['validation']['enabled'] = False

# Create AI provider
provider = AIProviderFactory.create_provider(auto_apply)
print(f"Provider created: {type(provider).__name__}\n")

# Create orchestrator and test
excel_path = Path("data/output/qa_jobs_master.xlsx")
orchestrator = FSMOrchestratorV2(provider, auto_apply, excel_path)
print("Orchestrator created. Starting test...\n")

result = orchestrator.apply_to_job(job)

print(f"\n{'='*60}")
print(f"Result: {result.get('status')}")
print(f"Reason: {result.get('reason')}")
print(f"{'='*60}\n")
