@echo off
title Cloudflare Worker Deployment - WhatsApp Bulk Messenger
cd /d "%~dp0"

echo ============================================================
echo      Deploy WhatsApp Update Server to Cloudflare Workers
echo ============================================================
echo.

echo [1/2] Checking Cloudflare Authentication...
call npx.cmd wrangler whoami >nul 2>&1
if errorlevel 1 (
    echo [INFO] You are not logged into Cloudflare yet.
    echo A browser window will now open for you to log in to Cloudflare.
    echo.
    call npx.cmd wrangler login
    if errorlevel 1 (
        echo.
        echo [ERROR] Cloudflare login failed or was cancelled.
        pause
        exit /b 1
    )
)

echo.
echo [2/2] Deploying Worker to Cloudflare edge network...
call npx.cmd wrangler deploy

if errorlevel 1 (
    echo.
    echo [ERROR] Deployment failed. Please check the logs above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [SUCCESS] Cloudflare Worker deployed successfully!
echo You can copy your worker URL (e.g. https://whatsapp-bulk-updater.xxx.workers.dev)
echo and paste it into update_config.json as "custom_endpoint".
echo ============================================================
echo.
pause

