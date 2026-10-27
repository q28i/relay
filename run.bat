@echo off
title WhatsApp Bulk Messenger Pro - 1-Click Runner
cd /d "%~dp0"

echo ============================================================
echo          WhatsApp Bulk Messenger Pro - 1-Click Runner
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
echo [INFO] Verifying dependencies (selenium, openpyxl, tksheet)...
python -c "import selenium, openpyxl, tksheet" >nul 2>&1
if errorlevel 1 goto :install_deps
goto :launch_app

:install_deps
echo [INFO] Installing required packages...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo.
    pause
    exit /b 1
)

:launch_app
echo [OK] Launching WhatsApp Bulk Messenger Pro...
echo.
python run.py %*

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
