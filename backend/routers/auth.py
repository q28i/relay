"""
Authentication and Session API Router.
Handles login, logout, identity inspection, and serves the mobile-friendly login interface.
"""

import os
import secrets
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from backend.auth_middleware import (
    is_auth_enabled,
    create_session,
    validate_session,
    destroy_session
)
from logger import get_logger

logger = get_logger("AuthRouter")
router = APIRouter(tags=["Authentication"])


class LoginRequest(BaseModel):
    password: str = Field(..., description="Relay Auth Key / Password configured in environment")


@router.get("/api/auth/me")
def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Returns the currently authenticated user's profile and active auth mode.
    """
    auth_on = is_auth_enabled()
    user = getattr(request.state, "user", None)
    if not auth_on:
        return {
            "authenticated": True,
            "auth_enabled": False,
            "auth_type": "disabled",
            "user": {
                "name": "Local Operator",
                "email": "local@localhost"
            }
        }

    if user and user.get("authenticated"):
        return {
            "authenticated": True,
            "auth_enabled": True,
            "auth_type": user.get("auth_type", "unknown"),
            "user": user
        }

    return {
        "authenticated": False,
        "auth_enabled": True,
        "auth_type": "none",
        "user": None
    }


@router.post("/api/auth/login")
def login(payload: LoginRequest, response: Response) -> Dict[str, Any]:
    """
    Authenticates operator using RELAY_AUTH_KEY or RELAY_PASSWORD and sets session cookie.
    """
    if not is_auth_enabled():
        return {"success": True, "message": "Authentication is not enabled."}

    expected_key = os.environ.get("RELAY_AUTH_KEY") or os.environ.get("RELAY_PASSWORD")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server has no RELAY_AUTH_KEY or RELAY_PASSWORD configured."
        )

    if not secrets.compare_digest(payload.password.strip(), expected_key.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication key or password."
        )

    user_info = {
        "authenticated": True,
        "auth_type": "session_cookie",
        "email": "admin@relay",
        "name": "Relay Operator"
    }
    token = create_session(user_info)

    # Set secure HTTP-only cookie
    response.set_cookie(
        key="relay_session",
        value=token,
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        secure=False  # Works over Tailscale Serve HTTP or HTTPS
    )

    return {
        "success": True,
        "token": token,
        "message": "Login successful",
        "user": user_info
    }


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> Dict[str, Any]:
    """
    Logs out the current session and clears the auth cookie.
    """
    cookie_token = request.cookies.get("relay_session")
    if cookie_token:
        destroy_session(cookie_token)
    response.delete_cookie("relay_session")
    return {"success": True, "message": "Logged out successfully."}


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def serve_login_page(request: Request):
    """
    Serves a lightweight, touch-friendly dark-mode login page for mobile or direct browser access.
    """
    # If already logged in, redirect to dashboard
    user = getattr(request.state, "user", None)
    if user and user.get("authenticated"):
        return RedirectResponse(url="/")

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>Relay &mdash; Cloud Sign In</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 16px;
    }
    .login-card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 32px 24px;
      width: 100%;
      max-width: 400px;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 24px;
    }
    .brand-icon {
      width: 40px;
      height: 40px;
      background: #0d9488;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    h1 { font-size: 20px; font-weight: 700; color: #f1f5f9; }
    p.sub { font-size: 13px; color: #94a3b8; margin-top: 2px; }
    .form-group { margin-bottom: 20px; }
    label { display: block; font-size: 13px; font-weight: 500; color: #cbd5e1; margin-bottom: 8px; }
    input[type="password"] {
      width: 100%;
      padding: 14px 16px;
      font-size: 16px;
      background: #0f172a;
      border: 1px solid #475569;
      border-radius: 10px;
      color: #fff;
      outline: none;
      transition: border-color 0.2s;
    }
    input[type="password"]:focus {
      border-color: #14b8a6;
      box-shadow: 0 0 0 2px rgba(20, 184, 166, 0.2);
    }
    .btn-submit {
      width: 100%;
      padding: 14px;
      background: #0d9488;
      color: #ffffff;
      font-size: 16px;
      font-weight: 600;
      border: none;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: background 0.2s;
    }
    .btn-submit:hover { background: #0f766e; }
    .error-msg {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid #ef4444;
      color: #fca5a5;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      margin-bottom: 16px;
      display: none;
    }
    .tailscale-note {
      margin-top: 24px;
      padding-top: 16px;
      border-top: 1px solid #334155;
      font-size: 12px;
      color: #64748b;
      line-height: 1.5;
      text-align: center;
    }
    .tailscale-note strong { color: #94a3b8; }
  </style>
</head>
<body>
  <div class="login-card">
    <div class="brand">
      <div class="brand-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div>
        <h1>Relay Dispatcher</h1>
        <p class="sub">Private 24/7 Cloud Access</p>
      </div>
    </div>

    <div id="error" class="error-msg"></div>

    <form id="loginForm" onsubmit="handleLogin(event)">
      <div class="form-group">
        <label for="password">Access Key / Password</label>
        <input type="password" id="password" name="password" placeholder="Enter RELAY_AUTH_KEY" required autocomplete="current-password" autofocus>
      </div>
      <button type="submit" class="btn-submit" id="submitBtn">Sign In</button>
    </form>

    <div class="tailscale-note">
      Connecting via <strong>Tailscale Serve</strong> automatically signs you in using your Tailscale Google identity.
    </div>
  </div>

  <script>
    async function handleLogin(e) {
      e.preventDefault();
      const pwInput = document.getElementById('password');
      const errorDiv = document.getElementById('error');
      const submitBtn = document.getElementById('submitBtn');
      errorDiv.style.display = 'none';
      submitBtn.disabled = true;
      submitBtn.innerText = 'Verifying...';

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: pwInput.value })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          window.location.href = '/';
        } else {
          errorDiv.innerText = data.detail || 'Invalid authentication key.';
          errorDiv.style.display = 'block';
          submitBtn.disabled = false;
          submitBtn.innerText = 'Sign In';
        }
      } catch (err) {
        errorDiv.innerText = 'Network error. Please try again.';
        errorDiv.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.innerText = 'Sign In';
      }
    }
  </script>
</body>
</html>
"""
    return html
