@echo off
title WhatsApp Bulk Messenger Pro - 1-Click Runner
cd /d "%~dp0"

echo ============================================================
echo      WhatsApp Bulk Messenger Pro - Web Dashboard v2.0
echo ============================================================
echo.

:: 1. Check Python installation
where python >nul 2>&1
if errorlevel 1 goto :no_python
goto :check_dependencies

:no_python
echo [INFO] Python was not found on your system.
echo [INFO] Starting automated Python installation...
echo.

where winget >nul 2>&1
if errorlevel 1 goto :curl_install

echo Installing Python via Windows Package Manager...
winget install -e --id Python.Python.3.12 --scope currentuser --accept-package-agreements --accept-source-agreements
goto :verify_python

:curl_install
echo Downloading official Python installer via curl...
curl -L -o python_installer.exe "https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe"
if not exist python_installer.exe goto :install_failed

echo Running silent installation...
python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
timeout /t 10 /nobreak >nul
del python_installer.exe

:verify_python
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo [WARNING] Python installation finished, but PATH is not updated in this session.
    echo Please close this window and double-click run.bat again.
    echo.
    pause
    exit /b 0
)

:check_dependencies
echo [INFO] Verifying packages (fastapi, uvicorn, selenium, openpyxl)...
python -c "import fastapi, uvicorn, selenium, openpyxl" >nul 2>&1
if errorlevel 1 goto :install_deps
goto :launch_menu

:install_deps
echo [INFO] Installing required dependencies from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo.
    pause
    exit /b 1
)

:launch_menu
if not "%~1"=="" (
    :: Arguments supplied directly from command line
    python web_run.py %*
    goto :end
)

echo.
echo Select interface:
echo   [1] Modern Web Dashboard (Default - Recommended)
echo   [2] CLI Dry-Run Simulation
echo   [3] CLI Pre-Flight Validation
echo   [4] Legacy Desktop GUI (Tkinter)
echo.

choice /c 1234 /t 3 /d 1 /m "Auto-launching Web Dashboard in 3 seconds (or choose 1-4)"
set "choice=%errorlevel%"

if "%choice%"=="4" (
    echo [INFO] Launching Legacy Desktop GUI...
    python gui.py
    goto :end
)

if "%choice%"=="3" (
    echo [INFO] Running CLI Pre-Flight Validation...
    python run.py --validate
    pause
    goto :end
)

if "%choice%"=="2" (
    echo [INFO] Running CLI Dry-Run simulation...
    python run.py --dry-run
    pause
    goto :end
)

echo [OK] Launching Modern Web Dashboard...
python web_run.py

:end
if errorlevel 1 (
    echo.
    echo [INFO] Application exited with code %ERRORLEVEL%.
    pause
)

exit /b 0

:install_failed
echo.
echo [ERROR] Could not download Python installer.
echo Please install Python manually from https://www.python.org/downloads/
echo and make sure to check "Add Python to PATH".
echo.
pause
exit /b 1
