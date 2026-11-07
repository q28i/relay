"""
Relay Device Identity & System Diagnostics API Router.

Provides endpoints to query local hardware and OS diagnostics, inspect and copy
persistent Installation ID, configure device labels, manage developer device enrollment,
and export privacy-redacted diagnostic reports.
"""

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any

from backend.device_identity import (
    device_identity_manager,
    VALID_CHANNELS,
    VALID_ROLES,
)
from logger import get_logger

logger = get_logger("DeviceRouter")

router = APIRouter(prefix="/api/device", tags=["Device Identity & Diagnostics"])


class UpdateLabelRequest(BaseModel):
    label: str


class UpdateChannelRequest(BaseModel):
    channel: str


class RegisterDeveloperRequest(BaseModel):
    label: Optional[str] = None
    token: Optional[str] = None
    channel: Optional[str] = "dev"


class ResetIdentityRequest(BaseModel):
    confirm: bool


@router.get("/info")
def get_device_info() -> Dict[str, Any]:
    """
    Returns full local device information:
    persistent identity, system hardware specs, application runtime info, and browser status.
    """
    return {
        "identity": device_identity_manager.get_device_identity(),
        "system": device_identity_manager.get_system_info(),
        "application": device_identity_manager.get_application_info(),
        "browser": device_identity_manager.get_browser_environment(),
    }


@router.post("/label")
def update_device_label(req: UpdateLabelRequest) -> Dict[str, Any]:
    """Updates the friendly local device label (e.g. 'Primary Development Workstation')."""
    try:
        updated = device_identity_manager.set_device_label(req.label)
        return {"status": "success", "identity": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/channel")
def update_update_channel(req: UpdateChannelRequest) -> Dict[str, Any]:
    """Updates update channel preference ('stable', 'beta', or 'dev')."""
    channel = req.channel.strip().lower()
    if channel not in VALID_CHANNELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel '{req.channel}'. Must be one of: {list(VALID_CHANNELS)}"
        )
    try:
        updated = device_identity_manager.set_update_channel(channel)
        return {"status": "success", "identity": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register-developer")
def register_developer_device(req: RegisterDeveloperRequest) -> Dict[str, Any]:
    """
    Registers the current computer as a developer workstation.
    Sets role to 'developer', updates label, and selects channel (defaults to 'dev').
    """
    target_channel = (req.channel or "dev").strip().lower()
    if target_channel not in VALID_CHANNELS:
        target_channel = "dev"
    updated = device_identity_manager.register_as_developer(
        label=req.label,
        token=req.token,
        channel=target_channel
    )
    return {
        "status": "success",
        "message": "Device successfully registered as a Developer Workstation.",
        "identity": updated,
    }


@router.post("/unregister-developer")
def unregister_developer_device() -> Dict[str, Any]:
    """Reverts the device back to Standard role and resets channel to stable."""
    updated = device_identity_manager.unregister_developer()
    return {
        "status": "success",
        "message": "Device reverted to Standard role.",
        "identity": updated,
    }


@router.post("/reset-identity")
def reset_device_identity(req: ResetIdentityRequest) -> Dict[str, Any]:
    """
    Regenerates a new Installation ID UUIDv4 and resets device identity.
    Requires explicit confirmation.
    """
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Resetting installation ID requires explicit confirm=true."
        )
    updated = device_identity_manager.reset_device_identity()
    return {
        "status": "success",
        "message": "Relay Installation ID has been regenerated.",
        "identity": updated,
    }


@router.get("/diagnostics")
def get_diagnostics_report(
    redact: bool = Query(default=True, description="Whether to redact username, hostname, and personal paths"),
    download: bool = Query(default=False, description="Whether to return report as downloadable JSON attachment")
):
    """
    Generates a system diagnostic report.
    By default (redact=true), username, host, and user directory paths are safely redacted.
    Never exports contacts, message contents, or private session tokens.
    """
    report = device_identity_manager.get_diagnostics_report(redact=redact)
    if download:
        import json
        payload = json.dumps(report, indent=2)
        filename = f"relay-diagnostics-{'redacted' if redact else 'full'}.json"
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    return report
