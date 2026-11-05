"""
Approved Media Assets API Router.
Handles media asset uploads, cataloging, categorization (banner, image, document, product card),
and serving media previews for the interactive conversation composer.
"""

import os
import uuid
import hashlib
import mimetypes
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.database import db
from logger import get_logger

logger = get_logger("MediaRouter")
router = APIRouter(prefix="/api/media", tags=["Media Assets"])

MEDIA_DIR = os.environ.get("RELAY_MEDIA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads", "media"
)
os.makedirs(MEDIA_DIR, exist_ok=True)
MAX_MEDIA_SIZE = 15 * 1024 * 1024  # 15 MB

ALLOWED_MIME_TYPES = {
    # Images & Banners
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/gif": "image",
    # Documents & Brochures
    "application/pdf": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "text/plain": "document",
    # Videos
    "video/mp4": "video"
}


@router.get("")
def list_media_assets(asset_type: Optional[str] = Query(None)):
    """Retrieves all approved media assets, optionally filtered by type."""
    return db.get_media_assets(asset_type=asset_type)


@router.post("/upload")
async def upload_media_asset(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    asset_type: Optional[str] = Form(None),
    approval_status: str = Form("approved")
):
    """
    Uploads and registers an approved media asset (image, banner, brochure, product card).
    Enforces extension, mime-type, and size boundaries.
    """
    filename = file.filename or "media"
    ext = os.path.splitext(filename)[1].lower()
    if not title:
        title = os.path.splitext(filename)[0] or filename
    if not asset_type:
        asset_type = "image" if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") else "document"

    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".docx", ".mp4", ".txt"):
        raise HTTPException(status_code=400, detail=f"Unsupported media file extension '{ext}'")

    contents = await file.read()
    file_size = len(contents)
    if file_size > MAX_MEDIA_SIZE:
        raise HTTPException(status_code=400, detail="Media file exceeds maximum 15 MB threshold")

    content_type = file.content_type
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        content_type = guessed or "application/octet-stream"
    content_hash = hashlib.sha256(contents).hexdigest()

    # SHA-256 Deduplication: Reuse existing asset if file exists on disk
    existing_asset = db.get_media_asset_by_hash(content_hash)
    if existing_asset and existing_asset.get("is_available"):
        return {
            **existing_asset,
            "preview_url": f"/api/media/file/{existing_asset['filename']}",
            "deduplicated": True
        }

    safe_filename = f"asset_{uuid.uuid4().hex[:10]}{ext}"
    safe_path = os.path.join(MEDIA_DIR, safe_filename)

    with open(safe_path, "wb") as f:
        f.write(contents)

    asset_id = db.add_media_asset(
        title=title,
        filename=safe_filename,
        file_path=safe_path,
        file_size=file_size,
        mime_type=content_type,
        asset_type=asset_type,
        content_hash=content_hash,
        approval_status=approval_status
    )
    db.log_event("INFO", "Media", f"Uploaded media asset #{asset_id} '{title}' ({asset_type}, {file_size} bytes, hash: {content_hash[:8]}...)")

    return {
        "id": asset_id,
        "title": title,
        "filename": safe_filename,
        "file_path": safe_path,
        "file_size": file_size,
        "mime_type": content_type,
        "asset_type": asset_type,
        "content_hash": content_hash,
        "approval_status": approval_status,
        "is_available": True,
        "usage_count": 0,
        "used_by": [],
        "preview_url": f"/api/media/file/{safe_filename}"
    }


@router.get("/{asset_id}")
def get_media_asset_details(asset_id: int):
    """Retrieves details of a specific media asset."""
    asset = db.get_media_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    asset["preview_url"] = f"/api/media/file/{asset['filename']}"
    return asset


@router.delete("/{asset_id}")
def delete_media_asset(asset_id: int, force: bool = Query(False)):
    """Deletes a media asset and removes its file from disk, checking for active references."""
    success, msg = db.delete_media_asset(asset_id, force=force)
    if not success:
        if "referenced" in msg.lower():
            raise HTTPException(status_code=409, detail={"message": msg, "code": "MEDIA_REFERENCED"})
        raise HTTPException(status_code=404, detail={"message": msg, "code": "NOT_FOUND"})
    db.log_event("INFO", "Media", f"Deleted media asset #{asset_id}: {msg}")
    return {"success": True, "deleted_id": asset_id, "message": msg}


class RenameMediaRequest(BaseModel):
    title: str


@router.patch("/{asset_id}/rename")
@router.put("/{asset_id}/rename")
def rename_media_asset_endpoint(asset_id: int, payload: RenameMediaRequest):
    """Renames an existing media asset's display title."""
    if not payload.title or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Asset title cannot be empty")
    success = db.rename_media_asset(asset_id, payload.title.strip())
    if not success:
        raise HTTPException(status_code=404, detail="Media asset not found")
    db.log_event("INFO", "Media", f"Renamed media asset #{asset_id} to '{payload.title.strip()}'")
    return {"success": True, "asset": db.get_media_asset(asset_id)}


class BulkDeleteMediaRequest(BaseModel):
    asset_ids: List[int]
    force: bool = False


@router.post("/bulk-delete")
@router.delete("/bulk-delete")
@router.delete("")
def bulk_delete_media_assets(payload: BulkDeleteMediaRequest):
    """Permanently deletes multiple media assets in bulk."""
    deleted_count = 0
    errors = []
    for aid in payload.asset_ids:
        success, msg = db.delete_media_asset(aid, force=payload.force)
        if success:
            deleted_count += 1
        else:
            errors.append(f"Asset #{aid}: {msg}")
    return {"success": True, "deleted_count": deleted_count, "errors": errors}


@router.get("/{asset_id}/file")
def serve_media_file_by_id(asset_id: int):
    """Serves the raw media file by asset ID for direct in-browser rendering."""
    asset = db.get_media_asset(asset_id)
    if not asset or not asset.get("file_path") or not os.path.isfile(asset["file_path"]):
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(asset["file_path"], media_type=asset.get("mime_type"))


@router.get("/file/{filename}")
def serve_media_file(filename: str):
    """Serves the raw media file for in-browser rendering inside the phone conversation preview."""
    clean_name = os.path.basename(filename)
    path = os.path.join(MEDIA_DIR, clean_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(path)

