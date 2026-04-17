@echo off
echo ============================================
echo   Your Project Files (Clean List)
echo ============================================
echo.
echo === DOCUMENTATION (3 files) ===
if exist README.md echo   README.md
if exist HOW_TO_RUN.md echo   HOW_TO_RUN.md
if exist FINAL_SUMMARY.md echo   FINAL_SUMMARY.md
echo.
echo === RUN FILES (2 files) ===
if exist job_run_scraper.bat echo   job_run_scraper.bat
if exist setup_scheduler.bat echo   setup_scheduler.bat
echo.
echo === MAIN APPLICATION (1 file) ===
if exist main.py echo   main.py
echo.
echo === CONFIGURATION (3 files) ===
if exist config\config.yaml echo   config\config.yaml
if exist config\settings.py echo   config\settings.py
if exist config\__init__.py echo   config\__init__.py
echo.
echo === DATA MODEL (2 files) ===
if exist models\job_schema.py echo   models\job_schema.py
if exist models\__init__.py echo   models\__init__.py
echo.
echo === SCRAPERS (6 files) ===
if exist scraper\base_scraper.py echo   scraper\base_scraper.py
if exist scraper\naukri_scraper.py echo   scraper\naukri_scraper.py
if exist scraper\linkedin_scraper.py echo   scraper\linkedin_scraper.py
if exist scraper\indeed_scraper.py echo   scraper\indeed_scraper.py
if exist scraper\foundit_scraper.py echo   scraper\foundit_scraper.py
if exist scraper\__init__.py echo   scraper\__init__.py
echo.
echo === UTILITIES (11 files) ===
if exist utils\scraper_manager.py echo   utils\scraper_manager.py
if exist utils\cache_layer.py echo   utils\cache_layer.py
if exist utils\deduplication_engine.py echo   utils\deduplication_engine.py
if exist utils\browser_pool_manager.py echo   utils\browser_pool_manager.py
if exist utils\rate_limiter.py echo   utils\rate_limiter.py
if exist utils\excel_writer.py echo   utils\excel_writer.py
if exist utils\logger.py echo   utils\logger.py
if exist utils\browser.py echo   utils\browser.py
if exist utils\company_careers.py echo   utils\company_careers.py
if exist utils\filters.py echo   utils\filters.py
if exist utils\__init__.py echo   utils\__init__.py
echo.
echo === DEPENDENCIES (2 files) ===
if exist requirements.txt echo   requirements.txt
if exist .env.example echo   .env.example
echo.
echo ============================================
echo   TOTAL: 31 Essential Files
echo ============================================
echo.
echo Cache/Generated folders (can be ignored):
echo   - __pycache__/ (Python cache)
echo   - .pytest_cache/ (Test cache)
echo   - .hypothesis/ (Test data)
echo   - .kiro/ (Spec files)
echo   - data/ (Output data)
echo   - logs/ (Log files)
echo.
pause
