"""
Quick test runner for the hallucination fix.
This will run auto-apply on just the first job (Gururo) for testing.
"""

import sys
import pandas as pd
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    print("=" * 70)
    print("HALLUCINATION FIX - REAL COMPANY TEST")
    print("=" * 70)
    
    # Check Excel file
    excel_path = "data/output/qa_jobs_master.xlsx"
    if not Path(excel_path).exists():
        print(f"❌ Excel file not found: {excel_path}")
        return
    
    df = pd.read_excel(excel_path)
    ready = df[(df['Career_Page_Valid'] == 'Yes') & (df['Applied'] == 'No')]
    
    print(f"\n✅ Found {len(ready)} jobs ready for auto-apply")
    print(f"\nFirst job to test:")
    first_job = ready.iloc[0]
    print(f"  Company: {first_job['Company']}")
    print(f"  Title: {first_job['Job Title']}")
    print(f"  Career Page: {first_job['Company Career Page']}")
    
    print("\n" + "=" * 70)
    print("WHAT TO WATCH FOR:")
    print("=" * 70)
    print("✅ GOOD: System uses only these tools:")
    print("   - click_element, enter_text, select_option")
    print("   - upload_file, press_key, navigate")
    print("\n❌ BAD: System tries to use hallucinated tools:")
    print("   - apply_for_job, custom_search_engine, etc.")
    print("\n✅ CORRECTION: If hallucination occurs:")
    print("   - System logs: 'Hallucination detected (count: X)'")
    print("   - Injects correction message with valid tools")
    print("   - Retries with correct tools")
    print("\n❌ FAIL-FAST: If 3 consecutive hallucinations:")
    print("   - System terminates with clear error message")
    print("   - Returns hallucination_count in result")
    
    print("\n" + "=" * 70)
    print("STARTING AUTO-APPLY MODE...")
    print("=" * 70 + "\n")
    
    # Import and run main
    from main import execute_apply_mode
    from config.settings import Config
    
    config = Config()
    execute_apply_mode(config)

if __name__ == "__main__":
    main()
