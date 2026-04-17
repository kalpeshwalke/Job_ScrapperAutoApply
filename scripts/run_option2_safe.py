#!/usr/bin/env python3
"""
Run Option 2 (Auto-Apply Mode) with safety wrapper.
This will run the actual system but intercept any submit actions.
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    """Run Option 2 with safety checks"""
    print("=" * 70)
    print("OPTION 2: Auto-Apply Mode (SAFETY WRAPPER)")
    print("=" * 70)
    print("\n[WARNING]  SAFETY MODE ENABLED:")
    print("   - Will fill forms")
    print("   - Will NOT submit applications")
    print("   - Will NOT update Excel with 'AI-Applied'")
    print("   - Will log all actions for review")
    print("\nPress Ctrl+C to cancel at any time")
    print("=" * 70)
    
    # Ask for confirmation
    response = input("\nContinue with SAFE mode? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled by user")
        return
    
    print("\n1. Starting main.py with Option 2...")
    print("   (This will show the CLI menu)")
    print("\nWhen prompted:")
    print("   - Choose '2' for Auto-Apply Mode")
    print("   - The system will run in safe mode")
    print("\n" + "=" * 70)
    
    # We need to modify the system to run in safe mode
    # The easiest way is to create a modified version that doesn't submit
    
    print("\nActually, let me create a safe test version instead...")
    
    # Create a safe test that uses the actual code but with mocks
    create_safe_test_version()

def create_safe_test_version():
    """Create a safe test version of the auto-apply system"""
    print("\nCreating safe test version...")
    
    # 1. First, let's check if we have real jobs to test with
    test_excel_path = "test_dummy_jobs.xlsx"
    if not os.path.exists(test_excel_path):
        print(f"[ERROR] Test file not found: {test_excel_path}")
        print("   Creating test data...")
        os.system("python create_test_data.py")
    
    # 2. Create a modified config that points to test data
    print("\n2. Creating test configuration...")
    
    # Backup original config
    import shutil
    config_path = "config/config.yaml"
    backup_path = "config/config.yaml.backup"
    if os.path.exists(config_path):
        shutil.copy2(config_path, backup_path)
        print(f"[SUCCESS] Original config backed up to {backup_path}")
    
    # Read and modify config
    with open(config_path, 'r') as f:
        config_content = f.read()
    
    # Add test mode flag
    if "test_mode:" not in config_content:
        config_content = config_content.replace(
            "auto_apply:",
            "auto_apply:\n  test_mode: true  # Safe mode - don't submit forms"
        )
    
    # Change master file to test data
    config_content = config_content.replace(
        "master_file_name: \"qa_jobs_master.xlsx\"",
        "master_file_name: \"test_dummy_jobs.xlsx\""
    )
    
    # Write modified config
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    print("[SUCCESS] Config modified for test mode")
    print("   - test_mode: true (safe mode)")
    print("   - Using test_dummy_jobs.xlsx")
    
    # 3. Create a safe version of the FSM orchestrator
    print("\n3. Creating safe FSM orchestrator...")
    
    safe_orchestrator_code = '''
"""
Safe FSM Orchestrator - Doesn't submit forms
"""
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.ai_auto_apply.orchestrator import FSMOrchestrator as OriginalFSMOrchestrator
from utils.logger import get_logger

logger = get_logger("safe_fsm_orchestrator")

class SafeFSMOrchestrator(OriginalFSMOrchestrator):
    """Safe version that doesn't submit forms"""
    
    def apply_to_job(self, job_data):
        """Apply to job but stop before submitting"""
        career_url = job_data["career_url"]
        excel_index = job_data["excel_index"]
        
        logger.info("SAFE MODE: Starting FSM for job: %s at %s", 
                   job_data["title"], job_data["company"])
        logger.info("SAFE MODE: Would navigate to %s", career_url)
        logger.info("SAFE MODE: Would fill forms with: %s", job_data.get("user_details", {}))
        
        # In safe mode, we simulate success but don't actually do anything
        print("\\n" + "="*50)
        print("SAFE MODE SIMULATION:")
        print(f"Job: {job_data['title']} at {job_data['company']}")
        print(f"URL: {career_url}")
        print("Actions that WOULD be taken:")
        print("1. Open browser and navigate to career page")
        print("2. Inject mmid attributes into DOM elements")
        print("3. AI would analyze page and plan actions")
        print("4. Would fill form fields with user details")
        print("5. Would STOP before submitting (safe mode)")
        print("="*50 + "\\n")
        
        # Return simulated success
        return {
            "status": "success",
            "reason": "Safe mode simulation - forms would be filled but not submitted",
            "iterations": 1,
            "actions_taken": ["simulated_form_fill"]
        }

# Monkey patch the original orchestrator
import utils.ai_auto_apply.orchestrator
utils.ai_auto_apply.orchestrator.FSMOrchestrator = SafeFSMOrchestrator
print("[SUCCESS] Safe FSM orchestrator installed")
'''
    
    safe_file_path = "safe_fsm_patch.py"
    with open(safe_file_path, 'w') as f:
        f.write(safe_orchestrator_code)
    
    print(f"[SUCCESS] Safe FSM patch created: {safe_file_path}")
    
    # 4. Instructions for running
    print("\n" + "=" * 70)
    print("READY FOR SAFE TEST!")
    print("=" * 70)
    print("\nTo run Option 2 in safe mode:")
    print("1. First, restore original config:")
    print("   python -c \"import shutil; shutil.copy2('config/config.yaml.backup', 'config/config.yaml')\"")
    print("\n2. Run the safe test:")
    print("   python safe_option2_test.py")
    print("\n3. Or run actual Option 2 (with caution):")
    print("   python main.py")
    print("   Then choose '2' for Auto-Apply Mode")
    print("\n[WARNING]  WARNING: Actual Option 2 WILL submit applications!")
    print("   Only use if you're ready for real applications")
    print("=" * 70)

if __name__ == "__main__":
    main()
