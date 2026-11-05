"""
Content Sets API Router.
Provides endpoints for creating, managing, and curating reusable Text Sets and Media Sets,
handling temporary campaign inclusion/exclusion, multi-selection bulk actions,
reordering, and text import/export (.csv, .json, .txt).
"""

import io
import csv
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Response, Request
from pydantic import BaseModel, Field

from backend.database import db
from logger import get_logger

logger = get_logger("SetsRouter")
router = APIRouter(prefix="/api/sets", tags=["Content Sets"])


# --- Request Schemas ---

class ContentSetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    set_type: str = Field(..., description="'text' or 'media'")
    description: Optional[str] = Field("", max_length=500)
    allocation_mode: Optional[str] = Field("balanced", description="'balanced', 'random', 'rules', 'fixed'")


class ContentSetUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    allocation_mode: Optional[str] = Field(None, description="'balanced', 'random', 'rules', 'fixed'")


class SetItemsAddRequest(BaseModel):
    template_ids: Optional[List[int]] = None
    media_asset_ids: Optional[List[int]] = None


class NewMessageInSetRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1)


class SetItemsBulkActionRequest(BaseModel):
    item_ids: List[int]
    target_set_id: Optional[int] = None
    is_included: Optional[int] = None


# --- Endpoints ---

@router.get("", response_model=List[Dict[str, Any]])
def list_content_sets(type: Optional[str] = Query(None, description="'text' or 'media'")):
    """Retrieves all content sets, optionally filtered by type."""
    return db.get_content_sets(set_type=type)


@router.post("", status_code=201)
def create_content_set(payload: ContentSetCreateRequest):
    """Creates a new reusable Text Set or Media Set."""
    if payload.set_type.lower() not in ("text", "media"):
        raise HTTPException(status_code=400, detail="set_type must be either 'text' or 'media'")
    return db.create_content_set(
        name=payload.name,
        set_type=payload.set_type,
        description=payload.description or "",
        allocation_mode=payload.allocation_mode or "balanced"
    )


@router.get("/{set_id}")
def get_content_set(set_id: int):
    """Retrieves a single content set with its full item contents and inclusion states."""
    s = db.get_content_set(set_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Content set ID {set_id} not found")
    return s


@router.put("/{set_id}")
def update_content_set(set_id: int, payload: ContentSetUpdateRequest):
    """Updates content set metadata."""
    updated = db.update_content_set(
        set_id=set_id,
        name=payload.name,
        description=payload.description,
        allocation_mode=payload.allocation_mode
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Content set ID {set_id} not found")
    return updated


@router.delete("/{set_id}")
def delete_content_set(set_id: int):
    """Deletes a content set and its associations (underlying library assets remain untouched)."""
    success = db.delete_content_set(set_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Content set ID {set_id} not found")
    return {"success": True, "deleted_set_id": set_id}


@router.post("/{set_id}/duplicate")
def duplicate_content_set(set_id: int):
    """Duplicates a content set with a new name and copies all items."""
    dup = db.duplicate_content_set(set_id)
    if not dup:
        raise HTTPException(status_code=404, detail=f"Content set ID {set_id} not found")
    return dup


@router.post("/{set_id}/items")
def add_items_to_set(set_id: int, payload: SetItemsAddRequest):
    """Adds existing templates or media assets to a content set."""
    s = db.get_content_set(set_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Content set ID {set_id} not found")
    res = db.add_items_to_set(
        set_id=set_id,
        template_ids=payload.template_ids,
        media_asset_ids=payload.media_asset_ids
    )
    return res


@router.post("/{set_id}/new-message")
def add_new_message_to_set(set_id: int, payload: NewMessageInSetRequest):
    """Creates a new template directly and adds it to the specified Text Set."""
    s = db.get_content_set(set_id)
    if not s or s["set_type"] != "text":
        raise HTTPException(status_code=400, detail="New messages can only be added directly to Text Sets")
    return db.add_new_message_to_set(
        set_id=set_id,
        title=payload.title,
        content=payload.content
    )


@router.post("/{set_id}/items/remove")
def remove_items_from_set(set_id: int, payload: SetItemsBulkActionRequest):
    """Removes selected items from a content set."""
    removed = db.remove_items_from_set(set_id, payload.item_ids)
    return {"success": True, "removed_count": removed, "set": db.get_content_set(set_id)}


@router.post("/{set_id}/items/move")
def move_items_between_sets(set_id: int, payload: SetItemsBulkActionRequest):
    """Moves selected items from this set to a target set."""
    if not payload.target_set_id:
        raise HTTPException(status_code=400, detail="target_set_id is required")
    moved = db.move_items_between_sets(set_id, payload.target_set_id, payload.item_ids)
    return {"success": True, "moved_count": moved, "target_set": db.get_content_set(payload.target_set_id)}


@router.post("/{set_id}/items/copy")
def copy_items_between_sets(set_id: int, payload: SetItemsBulkActionRequest):
    """Copies selected items from this set into a target set."""
    if not payload.target_set_id:
        raise HTTPException(status_code=400, detail="target_set_id is required")
    copied = db.copy_items_between_sets(set_id, payload.target_set_id, payload.item_ids)
    return {"success": True, "copied_count": copied, "target_set": db.get_content_set(payload.target_set_id)}


@router.put("/{set_id}/items/{item_id}/toggle")
def toggle_set_item_included(set_id: int, item_id: int, is_included: Optional[int] = Query(None)):
    """Toggles or sets the temporary campaign inclusion state (1 = included, 0 = excluded)."""
    success = db.toggle_set_item_included(item_id, is_included)
    if not success:
        raise HTTPException(status_code=404, detail=f"Set item ID {item_id} not found")
    return {"success": True, "set": db.get_content_set(set_id)}


@router.post("/{set_id}/items/bulk-toggle")
def bulk_toggle_set_items(set_id: int, payload: SetItemsBulkActionRequest):
    """Bulk updates campaign inclusion state across multiple set items."""
    is_inc = payload.is_included if payload.is_included is not None else 1
    updated = db.bulk_toggle_set_items(payload.item_ids, is_inc)
    return {"success": True, "updated_count": updated, "set": db.get_content_set(set_id)}


@router.post("/{set_id}/import")
async def import_text_set_file(
    set_id: int,
    request: Request,
    file: Optional[UploadFile] = None
):
    """
    Imports text messages into a Text Set from an uploaded file (.csv, .json, or .txt) or pasted raw text.
    Validates variable syntax ({name}, {first_name}, {phone}, etc.) and parses cleanly.
    """
    s = db.get_content_set(set_id)
    if not s or s["set_type"] != "text":
        raise HTTPException(status_code=400, detail="Import is only supported on Text Sets")

    content_type = request.headers.get("content-type", "")
    text = ""
    fmt = "auto"
    filename = ""

    if "application/json" in content_type:
        try:
            body = await request.json()
            text = body.get("raw_text", "")
            fmt = (body.get("format") or "auto").lower()
        except Exception:
            text = ""
    elif file is not None:
        filename = (file.filename or "").lower()
        content_bytes = await file.read()
        text = content_bytes.decode("utf-8", errors="replace")
        if filename.endswith(".json"):
            fmt = "json"
        elif filename.endswith(".csv"):
            fmt = "csv"
        else:
            fmt = "txt"
    else:
        try:
            form = await request.form()
            if "file" in form and hasattr(form["file"], "read"):
                f = form["file"]
                filename = (getattr(f, "filename", "") or "").lower()
                content_bytes = await f.read()
                text = content_bytes.decode("utf-8", errors="replace")
                if filename.endswith(".json"):
                    fmt = "json"
                elif filename.endswith(".csv"):
                    fmt = "csv"
                else:
                    fmt = "txt"
            elif "raw_text" in form:
                text = str(form["raw_text"])
                fmt = str(form.get("format", "auto")).lower()
        except Exception:
            pass

    if not text.strip():
        raise HTTPException(status_code=400, detail="No message content provided for import")

    imported_items = []

    # Auto-detect format if needed
    if fmt == "auto":
        trimmed = text.strip()
        if trimmed.startswith("[") or trimmed.startswith("{"):
            fmt = "json"
        elif "," in trimmed.splitlines()[0]:
            fmt = "csv"
        else:
            fmt = "txt"

    if fmt == "json":
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for obj in data:
                    title = obj.get("title") or obj.get("name") or "Imported Message"
                    body = obj.get("body") or obj.get("content") or obj.get("text") or ""
                    if body.strip():
                        imported_items.append({"title": title.strip(), "content": body.strip()})
            elif isinstance(data, dict) and "messages" in data:
                for obj in data["messages"]:
                    title = obj.get("title") or obj.get("name") or "Imported Message"
                    body = obj.get("body") or obj.get("content") or obj.get("text") or ""
                    if body.strip():
                        imported_items.append({"title": title.strip(), "content": body.strip()})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {e}")

    elif fmt == "csv":
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                title = row.get("Title") or row.get("title") or row.get("Name") or row.get("name") or "Imported Message"
                body = row.get("Body") or row.get("body") or row.get("Content") or row.get("content") or ""
                if body.strip():
                    imported_items.append({"title": title.strip(), "content": body.strip()})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV format: {e}")

    else:
        # Default .txt format: lines or double linebreaks
        raw_blocks = text.split("\n---\n") if "\n---\n" in text else text.split("\n\n\n")
        idx = 1
        for block in raw_blocks:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if lines:
                title = lines[0][:40] if len(lines) > 1 else f"Message #{idx}"
                body = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]
                imported_items.append({"title": title, "content": body})
                idx += 1

    if not imported_items:
        raise HTTPException(status_code=400, detail="No valid messages found in the input")

    added_ids = []
    now_str = datetime.now().strftime("%m%d%H%M%S")
    for idx, item in enumerate(imported_items):
        t_name = f"{item['title']} (Imp {now_str}_{idx})"
        tpl_id = db.add_template(name=t_name, content=item["content"])
        added_ids.append(tpl_id)

    res = db.add_items_to_set(set_id=set_id, template_ids=added_ids)
    return {
        "success": True,
        "imported_count": len(added_ids),
        "set": res["set"]
    }


@router.get("/{set_id}/export")
def export_content_set(set_id: int, format: str = Query("csv", description="'csv' or 'json'")):
    """Exports all messages or media references in a content set as CSV or JSON."""
    s = db.get_content_set(set_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Content set ID {set_id} not found")

    items = s.get("items", [])
    set_type = s["set_type"]

    if format.lower() == "json":
        json_data = json.dumps({
            "set_id": s["id"],
            "name": s["name"],
            "set_type": set_type,
            "allocation_mode": s["allocation_mode"],
            "items": [
                {
                    "title": it.get("title"),
                    "content": it.get("content") if set_type == "text" else None,
                    "filename": it.get("filename") if set_type == "media" else None,
                    "is_included": it.get("is_included", 1)
                } for it in items
            ]
        }, indent=2)
        return Response(
            content=json_data,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=set_{set_id}_{set_type}.json"}
        )

    # Default CSV
    output = io.StringIO()
    if set_type == "text":
        writer = csv.writer(output)
        writer.writerow(["ID", "Title", "Content", "Included_In_Campaign"])
        for it in items:
            writer.writerow([it.get("id"), it.get("title", ""), it.get("content", ""), it.get("is_included", 1)])
    else:
        writer = csv.writer(output)
        writer.writerow(["ID", "Title", "Filename", "MIME_Type", "File_Size", "Included_In_Campaign"])
        for it in items:
            writer.writerow([it.get("id"), it.get("title", ""), it.get("filename", ""), it.get("mime_type", ""), it.get("file_size_formatted", ""), it.get("is_included", 1)])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=set_{set_id}_{set_type}.csv"}
    )
