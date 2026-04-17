@echo off
REM ============================================================
REM  Job Scraper — Windows Task Scheduler Setup
REM  Run this script as Administrator to create a daily task.
REM ============================================================

echo.
echo ========================================
echo  Job Scraper - Task Scheduler Setup
echo ========================================
echo.

REM --- Configuration ---
set TASK_NAME=JobScraper_Daily
set PYTHON_PATH=python
set SCRIPT_DIR=%~dp0
set SCRIPT_PATH=%SCRIPT_DIR%main.py
set SCHEDULE_TIME=08:00

echo Task Name:    %TASK_NAME%
echo Script:       %SCRIPT_PATH%
echo Schedule:     Daily at %SCHEDULE_TIME%
echo.

REM --- Remove existing task (if any) ---
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

REM --- Create new scheduled task ---
schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" ^
    /SC DAILY ^
    /ST %SCHEDULE_TIME% ^
    /RL HIGHEST ^
    /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Task created successfully!
    echo    Name: %TASK_NAME%
    echo    Time: %SCHEDULE_TIME% daily
    echo.
    echo To modify: Open Task Scheduler ^> %TASK_NAME%
    echo To delete: schtasks /Delete /TN "%TASK_NAME%" /F
) else (
    echo.
    echo [ERROR] Failed to create task.
    echo    Try running this script as Administrator.
)

echo.
pause
