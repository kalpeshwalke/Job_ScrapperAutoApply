"""
Test script to run auto-apply on a single company from the Excel sheet.
"""

import sys
import pandas as pd
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Config
from src.common.logger import get_logger
from src.ai_auto_apply.providers.ai_provider import AIProviderFactory
from src.ai_auto_apply.core.orchestrator import FSMOrchestrator

logger = get_logger("test_single_company")


def test_single_company():
    """Test auto-apply on a single company."""
    print("\n" + "=" * 60)
    print("[*] TESTING AUTO-APPLY ON SINGLE COMPANY")
    print("=" * 60 + "\n")
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = Config.load()
        auto_apply_config = config.auto_apply_config
        
        # Load Excel file
        logger.info("Loading Excel file: %s", config.master_file_path)
        df = pd.read_excel(config.master_file_path)
        
        # Filter for jobs that haven't been applied to
        filtered_df = df[df['Applied'] == 'No'].copy()
        
        if len(filtered_df) == 0:
            print("[!] No jobs available for testing")
            return
        
        # Pick the first company (Gururo)
        test_job = filtered_df.iloc[0]
        
        print(f"\n[*] Testing with:")
        print(f"    Company: {test_job['Company']}")
        print(f"    Title: {test_job['Job Title']}")
        print(f"    Career Page: {test_job['Company Career Page']}")
        print()
        
        # Initialize AI provider
        ai_provider_name = auto_apply_config.get('ai_provider', 'gemini')
        ai_model = auto_apply_config.get('ai_model', 'gemini-2.0-flash-exp')
        
        logger.info("Initializing AI provider: %s (%s)", ai_provider_name, ai_model)
        print(f"[*] Using AI provider: {ai_provider_name} ({ai_model})")
        
        provider = AIProviderFactory.create_provider(config=auto_apply_config)
        
        # Validate provider
        if not provider.validate_availability():
            logger.error("AI provider validation failed")
            print("[!] AI provider validation failed")
            return
        
        logger.info("AI provider initialized successfully")
        
        # Initialize FSM orchestrator
        logger.info("Initializing FSM orchestrator...")
        orchestrator = FSMOrchestrator(
            provider=provider,
            config=auto_apply_config,
            excel_path=config.master_file_path
        )
        
        # Prepare job data
        job_data = {
            'title': test_job['Job Title'],
            'company': test_job['Company'],
            'career_url': test_job['Company Career Page'],
            'excel_index': test_job.name,  # DataFrame index
            'user_details': auto_apply_config.get('user_details', {})
        }
        
        # Add resume path if configured
        resume_path = auto_apply_config.get('resume_path', '')
        if resume_path:
            job_data['resume_path'] = resume_path
        
        print(f"\n[*] Starting auto-apply process...")
        print("=" * 60)
        
        # Execute FSM for this job
        result = orchestrator.apply_to_job(job_data)
        
        # Print result
        print("\n" + "=" * 60)
        print("  RESULT")
        print("=" * 60)
        print(f"  Status: {result['status']}")
        print(f"  Reason: {result.get('reason', 'N/A')}")
        print("=" * 60)
        
        logger.info("Test completed with status: %s", result['status'])
        
        # Cleanup
        orchestrator.close()
        
    except Exception as e:
        logger.error("Test failed: %s", e, exc_info=True)
        print(f"\n[!] Test failed: {e}")


if __name__ == "__main__":
    test_single_company()
