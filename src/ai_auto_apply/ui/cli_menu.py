"""
CLI Menu System

Interactive command-line menu for selecting execution mode.
"""

from typing import Literal
from src.common.logger import get_logger

logger = get_logger("cli_menu")


class CLIMenu:
    """Interactive CLI menu for mode selection"""
    
    @staticmethod
    def display_menu() -> Literal["scraping", "apply"]:
        """
        Display interactive menu and get user selection.
        
        Returns:
            "scraping" for Option 1, "apply" for Option 2
        """
        print("\n" + "=" * 60)
        print("  JOB SCRAPER - EXECUTION MODE SELECTION")
        print("=" * 60)
        print("\nPlease select an execution mode:\n")
        print("  [1] Scraping Mode")
        print("      - Scrape jobs from enabled platforms")
        print("      - Validate career page URLs")
        print("      - Save results to Excel")
        print("      - Preserves all anti-bot delays\n")
        print("  [2] Auto-Apply Mode")
        print("      - Load existing scraped jobs from Excel")
        print("      - Apply to validated career pages using AI")
        print("      - No artificial delays between applications")
        print("      - Requires AI API key configured\n")
        print("=" * 60)
        
        while True:
            try:
                choice = input("\nEnter your choice (1 or 2): ").strip()
                
                if choice == "1":
                    logger.info("User selected: Scraping Mode")
                    print("\n[*] Starting Scraping Mode...\n")
                    return "scraping"
                
                elif choice == "2":
                    logger.info("User selected: Auto-Apply Mode")
                    print("\n[*] Starting Auto-Apply Mode...\n")
                    return "apply"
                
                else:
                    print("[!] Invalid choice. Please enter 1 or 2.")
                    logger.debug("Invalid menu choice: %s", choice)
            
            except KeyboardInterrupt:
                print("\n\n[!] Operation cancelled by user")
                logger.info("Menu selection cancelled by user")
                raise
            
            except Exception as e:
                print(f"[!] Error reading input: {e}")
                logger.error("Menu input error: %s", e)
