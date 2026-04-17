@echo off
REM ============================================================
REM  Job Scraper — One-Click Runner
REM  Double-click this file to start scraping!
REM ============================================================

title Job Scraper - Running...
color 0A

echo.
echo  ============================================
echo   Job Scraper - Starting...
echo  ============================================
echo.

REM --- Change to script directory ---
cd /d "%~dp0"

REM --- Check Python is available ---
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  [ERROR] Python is not installed or not in PATH!
    echo  Please install Python 3.10+ from https://python.org
    echo.
    pause
    exit /b 1
)

REM --- Check if dependencies are installed ---
python -c "import DrissionPage, pandas, openpyxl, yaml, dotenv" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  [INFO] Installing dependencies...
    echo.
    pip install -r requirements.txt
    echo.
    if %ERRORLEVEL% NEQ 0 (
        echo  [ERROR] Failed to install dependencies!
        pause
        exit /b 1
    )
    echo  [OK] Dependencies installed.
    echo.
)

REM --- Run the scraper ---
echo  [START] Running job scraper...
echo  ============================================
echo.
python main.py

echo.
echo  ============================================
if %ERRORLEVEL% EQU 0 (
    echo  [DONE] Scraping completed successfully!
    echo.
    echo  Output file: data\output\qa_jobs_master.xlsx
) else (
    echo  [ERROR] Scraping finished with errors.
    echo  Check logs\scraper_%date:~-4%-%date:~4,2%-%date:~7,2%.log
)
echo  ============================================
echo.
pause
