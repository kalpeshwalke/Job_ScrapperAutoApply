#!/usr/bin/env python3
"""
Cleanup Project Utility

This script purges temporary files, cache folders, and test artifacts
to keep the Job Scrapper project clean and professional.
"""

import os
import shutil
from pathlib import Path

def cleanup():
    project_root = Path(__file__).resolve().parent.parent
    
    # 1. Directories to purge (recursive)
    purge_dirs = [
        "__pycache__",
        ".pytest_cache",
        ".hypothesis",
        ".ipynb_checkpoints"
    ]
    
    # 2. Specific folders to clear contents of
    clear_folders = [
        "logs"
    ]
    
    # 3. File patterns to delete in data/output
    output_dir = project_root / "data" / "output"
    
    print(f"--- Starting Cleanup at {project_root} ---")
    
    # Purge cache directories
    for p_dir in purge_dirs:
        for path in project_root.rglob(p_dir):
            if path.is_dir():
                print(f"Removing cache directory: {path.relative_to(project_root)}")
                shutil.rmtree(path, ignore_errors=True)
                
    # Clear logs
    for log_sec in clear_folders:
        log_path = project_root / log_sec
        if log_path.exists() and log_path.is_dir():
            print(f"Clearing logs in: {log_path.relative_to(project_root)}")
            for log_file in log_path.glob("*.log"):
                log_file.unlink()
                
    # Purge test output files
    if output_dir.exists():
        print(f"Purging test artifacts in: data/output")
        for test_file in output_dir.glob("test_*.xlsx"):
            print(f"  - Deleting {test_file.name}")
            test_file.unlink()
            
    print("\n--- Project Cleanup Complete! ---")

if __name__ == "__main__":
    cleanup()
