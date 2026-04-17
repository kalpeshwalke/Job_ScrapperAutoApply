@echo off
REM ============================================================
REM  PROJECT CLEANUP SCRIPT
REM  Removes unnecessary files and reorganizes project structure
REM ============================================================

echo.
echo ============================================================
echo  JOB SCRAPER - PROJECT CLEANUP
echo ============================================================
echo.

REM Step 1: Delete Python cache files
echo [1/6] Deleting Python cache files...
if exist __pycache__ rmdir /s /q __pycache__
if exist config\__pycache__ rmdir /s /q config\__pycache__
if exist models\__pycache__ rmdir /s /q models\__pycache__
if exist scraper\__pycache__ rmdir /s /q scraper\__pycache__
if exist utils\__pycache__ rmdir /s /q utils\__pycache__
if exist utils\ai_auto_apply\__pycache__ rmdir /s /q utils\ai_auto_apply\__pycache__
echo    Done!

REM Step 2: Delete test cache
echo [2/6] Deleting test cache files...
if exist .hypothesis rmdir /s /q .hypothesis
if exist .pytest_cache rmdir /s /q .pytest_cache
echo    Done!

REM Step 3: Clean old browser profiles (keep only main 4)
echo [3/6] Cleaning old browser profiles...
echo    Keeping: linkedin_profile, indeed_profile, foundit_profile, naukri_profile
echo    Deleting all other profiles...
cd data\profiles
for /d %%D in (*) do (
    if not "%%D"=="linkedin_profile" (
        if not "%%D"=="indeed_profile" (
            if not "%%D"=="foundit_profile" (
                if not "%%D"=="naukri_profile" (
                    rmdir /s /q "%%D" 2>nul
                )
            )
        )
    )
)
cd ..\..
echo    Done!

REM Step 4: Create tests directory structure
echo [4/6] Creating tests directory structure...
if not exist tests mkdir tests
if not exist tests\unit mkdir tests\unit
if not exist tests\property mkdir tests\property
if not exist tests\integration mkdir tests\integration
echo    Done!

REM Step 5: Move test files to tests directory
echo [5/6] Moving test files to tests directory...
move test_*.py tests\ 2>nul
echo    Done!

REM Step 6: Delete redundant documentation
echo [6/6] Cleaning up documentation...
if exist FINAL_SUMMARY.md del /q FINAL_SUMMARY.md
if exist PROJECT_CLEAN.md del /q PROJECT_CLEAN.md
if exist TASK_6_CHECKPOINT_RESULTS.md del /q TASK_6_CHECKPOINT_RESULTS.md
echo    Done!

echo.
echo ============================================================
echo  CLEANUP COMPLETE!
echo ============================================================
echo.
echo Summary:
echo  - Deleted Python cache files
echo  - Deleted test cache (.hypothesis, .pytest_cache)
echo  - Cleaned old browser profiles
echo  - Organized test files into tests/ directory
echo  - Removed redundant documentation
echo.
echo Next steps:
echo  1. Review CLEANUP_REPORT.md for details
echo  2. Run: python -m pytest tests/ to verify tests still work
echo  3. Commit changes to git
echo.
pause
