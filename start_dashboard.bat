@echo off
title WhatsApp Bulk Messenger Pro - Modern Web Dashboard
cd /d "%~dp0"

echo ============================================================
echo   🚀 WhatsApp Bulk Messenger Pro - Modern Web Dashboard
echo ============================================================
echo.
echo [INFO] Starting web server on http://localhost:8000 ...
echo [INFO] Your default web browser will open automatically.
echo.

:: 1. Check Python installation
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in your system PATH.
    echo Please run run.bat first to install Python automatically.
    pause
    exit /b 1
)

:: 2. Fast package check
python -c "import fastapi, uvicorn, selenium, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing required packages...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

:: 3. Launch Web Dashboard directly and open browser
python web_run.py

if errorlevel 1 (
    echo.
    echo [INFO] Web dashboard exited with code %ERRORLEVEL%.
    pause
)
exit /b 0

