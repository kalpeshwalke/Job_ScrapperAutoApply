@echo off
REM ============================================================
REM  Job Scraper — Quick Launcher (Root Directory)
REM  This is a shortcut to scripts/job_run_scraper.bat
REM ============================================================

REM Change to the directory where this batch file is located
cd /d "%~dp0"

REM Call the actual batch file in the scripts folder
call scripts\job_run_scraper.bat
