"""
Job Queue & Execution Monitor API Router.
Provides endpoints for monitoring jobs, issuing pause/resume/cancel controls,
and exporting CSV delivery reports.
"""

import io
import csv
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.database import db
from backend.job_queue import job_worker
from backend.models import JobActionRequest
from logger import get_logger, mask_phone

logger = get_logger("JobsRouter")
router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("")
def list_jobs(limit: int = Query(50, ge=1, le=200)):
    """Lists historical and active background jobs."""
    return db.get_jobs(limit=limit)


@router.get("/active")
def get_active_job():
    """Returns the currently active running or paused job, if any."""
    job = job_worker.get_active_job()
    return {"active_job": job}


@router.get("/activity/items")
def get_activity_items(
    status: Optional[str] = Query(None, description="Filter by status: ALL, SENT, FAILED, UNCERTAIN, PENDING"),
    search: Optional[str] = Query(None, description="Search by recipient name, phone, or message text"),
    job_id: Optional[str] = Query(None, description="Filter by specific job ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Returns recipient-level messaging activity with exact message text,
    media preview thumbnails, status filters, and honest delivery explanations.
    """
    items = db.get_recipient_activity_items(status=status, search=search, job_id=job_id, limit=limit, offset=offset)
    enriched = []
    for it in items:
        d = dict(it)
        d["phone_masked"] = mask_phone(d.get("recipient_phone", ""))
        enriched.append(d)
    return {"items": enriched, "count": len(enriched)}


@router.get("/activity/items/{item_id}")
def get_activity_item_detail(item_id: int):
    """Returns detailed recipient drawer metadata for a single dispatch item."""
    detail = db.get_recipient_activity_detail(item_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Recipient activity record not found")
    detail["phone_masked"] = mask_phone(detail.get("recipient_phone", ""))
    return detail


@router.post("/activity/items/{item_id}/retry")
def retry_single_activity_item(item_id: int):
    """Retries sending to a single failed or uncertain recipient."""
    item = db.get_recipient_activity_detail(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Recipient activity record not found")

    phone = item.get("recipient_phone", "")
    if db.is_phone_suppressed(phone):
        raise HTTPException(status_code=400, detail="Cannot retry: recipient phone is on the suppression/opt-out list")

    # Reset the queue item so status reflects retry in progress
    db.reset_queue_item_for_retry(item_id)

    single_contact = [{
        "name": item.get("recipient_name", "Customer"),
        "phone": phone,
        "message": item.get("resolved_message", "")
    }]

    retry_camp_name = f"Retry: {item.get('recipient_name', 'Recipient')}"
    new_job = job_worker.start_campaign_job(
        campaign_name=retry_camp_name,
        contacts=single_contact,
        template_content=item.get("resolved_message", ""),
        attachment_path=item.get("media_path") if item.get("media_path") else None,
        media_asset_id=item.get("media_asset_id"),
        message_format=item.get("message_format") or "image_with_caption"
    )

    return {
        "success": True,
        "message": f"Retry started for {item.get('recipient_name')} ({mask_phone(phone)})",
        "new_job_id": new_job["id"]
    }


@router.get("/{job_id}")
def get_job_details(job_id: str):
    """Retrieves full details and contact-level delivery logs for a job."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/action")
def perform_job_action(job_id: str, payload: JobActionRequest):
    """Executes a control action (pause, resume, cancel) on a running job."""
    action = payload.action.lower().strip()
    if action == "pause":
        success = job_worker.pause_job(job_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot pause: job is not currently active")
        return {"success": True, "action": "pause", "job_id": job_id}

    elif action == "resume":
        success = job_worker.resume_job(job_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot resume: job is not currently paused or waiting")
        return {"success": True, "action": "resume", "job_id": job_id}

    elif action == "cancel":
        success = job_worker.cancel_job(job_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot cancel: job is not active")
        return {"success": True, "action": "cancel", "job_id": job_id}

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action '{action}'. Valid actions: pause, resume, cancel")


@router.get("/{job_id}/queue")
def get_job_queue_items(
    job_id: str,
    status: Optional[str] = Query(None, description="Filter by status: PENDING, DISPATCHED, SUPPRESSED, RETRYING, FAILED_PERMANENT"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Retrieves durable per-recipient queue items and audit history for a job with privacy masking."""
    items = db.get_queue_items(job_id=job_id, status=status, limit=limit, offset=offset)
    stats = db.get_queue_stats(job_id=job_id)
    enriched_items = []
    for it in items:
        d = dict(it)
        d["phone_masked"] = mask_phone(d.get("recipient_phone", ""))
        enriched_items.append(d)

    return {
        "job_id": job_id,
        "total_queued": sum(stats.values()),
        "stats": stats,
        "items": enriched_items
    }


@router.post("/{job_id}/retry-failed")
def retry_failed_recipients(job_id: str):
    """
    Extracts failed recipients from a completed or stopped campaign run
    and queues a focused retry campaign for only those failed numbers.
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    queue_items = db.get_queue_items(job_id=job_id, limit=5000)
    failed_items = [it for it in queue_items if it.get("status") in ("FAILED", "FAILED_PERMANENT")]

    if not failed_items:
        # Also check results array from legacy jobs
        for r in job.get("results", []):
            if r.get("status") == "failed":
                failed_items.append({
                    "recipient_name": r.get("name", "Customer"),
                    "recipient_phone": r.get("phone", ""),
                    "rendered_message": r.get("message", "")
                })

    if not failed_items:
        raise HTTPException(status_code=400, detail="No failed recipients found for this campaign run.")

    custom_contacts = []
    for it in failed_items:
        p = it.get("recipient_phone") or it.get("phone")
        if p and not db.is_phone_suppressed(p):
            custom_contacts.append({
                "name": it.get("recipient_name") or it.get("name") or "Customer",
                "phone": p,
                "message": it.get("rendered_message") or it.get("message") or ""
            })

    if not custom_contacts:
        raise HTTPException(status_code=400, detail="All failed contacts are now on the suppression list.")

    retry_name = f"Retry: {job.get('campaign_name', 'Campaign')} ({len(custom_contacts)} failed)"
    new_job = job_worker.start_campaign_job(
        campaign_name=retry_name,
        contacts=custom_contacts,
        template_content=custom_contacts[0].get("message", "Retry notification") if custom_contacts else "",
        min_delay=job.get("min_delay", 8.0),
        max_delay=job.get("max_delay", 15.0),
        batch_size=job.get("batch_size", 20),
        batch_pause=job.get("batch_pause", 60.0),
        daily_cap=job.get("daily_cap", 100),
        use_mock=bool(job.get("use_mock", False))
    )

    db.log_event("INFO", "Jobs", f"Queued retry campaign '{retry_name}' for {len(custom_contacts)} failed recipients (Job ID: {new_job['id']})")
    return {
        "success": True,
        "message": f"Retry launched for {len(custom_contacts)} failed recipients.",
        "new_job_id": new_job["id"],
        "retried_count": len(custom_contacts)
    }


@router.get("/{job_id}/export")
def export_job_report_csv(job_id: str):
    """Generates and downloads a CSV delivery report for a specific job."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Job ID", "Campaign", "Recipient Name", "Phone", "Status", "Error Details", "Attachment", "Timestamp"])

    results = job.get("results", [])
    if results:
        for res in results:
            writer.writerow([
                job_id,
                job.get("campaign_name", ""),
                res.get("name", ""),
                mask_phone(res.get("phone", "")),
                res.get("status", ""),
                res.get("error", ""),
                res.get("attachment", ""),
                res.get("timestamp", "")
            ])
    else:
        # Fall back to durable queue items if no result records logged yet
        queue_items = db.get_queue_items(job_id=job_id, limit=5000)
        for item in queue_items:
            writer.writerow([
                job_id,
                job.get("campaign_name", ""),
                item.get("recipient_name", ""),
                mask_phone(item.get("recipient_phone", "")),
                item.get("status", ""),
                item.get("error_message", "") or item.get("variant_purpose", ""),
                item.get("media_path", ""),
                item.get("dispatched_at") or item.get("created_at", "")
            ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=whatsapp_job_report_{job_id}.csv"}
    )

