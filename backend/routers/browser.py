"""
Browser Automation and Profile Management API Router.
Provides a unified, contract-compliant interface for detecting local browsers,
discovering profiles, inspecting availability, probing session health honestly,
managing dedicated sessions, and launching interactive profile windows.

Contract endpoints:
- GET  /api/browser-profiles           (and /api/browser/profiles, /api/browser/browsers)
- GET  /api/browser-profile/selection  (and /api/browser/connection, /api/browser/session)
- PUT  /api/browser-profile/selection  (and POST /api/browser-profile/selection, POST /api/browser/select)
- POST /api/browser-profile/dedicated  (and POST /api/browser/disconnect, POST /api/browser/dedicated)
- POST /api/browser-profile/open       (and POST /api/browser/open)
- POST /api/browser-profile/test       (and POST /api/browser/test, GET /api/browser/test)
- POST /api/browser-profile/test-send  (and POST /api/browser/test-send)
"""

import os
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Body, Response

from browser_manager import BrowserManager
from config_manager import ConfigManager
from backend.models import (
    ProfileSelectRequest,
    BrowserPreferenceUpdateRequest,
    TestSendRequest,
    ConnectionActionRequest,
    BrowserConflictConfirmRequest,
    SessionStartRequest
)
from backend.connection_monitor import connection_monitor, ConnectionState
from data_loader import DataLoader
from backend.database import db
from logger import get_logger

logger = get_logger("BrowserRouter")
router = APIRouter(tags=["Browser Profile"])

# Global shared browser adapter instance
_browser_adapter = None


def get_browser_adapter():
    global _browser_adapter
    if _browser_adapter is None:
        from backend.adapter import WhatsAppWebAdapter
        _browser_adapter = WhatsAppWebAdapter()
    return _browser_adapter


def _build_structured_error(code: str, message: str, action: str) -> Dict[str, str]:
    return {
        "code": code,
        "message": message,
        "action": action,
        "detail": message
    }


# ==============================================================================
# 1. BROWSER PROFILES DISCOVERY
# ==============================================================================

@router.get("/api/browser-profiles")
@router.get("/api/browser-profile")
@router.get("/api/browser/profiles")
@router.get("/api/browser/profile")
@router.get("/api/browser/browsers")
def list_browser_profiles(browser: Optional[str] = None):
    """
    Discovers installed browsers and their user profiles locally on Windows.
    Returns shortened paths and honest availability states without reading sensitive data.
    If no browsers are found, returns a helpful fallback rather than a 404 error.
    """
    installed = BrowserManager.get_installed_browsers()
    cfg = ConfigManager().get_config()
    cur_browser = getattr(cfg, "browser", "chrome") or "chrome"
    cur_profile = getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"

    # Check remembered database preferences
    pref = db.get_browser_profile_preference()
    if pref and pref.get("remember_profile", 1) and cur_profile == "__dedicated__":
        pref_b = pref.get("browser_id")
        pref_p = pref.get("canonical_profile_dir")
        if pref_b and pref_p:
            cur_browser = pref_b
            cur_profile = pref_p

    browser_list = []
    total_profiles_count = 0

    for key, info in BrowserManager.BROWSERS.items():
        is_inst = key in installed
        raw_profiles = BrowserManager.get_profiles(key) if is_inst else []
        
        # Annotate profiles with selection status
        annotated_profiles = []
        for p in raw_profiles:
            is_selected = (key == cur_browser and p["dir"] == cur_profile)
            p_copy = dict(p)
            p_copy["is_selected"] = is_selected
            p_copy["browser"] = key
            p_copy["display_availability"] = "Selected" if is_selected else (p.get("availability") or "available").replace("_", " ").title()
            annotated_profiles.append(p_copy)

        total_profiles_count += len(annotated_profiles)
        browser_list.append({
            "key": key,
            "name": info["name"],
            "installed": is_inst,
            "driver_type": info.get("driver_type", key),
            "profiles": annotated_profiles,
            "total_profiles": len(annotated_profiles)
        })

    # If single browser filtered
    if isinstance(browser, str) and browser.strip():
        b_clean = browser.strip().lower()
        target_b = next((b for b in browser_list if b["key"] == b_clean), None)
        if not target_b:
            return {
                "browser": browser,
                "profiles": [],
                "message": f"Browser '{browser}' is not installed."
            }
        return {
            "browser": browser,
            "profiles": target_b["profiles"],
            "total_profiles": len(target_b["profiles"])
        }

    # If no installed browsers found on the machine
    if not installed:
        return {
            "browsers": [],
            "profiles": [],
            "total_browsers": 0,
            "total_profiles": 0,
            "selection": get_browser_selection(),
            "message": "No browser profiles were found. You can create a dedicated local session and sign in with QR code."
        }

    return {
        "browsers": browser_list,
        "total_browsers": len([b for b in browser_list if b["installed"]]),
        "total_profiles": total_profiles_count,
        "selection": get_browser_selection(),
        "message": f"Discovered {len(installed)} installed browser(s)."
    }


# ==============================================================================
# 2. CURRENT SELECTION
# ==============================================================================

@router.get("/api/browser-profile/selection")
@router.get("/api/browser/connection")
@router.get("/api/browser/session")
def get_browser_selection():
    """
    Returns the currently active messaging browser, profile, and honest status.
    Cleanly separates saved_config, active_session, connection_health, and pending_transition.
    Restores remembered user preferences from database on restart without silently defaulting to dedicated session.
    """
    cm = ConfigManager()
    cfg = cm.get_config()
    adapter = get_browser_adapter()
    is_active = (
        adapter._browser_mgr is not None and
        adapter._engine is not None and
        getattr(adapter._engine, "driver", None) is not None
    )

    pref = db.get_browser_profile_preference()
    b_key = getattr(cfg, "browser", "chrome") or "chrome"
    p_dir = getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"
    p_name = getattr(cfg, "profile_name", "Dedicated WhatsApp Session") or "Dedicated WhatsApp Session"

    # Restore from persistent preference if configured to remember and currently unassigned or default
    if pref and pref.get("remember_profile", 1):
        pref_b = pref.get("browser_id")
        pref_p = pref.get("canonical_profile_dir")
        pref_name = pref.get("profile_display_name")
        if pref_b and pref_p and (p_dir == "__dedicated__" or not getattr(cfg, "profile_dir", None)):
            b_key = pref_b
            p_dir = pref_p
            p_name = pref_name or p_dir
            cfg.browser = b_key
            cfg.profile_dir = p_dir
            cfg.profile_name = p_name
            cm.save_config(cfg)

    is_dedicated = (p_dir == "__dedicated__")
    b_info = BrowserManager.BROWSERS.get(b_key, {})
    b_name = b_info.get("name", b_key.title())

    # Pre-flight diagnosis for honest availability
    diag = BrowserManager.diagnose_profile(
        b_key,
        profile_dir=p_dir,
        is_dedicated=is_dedicated
    )

    exists_on_disk = diag.get("condition") not in ("MISSING_EXECUTABLE", "PROFILE_PATH_INVALID")
    availability = diag.get("availability", "available")
    is_locked = diag.get("is_locked", False)
    is_stale = diag.get("is_stale_lock", False)
    lock_state = "locked" if is_locked else ("stale_lock" if is_stale else "available")

    if not exists_on_disk:
        status = "Profile unavailable"
    elif is_locked:
        status = "Profile in use"
    elif availability == "active_in_relay":
        status = "Active in Relay"
    elif availability == "browser_running":
        status = "Browser running"
    elif is_stale:
        status = "Stale lock detected"
    else:
        status = getattr(cfg, "connection_status", "Not checked") or "Not checked"
        if status == "Profile in use" and not is_locked:
            status = "Not checked"

    mode = "dedicated" if is_dedicated else "existing_profile"
    is_selected = bool(p_dir and (status != "Not checked" or is_dedicated or pref is not None))

    saved_config = {
        "browser": b_key,
        "browser_name": b_name,
        "profile_dir": p_dir,
        "profile_name": p_name,
        "mode": mode,
        "is_dedicated": is_dedicated,
        "remember_profile": bool(pref.get("remember_profile", 1) if pref else True),
        "auto_connect": bool(pref.get("auto_connect", 0) if pref else False),
        "last_selected_at": pref.get("last_selected_at") if pref else None,
        "last_connected_at": pref.get("last_connected_at") if pref else None,
        "exists_on_disk": exists_on_disk,
        "safe_error_reason": diag.get("safe_error_reason", "")
    }

    active_session = {
        "is_active": is_active or connection_monitor.is_connected(),
        "has_driver": connection_monitor.get_driver() is not None,
        "browser": connection_monitor._browser_key,
        "profile_dir": connection_monitor._profile_dir,
        "is_dedicated": connection_monitor._is_dedicated
    }

    live_mon = connection_monitor.get_live_status()
    connection_health = {
        "state": live_mon.get("state", "browser_closed"),
        "health_state": live_mon.get("health_state", "not_started"),
        "status": status,
        "availability": availability,
        "is_locked": is_locked,
        "lock_state": lock_state,
        "can_send": connection_monitor.is_connected(),
        "last_checked_at": live_mon.get("last_checked_at")
    }

    pers_pref = pref.get("preferred_personal_profile") if pref else None
    if pers_pref:
        pers_b = pers_pref.get("browser", "chrome")
        pers_p = pers_pref.get("profile_dir", "Profile 10")
        pers_name = pers_pref.get("profile_name", "whatsapp auto")
        pers_supp = pers_pref.get("is_supported", False)
        pers_reason = pers_pref.get("unsupported_reason", "")
        preferred_profile = {
            "browser": pers_b,
            "browser_name": BrowserManager.BROWSERS.get(pers_b, {}).get("name", pers_b.title()),
            "profile_dir": pers_p,
            "profile_name": pers_name,
            "is_supported": pers_supp,
            "unsupported_reason": pers_reason
        }
    else:
        preferred_profile = {
            "browser": b_key,
            "browser_name": b_name,
            "profile_dir": p_dir,
            "profile_name": p_name,
            "is_supported": diag.get("is_automation_supported", True),
            "unsupported_reason": diag.get("safe_error_reason", "") if not diag.get("is_automation_supported", True) else ""
        }

    return {
        # Structured separation
        "preferred_profile": preferred_profile,
        "saved_config": saved_config,
        "active_session": active_session,
        "connection_health": connection_health,
        "pending_transition": None,
        # Flat legacy keys for full frontend backward compatibility
        "browser": b_key,
        "browser_name": b_name,
        "profile_dir": p_dir,
        "profile_name": p_name,
        "status": status,
        "active_session": is_active or connection_monitor.is_connected(),
        "is_selected": is_selected,
        "is_dedicated": is_dedicated,
        "mode": mode,
        "is_locked": is_locked,
        "lock_state": lock_state,
        "availability": availability,
        "exists_on_disk": exists_on_disk,
        "remember_profile": bool(pref.get("remember_profile", 1) if pref else True),
        "auto_connect": bool(pref.get("auto_connect", 0) if pref else False)
    }


# ==============================================================================
# 3. SELECT AND SAVE PROFILE
# ==============================================================================

@router.put("/api/browser-profile/selection")
@router.post("/api/browser-profile/selection")
@router.post("/api/browser/select")
@router.post("/api/browser/profile/select")
def select_browser_profile(payload: ProfileSelectRequest):
    """
    Saves an explicit selected browser and profile for messaging.
    Validates existence, requires owner confirmation, updates database persistence, and closes previous sessions.
    """
    if not payload.owner_confirmed:
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "CONFIRMATION_REQUIRED",
                "Account owner confirmation is required.",
                "Please confirm that you own this browser profile before selecting it."
            )
        )

    # Check browser exists
    installed = BrowserManager.get_installed_browsers()
    b_key = payload.browser.lower()
    if b_key not in BrowserManager.BROWSERS:
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "BROWSER_NOT_SUPPORTED",
                f"Browser '{payload.browser}' is not supported.",
                "Choose one of: Chrome, Edge, Brave, or Firefox."
            )
        )

    if b_key not in installed:
        b_name = BrowserManager.BROWSERS[b_key]["name"]
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "BROWSER_NOT_FOUND",
                f"{b_name} was not found on this computer.",
                "Choose another installed browser or create a dedicated session."
            )
        )

    # Check profile exists
    profiles = BrowserManager.get_profiles(b_key)
    target = next((p for p in profiles if p["dir"] == payload.profile_dir), None)
    if not target:
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "PROFILE_NOT_FOUND",
                f"Profile '{payload.profile_dir}' was not found for {BrowserManager.BROWSERS[b_key]['name']}.",
                "Select a discovered profile or choose the Dedicated WhatsApp Session."
            )
        )

    # Close any running adapter
    adapter = get_browser_adapter()
    try:
        adapter.close()
    except Exception:
        pass

    cm = ConfigManager()
    cfg = cm.get_config()
    cfg.browser = b_key
    cfg.profile_dir = payload.profile_dir
    cfg.profile_name = payload.profile_name or target.get("name", payload.profile_dir)
    is_dedicated = (cfg.profile_dir == "__dedicated__")

    is_locked = False
    if not is_dedicated and target.get("availability") == "in_use":
        is_locked = True
        cfg.connection_status = "Profile in use"
    else:
        cfg.connection_status = "Not checked"

    cm.save_config(cfg)
    connection_monitor.stop_monitoring()
    connection_monitor.update_profile_selection(
        browser_key=b_key,
        profile_dir=cfg.profile_dir,
        profile_name=cfg.profile_name,
        is_dedicated=is_dedicated
    )

    b_info = BrowserManager.BROWSERS.get(b_key, {})
    b_name = b_info.get("name", b_key.title())

    # Save to persistent database preferences table
    db.save_browser_profile_preference(
        browser_id=b_key,
        browser_family=b_info.get("driver_type", b_key),
        browser_exe_path=b_info.get("exe_path", ""),
        profile_display_name=cfg.profile_name,
        canonical_profile_dir=cfg.profile_dir,
        connection_mode="dedicated" if is_dedicated else "existing_profile",
        remember_profile=payload.remember_profile,
        auto_connect=payload.auto_connect
    )

    logger.info(f"Updated messaging connection: {b_key} -> {cfg.profile_name} ({cfg.profile_dir}) [remember={payload.remember_profile}, auto_connect={payload.auto_connect}]")

    sel_dict = {
        "browser": cfg.browser,
        "browser_name": b_name,
        "profile_dir": cfg.profile_dir,
        "profile_name": cfg.profile_name,
        "status": cfg.connection_status,
        "is_selected": True,
        "is_dedicated": is_dedicated,
        "mode": "dedicated" if is_dedicated else "existing_profile",
        "is_locked": is_locked,
        "lock_state": "locked" if is_locked else "available",
        "remember_profile": payload.remember_profile,
        "auto_connect": payload.auto_connect
    }

    return {
        "success": True,
        "message": f"Selected {cfg.profile_name} ({b_name}).",
        "selection": sel_dict,
        "connection": sel_dict
    }


# ==============================================================================
# 3B. PREFERENCES ENDPOINT
# ==============================================================================

@router.get("/api/browser-profile/preferences")
def get_browser_preferences():
    """Returns stored browser profile preferences."""
    pref = db.get_browser_profile_preference()
    return {
        "success": True,
        "preferences": pref
    }


@router.post("/api/browser-profile/preferences")
@router.patch("/api/browser-profile/preferences")
def update_browser_preferences(payload: BrowserPreferenceUpdateRequest):
    """Updates persistent browser profile preferences (remember_profile, auto_connect)."""
    pref = db.get_browser_profile_preference()
    rem = payload.remember_profile if payload.remember_profile is not None else bool(pref.get("remember_profile", 1) if pref else True)
    auto = payload.auto_connect if payload.auto_connect is not None else bool(pref.get("auto_connect", 0) if pref else False)
    b_id = payload.browser or (pref.get("browser_id") if pref else "chrome")
    p_dir = payload.profile_dir or (pref.get("canonical_profile_dir") if pref else "Profile 10")
    p_name = payload.profile_name or (pref.get("profile_display_name") if pref else "whatsapp auto")

    b_info = BrowserManager.BROWSERS.get(b_id, {})
    db.save_browser_profile_preference(
        browser_id=b_id,
        browser_family=b_info.get("driver_type", b_id),
        browser_exe_path=b_info.get("exe_path", ""),
        profile_display_name=p_name,
        canonical_profile_dir=p_dir,
        connection_mode="dedicated" if p_dir == "__dedicated__" else "existing_profile",
        remember_profile=rem,
        auto_connect=auto
    )
    return {
        "success": True,
        "message": "Browser profile preferences updated.",
        "preferences": db.get_browser_profile_preference()
    }


# ==============================================================================
# 4. RESET TO DEDICATED PROFILE
# ==============================================================================

@router.post("/api/browser-profile/dedicated")
@router.post("/api/browser/disconnect")
@router.post("/api/browser/dedicated")
def reset_to_dedicated_profile():
    """Resets messaging connection to the default Dedicated WhatsApp Session and closes driver."""
    adapter = get_browser_adapter()
    try:
        adapter.close()
    except Exception:
        pass

    cm = ConfigManager()
    cfg = cm.get_config()
    cfg.browser = "chrome"
    cfg.profile_dir = "__dedicated__"
    cfg.profile_name = "Dedicated WhatsApp Session"
    cfg.connection_status = "Not checked"
    cm.save_config(cfg)
    connection_monitor.stop_monitoring()

    pref = db.get_browser_profile_preference()
    rem = bool(pref.get("remember_profile", 1) if pref else True)
    auto = bool(pref.get("auto_connect", 0) if pref else False)

    db.save_browser_profile_preference(
        browser_id="chrome",
        browser_family="chrome",
        browser_exe_path="",
        profile_display_name="Dedicated WhatsApp Session",
        canonical_profile_dir="__dedicated__",
        connection_mode="dedicated",
        remember_profile=rem,
        auto_connect=auto
    )

    b_key = getattr(cfg, "browser", "chrome") or "chrome"
    p_dir = getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"
    p_name = getattr(cfg, "profile_name", "Dedicated WhatsApp Session") or "Dedicated WhatsApp Session"
    is_dedicated = (p_dir == "__dedicated__")
    b_name = BrowserManager.BROWSERS.get(b_key, {}).get("name", b_key.title())

    logger.info("Disconnected messaging session and stopped driver.")
    sel_dict = {
        "browser": b_key,
        "browser_name": b_name,
        "profile_dir": p_dir,
        "profile_name": p_name,
        "status": "Not checked",
        "is_selected": True,
        "is_dedicated": is_dedicated,
        "mode": "dedicated" if is_dedicated else "existing_profile",
        "is_locked": False,
        "lock_state": "available",
        "remember_profile": rem,
        "auto_connect": auto
    }
    return {
        "success": True,
        "message": "Disconnected messaging session.",
        "selection": sel_dict,
        "connection": sel_dict
    }


# ==============================================================================
# 5. OPEN SELECTED PROFILE & LIVE CONNECTION MONITORING
# ==============================================================================

@router.get("/api/browser-connection/live")
@router.get("/api/browser/live")
@router.get("/api/browser-connection")
def get_live_browser_connection():
    """
    Returns real-time reactive connection state machine data, event timeline,
    and contextual action buttons for the unified Connection Monitor Card.
    """
    return connection_monitor.get_live_status()


@router.post("/api/browser-connection/action")
@router.post("/api/browser/action")
def execute_connection_action(payload: ConnectionActionRequest):
    """
    Executes a lifecycle action on the connection monitor (e.g. open_whatsapp, cancel, restart_connection).
    """
    return connection_monitor.perform_action(payload.action)


@router.post("/api/browser-session/start")
@router.post("/api/browser/start-session")
def start_browser_session(payload: Optional[SessionStartRequest] = None):
    """
    Primary endpoint for Start Session.
    Acquires launch lock, auto-resolves Relay-owned browser conflicts,
    launches browser window, navigates to WhatsApp Web, and monitors login state.
    """
    cm = ConfigManager()
    cfg = cm.get_config()
    b_key = (payload.browser if payload and payload.browser else None) or getattr(cfg, "browser", "chrome") or "chrome"
    p_dir = (payload.profile_dir if payload and payload.profile_dir else None) or getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"
    p_name = (payload.profile_name if payload and payload.profile_name else None) or getattr(cfg, "profile_name", "")
    force_restart = payload.force_restart if payload else False
    headless = payload.headless if payload else False

    live_status = connection_monitor.start_monitoring(
        browser_key=b_key,
        profile_dir=p_dir,
        profile_name=p_name,
        headless=headless,
        force_restart=force_restart
    )

    return {
        "success": live_status.get("state") not in (ConnectionState.LAUNCH_FAILED, ConnectionState.PROFILE_LOCKED),
        "message": live_status.get("current_activity", "Session started."),
        "prompt_required": live_status.get("prompt_required", False),
        "connection": live_status
    }


@router.post("/api/browser-session/confirm-restart")
def confirm_personal_browser_restart(payload: BrowserConflictConfirmRequest):
    """
    Receives explicit operator confirmation to gracefully close personal browser window(s)
    and launch the automated messaging session.
    """
    if not payload.confirmed:
        return {
            "success": False,
            "message": "Confirmation rejected. Personal browser windows left untouched.",
            "connection": connection_monitor.get_live_status()
        }

    cm = ConfigManager()
    cfg = cm.get_config()
    b_key = payload.browser or getattr(cfg, "browser", "chrome") or "chrome"
    p_dir = payload.profile_dir or getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"

    live_status = connection_monitor.start_monitoring(
        browser_key=b_key,
        profile_dir=p_dir,
        headless=False,
        force_personal=True
    )

    return {
        "success": live_status.get("state") not in (ConnectionState.LAUNCH_FAILED, ConnectionState.PROFILE_LOCKED),
        "message": live_status.get("current_activity", "Personal window closed and session started."),
        "connection": live_status
    }


@router.post("/api/browser-session/resolve-conflict")
def resolve_browser_conflict(browser: Optional[str] = None, profile_dir: Optional[str] = None, force_personal: bool = False):
    """
    Explicitly triggers conflict resolution for a designated profile.
    """
    cm = ConfigManager()
    cfg = cm.get_config()
    target_b = browser or getattr(cfg, "browser", "chrome") or "chrome"
    target_p = profile_dir or getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"
    is_dedicated = (target_p == "__dedicated__")

    result = BrowserManager.resolve_conflict(
        target_b,
        profile_dir=target_p,
        is_dedicated=is_dedicated,
        force_personal=force_personal
    )
    return {
        "success": result.get("resolved", False),
        "result": result,
        "connection": connection_monitor.get_live_status()
    }


@router.post("/api/browser-profile/open")
@router.post("/api/browser/open")
def open_browser_profile():
    """
    Opens the chosen profile in a visible window and begins continuous intelligent observation.
    Automatically resolves previous Relay-owned browser conflicts.
    """
    cm = ConfigManager()
    cfg = cm.get_config()
    b_key = getattr(cfg, "browser", "chrome") or "chrome"
    p_dir = getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"

    b_info = BrowserManager.BROWSERS.get(b_key, {})
    b_name = b_info.get("name", b_key.title())

    # Pre-flight diagnostic check
    diag = BrowserManager.diagnose_profile(
        b_key,
        profile_dir=p_dir,
        is_dedicated=(p_dir == "__dedicated__")
    )
    if diag.get("condition") == "MISSING_EXECUTABLE":
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "BROWSER_NOT_FOUND",
                f"Couldn't start the selected browser profile.",
                diag.get("safe_error_reason", f"{b_name} executable was not found on this computer.")
            )
        )

    # Auto-resolve Relay-owned conflicts
    if diag.get("is_locked") and diag.get("conflict_type") == "relay_owned":
        from backend.session_lifecycle import session_lifecycle
        session_lifecycle.resolve_conflict(b_key, p_dir, is_dedicated=(p_dir == "__dedicated__"), force_personal=False)
        diag = BrowserManager.diagnose_profile(b_key, profile_dir=p_dir, is_dedicated=(p_dir == "__dedicated__"))

    if diag.get("is_locked"):
        raise HTTPException(
            status_code=409,
            detail={
                **_build_structured_error(
                    "PROFILE_IN_USE",
                    diag.get("user_message", f"The selected profile is currently open in {b_name}."),
                    f"Close {b_name} completely to use this profile for automated messaging, or use a dedicated Relay session instead."
                ),
                "prompt_required": True,
                "conflict_type": diag.get("conflict_type", "personal_browser"),
                "personal_pids": diag.get("personal_pids", [])
            }
        )

    # Launch or attach via connection monitor
    live_status = connection_monitor.start_monitoring(
        browser_key=b_key,
        profile_dir=p_dir,
        profile_name=getattr(cfg, "profile_name", ""),
        headless=False
    )

    if live_status.get("state") == ConnectionState.PROFILE_LOCKED:
        raise HTTPException(
            status_code=409,
            detail={
                **_build_structured_error(
                    "PROFILE_IN_USE",
                    live_status.get("current_activity", "Profile is in use."),
                    live_status.get("error_detail", "Close active browser windows.")
                ),
                "prompt_required": live_status.get("prompt_required", True),
                "conflict_type": live_status.get("conflict_type", "personal_browser")
            }
        )
    elif live_status.get("state") == ConnectionState.LAUNCH_FAILED:
        raise HTTPException(
            status_code=500,
            detail=_build_structured_error(
                "LAUNCH_FAILED",
                live_status.get("current_activity", "Couldn't start the selected browser profile."),
                live_status.get("error_detail", "Browser launch failed.")
            )
        )

    return {
        "success": True,
        "message": "Browser profile opened. Continuous WhatsApp Web monitoring active.",
        "connection": live_status
    }


# ==============================================================================
# 6. TEST BROWSER CONNECTION
# ==============================================================================

@router.post("/api/browser-profile/test")
@router.post("/api/browser/test")
@router.get("/api/browser/test")
def test_browser_connection(browser: Optional[str] = None, profile_dir: Optional[str] = None):
    """
    Probes the selected profile in a controlled, non-destructive session to check WhatsApp Web sign-in state.
    Reuses existing healthy Relay sessions when available.
    Automatically handles Relay-owned process conflicts and safely prompts for personal instances.
    Returns honest statuses only: 'Signed in', 'Needs QR sign-in', 'Browser unavailable', 'Profile in use', 'Stale lock detected', or 'Could not verify'.
    Test Connection strictly checks launcher and session status; it NEVER dispatches or queues messages.
    """
    cm = ConfigManager()
    cfg = cm.get_config()

    target_browser = browser or getattr(cfg, "browser", "chrome") or "chrome"
    target_profile = profile_dir or getattr(cfg, "profile_dir", "__dedicated__") or "__dedicated__"
    is_dedicated = (target_profile == "__dedicated__")

    b_info = BrowserManager.BROWSERS.get(target_browser, {})
    b_name = b_info.get("name", target_browser.title())

    # Scenario 3: Reuse existing healthy Relay session
    from backend.session_lifecycle import session_lifecycle
    if connection_monitor.is_connected() and connection_monitor.get_driver() is not None:
        if session_lifecycle.is_session_healthy(connection_monitor.get_driver()):
            logger.info("Test Connection: Reusing active healthy Relay session.")
            status = "Signed in"
            cfg.connection_status = status
            cm.save_config(cfg)
            db.update_browser_last_connected()
            return {
                "success": True,
                "browser": target_browser,
                "browser_name": b_name,
                "profile_dir": target_profile,
                "status": status,
                "is_locked": False,
                "lock_state": "available",
                "mode": "dedicated" if is_dedicated else "existing_profile",
                "detail": "Active WhatsApp Web session verified and ready.",
                "logged_in": True,
                "reused_session": True
            }

    # Pre-flight diagnostic check
    diag = BrowserManager.diagnose_profile(target_browser, profile_dir=target_profile, is_dedicated=is_dedicated)

    if diag.get("condition") == "UNSUPPORTED_DEFAULT_PROFILE" or not diag.get("is_automation_supported", True):
        status = "Cannot be automated"
        cfg.connection_status = status
        cm.save_config(cfg)
        return {
            "success": False,
            "browser": target_browser,
            "browser_name": b_name,
            "profile_dir": target_profile,
            "status": status,
            "is_locked": False,
            "is_automation_supported": False,
            "lock_state": "unsupported_profile",
            "mode": "dedicated" if is_dedicated else "existing_profile",
            "detail": diag.get("safe_error_reason", "Selected Chrome profile cannot be automated due to Chrome 136+ security restrictions. Use persistent Relay session."),
            "logged_in": False
        }

    if diag.get("condition") == "MISSING_EXECUTABLE":
        status = "Browser unavailable"
        cfg.connection_status = status
        cm.save_config(cfg)
        return {
            "success": True,
            "browser": target_browser,
            "browser_name": b_name,
            "profile_dir": target_profile,
            "status": status,
            "is_locked": False,
            "lock_state": "available",
            "mode": "dedicated" if is_dedicated else "existing_profile",
            "detail": diag.get("safe_error_reason", "Browser executable not found."),
            "logged_in": False
        }

    # Auto-resolve Relay-owned conflict
    if diag.get("is_locked") and diag.get("conflict_type") == "relay_owned":
        logger.info("Test Connection: Auto-resolving previous Relay session conflict...")
        session_lifecycle.resolve_conflict(target_browser, target_profile, is_dedicated=is_dedicated, force_personal=False)
        diag = BrowserManager.diagnose_profile(target_browser, profile_dir=target_profile, is_dedicated=is_dedicated)

    if diag.get("is_locked"):
        status = "Profile in use"
        cfg.connection_status = status
        cm.save_config(cfg)
        return {
            "success": True,
            "browser": target_browser,
            "browser_name": b_name,
            "profile_dir": target_profile,
            "status": status,
            "is_locked": True,
            "lock_state": "locked",
            "mode": "existing_profile",
            "prompt_required": diag.get("conflict_type") == "personal_browser",
            "conflict_type": diag.get("conflict_type", "personal_browser"),
            "personal_pids": diag.get("personal_pids", []),
            "detail": diag.get("user_message", f"Profile is currently open in {b_name}."),
            "logged_in": False
        }

    if diag.get("is_stale_lock"):
        status = "Stale lock detected"
        cfg.connection_status = status
        cm.save_config(cfg)
        return {
            "success": True,
            "browser": target_browser,
            "browser_name": b_name,
            "profile_dir": target_profile,
            "status": status,
            "is_locked": False,
            "is_stale_lock": True,
            "lock_state": "stale_lock",
            "mode": "existing_profile",
            "detail": diag.get("user_message", "Stale lock artifact detected."),
            "logged_in": False
        }

    probe = BrowserManager.check_profile_session(target_browser, target_profile)
    status = probe.get("status", "Could not verify")
    is_locked = probe.get("is_locked", False)
    is_stale = probe.get("is_stale_lock", False)

    cfg.connection_status = status
    cm.save_config(cfg)
    if probe.get("logged_in"):
        db.update_browser_last_connected()

    logger.info(f"Connection probe for {target_browser}/{target_profile} result: {status}")
    return {
        "success": True,
        "browser": target_browser,
        "browser_name": b_name,
        "profile_dir": target_profile,
        "status": status,
        "is_locked": is_locked,
        "is_stale_lock": is_stale,
        "lock_state": "locked" if is_locked else ("stale_lock" if is_stale else "available"),
        "mode": "dedicated" if is_dedicated else "existing_profile",
        "detail": probe.get("detail", ""),
        "logged_in": probe.get("logged_in", False)
    }


# ==============================================================================
# 7. TEST SEND MESSAGE
# ==============================================================================

@router.post("/api/browser-profile/test-send")
@router.post("/api/browser/test-send")
def send_test_message(payload: TestSendRequest):
    """
    Dispatches a single test message to a specified verified phone number.
    Ensures safe formatting and logs the activity.
    """
    phone = payload.phone.strip()
    cleaned = DataLoader.clean_phone_number(phone)
    if not cleaned or len(cleaned) < 7 or len(cleaned) > 16:
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "INVALID_PHONE_NUMBER",
                "Invalid phone number format. Please include country code and digits only.",
                "Verify the recipient phone number."
            )
        )

    if db.is_phone_suppressed(cleaned):
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "PHONE_SUPPRESSED",
                "Recipient phone number is currently on the suppression list.",
                "Choose a different phone number or manage suppressions."
            )
        )

    attachment_path = None
    if payload.media_id:
        asset = db.get_media_asset(payload.media_id)
        if not asset:
            raise HTTPException(
                status_code=400,
                detail=_build_structured_error(
                    "MEDIA_NOT_FOUND",
                    f"Media asset #{payload.media_id} not found.",
                    "Select a valid media asset from your media library."
                )
            )
        if not asset.get("is_available") or not os.path.isfile(asset.get("file_path", "")):
            raise HTTPException(
                status_code=400,
                detail=_build_structured_error(
                    "MEDIA_UNAVAILABLE",
                    f"Media failed — file missing on disk: {asset.get('filename')}. No text was sent.",
                    "Re-upload the missing media file."
                )
            )
        try:
            if os.path.getsize(asset["file_path"]) == 0:
                raise HTTPException(
                    status_code=400,
                    detail=_build_structured_error(
                        "MEDIA_UNAVAILABLE",
                        f"Media failed — file is 0 bytes: {asset.get('filename')}. No text was sent.",
                        "Re-upload a non-empty media file."
                    )
                )
        except HTTPException:
            raise
        except Exception:
            pass
        attachment_path = asset["file_path"]
    elif payload.attachment_path:
        if not os.path.isfile(payload.attachment_path):
            raise HTTPException(
                status_code=400,
                detail=_build_structured_error(
                    "MEDIA_UNAVAILABLE",
                    f"Media failed — file missing on disk: {payload.attachment_path}. No text was sent.",
                    "Verify the media file path."
                )
            )
        try:
            if os.path.getsize(payload.attachment_path) == 0:
                raise HTTPException(
                    status_code=400,
                    detail=_build_structured_error(
                        "MEDIA_UNAVAILABLE",
                        f"Media failed — file is 0 bytes: {payload.attachment_path}. No text was sent.",
                        "Provide a non-empty media file."
                    )
                )
        except HTTPException:
            raise
        except Exception:
            pass
        attachment_path = payload.attachment_path

    message_text = payload.message.strip() if payload.message else ""
    if not message_text and not attachment_path:
        raise HTTPException(
            status_code=400,
            detail=_build_structured_error(
                "EMPTY_MESSAGE",
                "Message content or media attachment must be provided.",
                "Enter text or select a media attachment for your test message."
            )
        )

    adapter = get_browser_adapter()

    try:
        msg_fmt = getattr(payload, "message_format", None) or "image_with_caption"
        res = adapter.send_message(
            phone=cleaned,
            message=message_text,
            attachment_path=attachment_path,
            message_format=msg_fmt
        )
        status = res.get("status") if isinstance(res, dict) else None
        success = (status == "SENT") or (res.get("success", False) if isinstance(res, dict) else False)
        error_msg = res.get("error", "") if isinstance(res, dict) else ""

        status_label = "sent" if success else "failed"
        db.log_event(
            "INFO" if success else "ERROR",
            "Browser",
            f"Test send to {cleaned}: {status_label}" + (f" - {error_msg}" if error_msg else "")
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail=_build_structured_error(
                    "DISPATCH_FAILED",
                    f"Test send failed: {error_msg or 'Browser dispatch returned failure'}",
                    "Ensure WhatsApp Web is open and connected."
                )
            )

        return {
            "success": True,
            "message": f"Test message successfully sent to {cleaned}",
            "phone": cleaned,
            "media_sent": res.get("media_sent", False),
            "caption_sent": res.get("caption_sent", False)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during test-send: {e}")
        db.log_event("ERROR", "Browser", f"Test send failed to {cleaned}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=_build_structured_error(
                "DISPATCH_ERROR",
                f"Failed to send test message: {str(e)}",
                "Check server logs and browser status."
            )
        )


@router.get("/api/browser/screenshot")
def get_browser_screenshot():
    from backend.connection_monitor import connection_monitor
    driver = connection_monitor.get_driver()
    if not driver:
        adapter = get_browser_adapter()
        driver = getattr(adapter, "driver", None) or getattr(getattr(adapter, "_engine", None), "driver", None)
    if not driver:
        raise HTTPException(status_code=404, detail="No active browser session")
    try:
        png_data = driver.get_screenshot_as_png()
        return Response(content=png_data, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture screenshot: {str(e)}")


# Legacy helpers
@router.get("/api/browser")
@router.get("/api/browser/")
def get_browser_root():
    return list_browser_profiles()


@router.get("/api/browser/status")
def get_browser_session_status():
    adapter = get_browser_adapter()
    return adapter.check_session_status()
