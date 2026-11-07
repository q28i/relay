"""
Application Updates API Router for Relay Desktop.
Provides endpoints for version queries, checking updates from GitHub Releases,
downloading installers, and triggering upgrades safely.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from backend.updater_service import relay_updater, CURRENT_VERSION
from backend.job_queue import job_worker

router = APIRouter(prefix="/api/updates", tags=["Application Updates"])


class CheckUpdateRequest(BaseModel):
    channel: Optional[str] = None


class DownloadUpdateRequest(BaseModel):
    download_url: Optional[str] = None


class ApplyUpdateRequest(BaseModel):
    silent: bool = False


@router.get("/status")
def get_update_status():
    """Returns the current application version, active channel, and update engine state."""
    return relay_updater.get_status()


@router.post("/check")
def check_for_updates(req: Optional[CheckUpdateRequest] = None):
    """Queries GitHub Releases API for the latest release on the target or active channel."""
    channel = req.channel if req else None
    result = relay_updater.check_for_updates(channel=channel)
    return result


@router.post("/download")
def download_update(req: DownloadUpdateRequest, background_tasks: BackgroundTasks):
    """Initiates an asynchronous download of the latest installer."""
    status = relay_updater.get_status()
    if status["is_downloading"]:
        return {"status": "in_progress", "message": "Download already in progress."}

    background_tasks.add_task(relay_updater.download_installer, req.download_url)
    return {"status": "started", "message": "Download started in background."}


@router.post("/apply")
def apply_update(req: ApplyUpdateRequest):
    """
    Applies the downloaded update.
    Rejects immediately if an active campaign is running or paused to protect dispatches.
    """
    if job_worker.get_active_job():
        raise HTTPException(
            status_code=409,
            detail="Cannot update while a WhatsApp campaign is actively dispatching. Please pause or let it complete first."
        )

    success, msg = relay_updater.trigger_update_installer(silent=req.silent)
    if not success:
        raise HTTPException(status_code=409 if "campaign" in msg.lower() else 400, detail=msg)

    return {"status": "applied", "message": msg}
