"""
Test script to verify the auto-apply system works with a single job
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.settings import Config
from src.ai_auto_apply.core.orchestrator_v2 import FSMOrchestratorV2
from common.logger import get_logger

logger = get_logger(__name__)

def test_single_job():
    """Test auto-apply with a single job"""
    
    # Test job data
    test_job = {
        "Company": "Gururo",
        "Job Title": "QA Automation Engineer",
        "Company Career Page": "https://gururo.com/careers",
        "Location": "Bangalore",
        "Experience": "2-5 years",
        "Skills": "Selenium, Python, API Testing",
        "Platform": "Test",
        "Link": "https://gururo.com/careers"
    }
    
    print("\n" + "="*60)
    print("TESTING AUTO-APPLY SYSTEM")
    print("="*60)
    print(f"\nCompany: {test_job['Company']}")
    print(f"Job Title: {test_job['Job Title']}")
    print(f"Career URL: {test_job['Company Career Page']}")
    print("\n" + "="*60 + "\n")
    
    try:
        # Load config
        from config.settings import Config as ConfigClass
        config = ConfigClass()
        if not config._loaded:
            config.load()
        
        # Check if auto-apply is enabled
        if not config.auto_apply.get('enabled', False):
            print("⚠️  WARNING: Auto-apply is disabled in config.yaml")
            print("   Set auto_apply.enabled: true to enable it")
            return False
        
        # Check AI provider
        ai_provider = config.auto_apply.get('ai_provider', 'ollama')
        print(f"✓ AI Provider: {ai_provider}")
        
        if ai_provider == 'ollama':
            import requests
            try:
                response = requests.get('http://localhost:11434/api/tags', timeout=2)
                if response.status_code == 200:
                    print("✓ Ollama is running")
                else:
                    print("✗ Ollama is not responding correctly")
                    return False
            except Exception as e:
                print(f"✗ Ollama is not running: {e}")
                print("  Start Ollama with: ollama serve")
                return False
        
        print("\n" + "-"*60)
        print("Starting auto-apply test...")
        print("-"*60 + "\n")
        
        # Create orchestrator
        orchestrator = FSMOrchestratorV2(provider=None, config=config, excel_path="dummy.xlsx")
        
        # Apply to job
        result = orchestrator.apply_to_job(test_job)
        
        print("\n" + "="*60)
        print("TEST RESULTS")
        print("="*60)
        print(f"\nStatus: {result.get('status', 'unknown')}")
        print(f"Reason: {result.get('reason', 'No reason provided')}")
        
        if result.get('status') == 'success':
            print("\n✅ SUCCESS! Auto-apply system is working correctly!")
            return True
        else:
            print(f"\n⚠️  Application did not succeed")
            print(f"   This might be expected (e.g., login required, CAPTCHA, etc.)")
            print(f"   Check the logs for details")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    success = test_single_job()
    sys.exit(0 if success else 1)
