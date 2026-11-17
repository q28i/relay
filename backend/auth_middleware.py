"""
Authentication and Identity Middleware for Relay Cloud & Tailscale Integration.

Supports:
1. Tailscale Serve identity headers (`Tailscale-User-Login`, `Tailscale-User-Name`).
2. Bearer token / API Key authentication via `RELAY_AUTH_KEY`.
3. Session cookies (`relay_session`) for browser/mobile access.
4. Backward-compatible local mode (auth disabled by default on desktop/localhost).
"""

import os
import secrets
import time
from typing import Dict, Any, Optional, Set
from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from logger import get_logger

logger = get_logger("AuthMiddleware")

# In-memory active session tokens: token -> { "created_at": float, "user": dict }
_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_EXPIRY_SECONDS = 30 * 86400  # 30 days


def is_auth_enabled() -> bool:
    """Returns True if authentication is strictly enforced."""
    enable_env = os.environ.get("RELAY_ENABLE_AUTH", "").lower() in ("1", "true", "yes")
    has_key = bool(os.environ.get("RELAY_AUTH_KEY")) or bool(os.environ.get("RELAY_PASSWORD"))
    return enable_env or has_key


def get_allowed_tailscale_users() -> Set[str]:
    """Returns set of allowed Tailscale user login emails. If empty, allows all tailnet users."""
    raw = os.environ.get("ALLOWED_TAILSCALE_USERS", "").strip()
    if not raw or raw == "*":
        return set()
    return {u.strip().lower() for u in raw.split(",") if u.strip()}


def create_session(user_info: Dict[str, Any]) -> str:
    """Creates and records a new session token."""
    token = secrets.token_urlsafe(32)
    _ACTIVE_SESSIONS[token] = {
        "created_at": time.time(),
        "user": user_info
    }
    return token


def validate_session(token: str) -> Optional[Dict[str, Any]]:
    """Validates session token and returns user info if valid."""
    if not token or token not in _ACTIVE_SESSIONS:
        return None
    sess = _ACTIVE_SESSIONS[token]
    if time.time() - sess["created_at"] > SESSION_EXPIRY_SECONDS:
        del _ACTIVE_SESSIONS[token]
        return None
    return sess["user"]


def destroy_session(token: str) -> bool:
    """Revokes session token."""
    if token in _ACTIVE_SESSIONS:
        del _ACTIVE_SESSIONS[token]
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """
    FastAPI HTTP middleware inspecting Tailscale headers, Bearer tokens, and session cookies.
    """

    PUBLIC_PATHS = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/me",
        "/favicon.ico",
        "/manifest.json",
        "/login",
    }

    async def dispatch(self, request: Request, call_next):
        # 1. If auth is not enabled, bypass immediately
        if not is_auth_enabled():
            request.state.user = {
                "authenticated": True,
                "auth_type": "disabled",
                "email": "local@localhost",
                "name": "Local User"
            }
            return await call_next(request)

        path = request.url.path
        is_public = (
            path in self.PUBLIC_PATHS
            or path.startswith("/static")
            or path.startswith("/api/docs")
            or path.startswith("/api/openapi.json")
        )

        user_info = None

        # 2. Check Tailscale Serve Headers (injected by host tailscale serve)
        ts_login = request.headers.get("Tailscale-User-Login")
        if ts_login:
            ts_login_clean = ts_login.strip().lower()
            allowed = get_allowed_tailscale_users()
            if allowed and ts_login_clean not in allowed:
                logger.warning(f"Tailscale user '{ts_login_clean}' rejected: not in ALLOWED_TAILSCALE_USERS.")
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Access denied: Tailscale user '{ts_login}' is not authorized."}
                )

            user_info = {
                "authenticated": True,
                "auth_type": "tailscale",
                "email": ts_login_clean,
                "name": request.headers.get("Tailscale-User-Name", ts_login_clean),
                "profile_pic": request.headers.get("Tailscale-User-Profile-Pic", "")
            }

        # 3. Check Bearer Token in Authorization header
        if not user_info:
            auth_header = request.headers.get("Authorization") or ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                expected_key = os.environ.get("RELAY_AUTH_KEY") or os.environ.get("RELAY_PASSWORD")
                if expected_key and secrets.compare_digest(token, expected_key):
                    user_info = {
                        "authenticated": True,
                        "auth_type": "bearer_key",
                        "email": "admin@relay",
                        "name": "Relay Operator"
                    }
                else:
                    sess_user = validate_session(token)
                    if sess_user:
                        user_info = sess_user

        # 4. Check Session Cookie
        if not user_info:
            cookie_token = request.cookies.get("relay_session")
            if cookie_token:
                sess_user = validate_session(cookie_token)
                if sess_user:
                    user_info = sess_user

        # 5. Check query param token (?token=...) for WebSocket or initial redirect
        if not user_info and request.query_params.get("token"):
            q_token = request.query_params.get("token")
            expected_key = os.environ.get("RELAY_AUTH_KEY") or os.environ.get("RELAY_PASSWORD")
            if expected_key and secrets.compare_digest(q_token, expected_key):
                user_info = {
                    "authenticated": True,
                    "auth_type": "query_token",
                    "email": "admin@relay",
                    "name": "Relay Operator"
                }

        # 6. Outcome
        if user_info:
            request.state.user = user_info
            return await call_next(request)

        # Allow unauthenticated access if path is public
        if is_public:
            request.state.user = {"authenticated": False, "auth_type": "public"}
            return await call_next(request)

        # Unauthenticated request to protected endpoint
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required. Please authenticate via Tailscale or provide a valid Relay key."}
            )

        # For browser navigation, if not authenticated and not /login, return simple login page or 401
        return RedirectResponse(url="/login")
