"""
FastAPI Application Entry Point.
Initializes middleware, registers REST and WebSocket routers, mounts static assets,
and serves the Single Page Application dashboard.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.database import db
from backend.routers import (
    contacts,
    templates,
    campaigns,
    jobs,
    config,
    browser,
    logs,
    ws,
    media,
    collections,
    sets
)
from logger import get_logger

logger = get_logger("FastAPIApp")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and graceful shutdown."""
    logger.info("WhatsApp Automation Web Backend starting up...")
    db.log_event("INFO", "System", "Web dashboard server initialized on http://127.0.0.1:8000")

    # Intelligent startup sequence: restore working Relay session and reuse healthy browser processes
    try:
        from browser_manager import BrowserManager
        from backend.connection_monitor import connection_monitor
        from backend.session_lifecycle import session_lifecycle
        from config_manager import ConfigManager

        pref = db.get_browser_profile_preference()
        auto_connect = bool(pref.get("auto_connect", 0)) if pref else False
        mode = pref.get("selected_automation_mode") or pref.get("connection_mode") or "dedicated"
        last_conn = pref.get("last_connected_session", {})

        target_b = "chrome"
        target_p = "__dedicated__"
        target_name = "Relay Automation Session"
        is_dedicated = True

        if mode == "existing_profile":
            pers_prof = pref.get("preferred_personal_profile") or {}
            cand_b = pers_prof.get("browser") or pref.get("browser_id", "chrome")
            cand_p = pers_prof.get("profile_dir") or pref.get("canonical_profile_dir", "Profile 10")
            cand_name = pers_prof.get("profile_name") or pref.get("profile_display_name", "whatsapp auto")

            is_supp, _, _ = BrowserManager.is_profile_automation_supported(cand_b, profile_dir=cand_p, is_dedicated=False)
            if is_supp:
                target_b = cand_b
                target_p = cand_p
                target_name = cand_name
                is_dedicated = False
            else:
                logger.info(f"Personal profile '{cand_name}' cannot be automated under Chromium security rules. Preserving preference, but directing automation to supported Relay session.")
                target_b = last_conn.get("browser") or "chrome"
                target_p = last_conn.get("profile_dir") or "__dedicated__"
                target_name = last_conn.get("profile_name") or "Relay Automation Session"
                is_dedicated = (target_p == "__dedicated__")
        else:
            target_b = last_conn.get("browser") or "chrome"
            target_p = last_conn.get("profile_dir") or "__dedicated__"
            target_name = last_conn.get("profile_name") or "Relay Automation Session"
            is_dedicated = (target_p == "__dedicated__")

        # Synchronize in-memory config and config.json with target automation session
        cm = ConfigManager()
        cfg = cm.get_config()
        cfg.browser = target_b
        cfg.profile_dir = target_p
        cfg.profile_name = target_name
        cm.save_config(cfg)

        # Check session directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if target_p == "__dedicated__":
            target_path = os.path.join(base_dir, "whatsapp_browser_session")
        else:
            b_info = BrowserManager.BROWSERS.get(target_b, {})
            target_path = os.path.join(b_info.get("user_data_path", ""), target_p)
        os.makedirs(target_path, exist_ok=True)

        # Detect whether a healthy Relay-owned browser is already running
        running_diag = BrowserManager.diagnose_profile(target_b, profile_dir=target_p, is_dedicated=is_dedicated)
        has_running_relay = running_diag.get("availability") == "active_in_relay" or (
            running_diag.get("conflict_type") == "relay_owned" and bool(running_diag.get("matching_pids"))
        )

        connection_monitor.update_profile_selection(
            browser_key=target_b,
            profile_dir=target_p,
            profile_name=target_name,
            is_dedicated=is_dedicated
        )

        if has_running_relay:
            logger.info(f"Found running Relay-owned browser process for {target_name}. Attaching and reusing session...")
            connection_monitor.start_monitoring(
                browser_key=target_b,
                profile_dir=target_p,
                profile_name=target_name,
                headless=False,
                force_restart=False
            )
        elif auto_connect:
            logger.info(f"Auto-connect enabled: launching persistent session for {target_name} ({target_p})...")
            connection_monitor.start_monitoring(
                browser_key=target_b,
                profile_dir=target_p,
                profile_name=target_name,
                headless=False,
                force_restart=False
            )
        else:
            logger.info(f"Relay initialized with target session: {target_name} ({target_p}). Ready to start session.")
    except Exception as e:
        logger.warning(f"Could not complete intelligent startup: {e}")

    yield
    logger.info("WhatsApp Automation Web Backend shutting down...")
    db.log_event("INFO", "System", "Web dashboard server stopped")


app = FastAPI(
    title="WhatsApp Bulk Messenger Pro - Web Dashboard API",
    description="Modern, intelligent REST and WebSocket API for WhatsApp automation, contacts management, and campaign staging.",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Configure CORS restricted to localhost origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    """Ensure browsers do not serve stale cached static frontend files or HTML."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static") or path == "/" or path.endswith(".html") or path.endswith(".js") or path.endswith(".css"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

from starlette.exceptions import HTTPException as StarletteHTTPException

# Global API Exception Handler for structured JSON errors
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict):
        content = dict(exc.detail)
        if "detail" not in content and "message" in content:
            content["detail"] = content["message"]
        return JSONResponse(status_code=exc.status_code, content=content)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred. Please check server logs.", "error": str(exc)}
    )

# Register REST & WebSocket API Routers
app.include_router(contacts.router)
app.include_router(templates.router)
app.include_router(campaigns.router)
app.include_router(jobs.router)
app.include_router(config.router)
app.include_router(browser.router)
app.include_router(logs.router)
app.include_router(ws.router)
app.include_router(media.router)
app.include_router(collections.router)
app.include_router(sets.router)


@app.get("/api/health", tags=["Health"])
def health_check():
    """Health check endpoint verifying API service status and database connectivity."""
    kpis = db.get_overview_kpis()
    return {
        "status": "healthy",
        "version": "2.0.0",
        "database": "connected",
        "total_contacts": kpis["total_contacts"],
        "active_jobs": 0
    }


# Mount static assets directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serves a clean SVG favicon preventing 404 logs."""
    svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>"""
    return Response(content=svg_icon, media_type="image/svg+xml")


@app.get("/", include_in_schema=False)
def serve_dashboard_spa():
    """Serves the Single Page Application index.html."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    return {"message": "WhatsApp Automation API is running. Access interactive docs at /api/docs"}

