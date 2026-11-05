"""
Contacts Management API Router.
Handles contact file uploads, column detection, phone cleaning, CRUD,
audience groups, consent recording, and opt-out suppression lists.
"""

import os
import io
import csv
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from backend.database import db
from backend.models import (
    ContactCreate,
    ContactUpdate,
    ContactBulkCreate,
    ContactBulkMoveRequest,
    ContactBulkEditRequest,
    ContactBulkDeleteRequest,
    DemoRecordsRemoveRequest,
    ContactMergeRequest,
    ContactCleanRequest,
    ContactCleanResponse,
    ContactConsentUpdate,
    SuppressionAddRequest,
    GroupCreate,
    GroupRenameRequest
)
from data_loader import DataLoader
from logger import get_logger

logger = get_logger("ContactsRouter")
router = APIRouter(prefix="/api/contacts", tags=["Contacts"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


@router.post("/upload-preview")
async def upload_and_preview_file(file: UploadFile = File(...)):
    """
    Receives an Excel or CSV file, performs validation, and returns detected columns
    and sample rows for client-side column mapping.
    """
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="Invalid file type. Supported formats: .csv, .xlsx, .xls")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (exceeds 15 MB limit)")

    temp_filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
    temp_path = os.path.join(UPLOAD_DIR, temp_filename)
    with open(temp_path, "wb") as f:
        f.write(contents)

    try:
        if ext == ".csv":
            raw_rows = DataLoader._read_csv(temp_path)
        else:
            raw_rows = DataLoader._read_excel(temp_path)

        if not raw_rows:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        columns = list(raw_rows[0].keys())
        detected_phone = DataLoader._match_header(columns, DataLoader.PHONE_SYNONYMS)
        detected_name = DataLoader._match_header(columns, DataLoader.NAME_SYNONYMS)
        detected_message = DataLoader._match_header(columns, DataLoader.MESSAGE_SYNONYMS)
        detected_attachment = DataLoader._match_header(columns, DataLoader.ATTACHMENT_SYNONYMS)

        sample_preview = raw_rows[:8]

        # Calculate preliminary preview statistics
        valid_count = 0
        invalid_count = 0
        duplicate_count = 0
        seen_phones = set()

        target_phone_col = detected_phone or (columns[0] if columns else "")
        for r in raw_rows:
            raw_p = str(r.get(target_phone_col, "") or "").strip()
            clean_p = DataLoader.clean_phone_number(raw_p)
            if not clean_p or len(clean_p) < 7:
                invalid_count += 1
            elif clean_p in seen_phones:
                duplicate_count += 1
            else:
                seen_phones.add(clean_p)
                valid_count += 1

        return {
            "temp_file_id": temp_filename,
            "filename": filename,
            "total_rows": len(raw_rows),
            "columns": columns,
            "detected_mappings": {
                "phone": detected_phone,
                "name": detected_name,
                "message": detected_message,
                "attachment": detected_attachment
            },
            "preview_stats": {
                "total": len(raw_rows),
                "valid": valid_count,
                "invalid": invalid_count,
                "duplicates": duplicate_count
            },
            "sample_rows": sample_preview
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing uploaded file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {str(e)}")


@router.post("/commit-upload")
def commit_upload_to_group(
    temp_file_id: str = Form(...),
    group_name: str = Form("Default"),
    phone_col: str = Form(...),
    name_col: Optional[str] = Form(None),
    default_country_code: str = Form(""),
    consent_source: str = Form("spreadsheet_import")
):
    """
    Imports contacts from a previously previewed temp file using confirmed column mappings.
    Checks against global suppression lists and marks opted-out numbers automatically.
    """
    clean_id = os.path.basename(temp_file_id)
    file_path = os.path.join(UPLOAD_DIR, clean_id)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Uploaded file session expired or not found")

    ext = os.path.splitext(file_path)[1].lower()
    raw_rows = DataLoader._read_csv(file_path) if ext == ".csv" else DataLoader._read_excel(file_path)

    suppressed_phones = db.get_suppressed_phones_set()
    contacts_to_add = []
    valid_count = 0
    skipped_count = 0
    suppressed_count = 0

    for row in raw_rows:
        raw_phone = str(row.get(phone_col, "") or "").strip()
        cleaned = DataLoader.clean_phone_number(raw_phone, default_country_code)
        if not cleaned:
            skipped_count += 1
            continue

        name = str(row.get(name_col, "") or "").strip() if name_col else "Customer"
        if not name:
            name = "Customer"

        is_suppressed = cleaned in suppressed_phones
        consent_status = "opted_out" if is_suppressed else "opted_in"
        if is_suppressed:
            suppressed_count += 1

        contacts_to_add.append({
            "name": name,
            "phone": cleaned,
            "raw_phone": raw_phone,
            "consent_status": consent_status,
            "consent_source": consent_source,
            **{k: v for k, v in row.items() if k not in (phone_col, name_col)}
        })
        valid_count += 1

    inserted = db.bulk_add_contacts(contacts_to_add, group_name=group_name, consent_source=consent_source)
    db.log_event("INFO", "Contacts", f"Imported {inserted} contacts into group '{group_name}' (Opted-in: {inserted - suppressed_count}, Suppressed: {suppressed_count}, Invalid skipped: {skipped_count})")

    # Clean up temp file
    try:
        os.remove(file_path)
    except Exception:
        pass

    return {
        "success": True,
        "inserted": inserted,
        "opted_in": inserted - suppressed_count,
        "suppressed": suppressed_count,
        "skipped": skipped_count,
        "group_name": group_name
    }


@router.get("")
def list_contacts(
    group: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    consent: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Lists contacts with optional group filtering, consent filtering, search query, and pagination."""
    items = db.get_contacts(group_name=group, search=search, consent_status=consent, limit=limit, offset=offset)
    total = db.count_contacts(group_name=group, search=search, consent_status=consent)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("")
def add_single_contact(contact: ContactCreate):
    """Adds a single recipient contact with explicit consent metadata and duplicate prevention."""
    cleaned = DataLoader.clean_phone_number(contact.phone)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Invalid phone number format")

    is_suppressed = db.is_phone_suppressed(cleaned)
    final_consent = "opted_out" if is_suppressed else contact.consent_status

    try:
        cid = db.add_contact(
            name=contact.name,
            phone=cleaned,
            raw_phone=contact.phone,
            custom_fields=contact.custom_fields,
            group_name=contact.group_name,
            consent_status=final_consent,
            consent_source=contact.consent_source,
            customer_tier=contact.customer_tier,
            language=contact.language,
            deduplicate=contact.deduplicate
        )
    except ValueError as ve:
        raise HTTPException(status_code=409, detail={"message": str(ve)})

    db.log_event("INFO", "Contacts", f"Created contact #{cid} '{contact.name}' (+{cleaned}, Tier: {contact.customer_tier}, Lang: {contact.language}, Consent: {final_consent})")
    return {
        "id": cid,
        "name": contact.name,
        "phone": cleaned,
        "group_name": contact.group_name,
        "customer_tier": contact.customer_tier,
        "language": contact.language,
        "consent_status": final_consent,
        "is_suppressed": is_suppressed
    }


@router.get("/demo-records")
def get_identified_demo_records():
    """Returns identified synthetic demo/test records that can be safely removed."""
    records = db.get_identified_demo_records()
    return {"demo_records": records, "count": len(records)}


@router.post("/demo-records/remove")
def remove_demo_records(payload: DemoRecordsRemoveRequest):
    """Safely removes confirmed synthetic demo records upon explicit user confirmation."""
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required to delete demo records")

    deleted = db.remove_identified_demo_records(payload.ids)
    remaining = db.count_contacts()
    return {"success": True, "deleted_count": deleted, "removed_count": deleted, "remaining_count": remaining}


@router.get("/duplicates")
def get_duplicate_contacts():
    """Returns clusters of contacts sharing identical normalized phone numbers."""
    clusters = db.get_duplicate_contacts()
    return {"duplicate_clusters": clusters, "total_clusters": len(clusters)}


@router.post("/merge")
def merge_duplicate_contacts(payload: ContactMergeRequest):
    """Merges duplicate contact records into a primary contact."""
    success = db.merge_contacts(payload.primary_id, payload.duplicate_ids, payload.merged_data)
    if not success:
        raise HTTPException(status_code=400, detail="Merge failed. Ensure the primary contact exists.")
    return {"success": True, "primary_id": payload.primary_id, "merged_ids": payload.duplicate_ids}


@router.post("/bulk-delete")
def bulk_delete_contacts(payload: ContactBulkDeleteRequest):
    """Permanently deletes selected contacts in bulk by ID."""
    deleted = db.bulk_delete_contacts(payload.contact_ids)
    return {"success": True, "deleted_count": deleted}


@router.post("/bulk-move")
def bulk_move_contacts(payload: ContactBulkMoveRequest):
    """Moves multiple contacts to a target audience group."""
    updated = db.bulk_move_contacts(payload.contact_ids, payload.target_group)
    return {"success": True, "updated_count": updated, "target_group": payload.target_group}


@router.post("/bulk-copy")
def bulk_copy_contacts(payload: ContactBulkMoveRequest):
    """Copies multiple contacts into a target audience group."""
    copied = db.bulk_copy_contacts(payload.contact_ids, payload.target_group)
    return {"success": True, "copied_count": copied, "target_group": payload.target_group}


@router.post("/bulk-edit")
def bulk_edit_contacts(payload: ContactBulkEditRequest):
    """Bulk edits customer tier, language, or consent status across multiple contacts."""
    updated = db.bulk_edit_contacts(
        contact_ids=payload.contact_ids,
        customer_tier=payload.customer_tier,
        language=payload.language,
        consent_status=payload.consent_status,
        consent_override=payload.consent_override
    )
    return {"success": True, "updated_count": updated}


@router.delete("")
def clear_contacts_group(group: Optional[str] = Query(None)):
    """Deletes all contacts in a group or across the entire database."""
    db.clear_contacts(group_name=group)
    db.log_event("WARNING", "Contacts", f"Cleared contacts for group '{group or 'All'}'")
    return {"success": True, "cleared_group": group or "All"}


@router.get("/groups")
def list_groups():
    """Lists all contact audience groups and their contact/opt-in counts."""
    return db.get_groups()


@router.post("/groups")
def create_group(group: GroupCreate):
    """Creates a new contact group."""
    try:
        gid = db.add_group(group.name, group.description)
        return {"id": gid, "name": group.name, "description": group.description}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Group creation failed: {e}")


@router.put("/groups/{group_name}")
def rename_contact_group(group_name: str, payload: GroupRenameRequest):
    """Renames an existing contact group and updates all associated contacts."""
    success = db.rename_group(old_name=group_name, new_name=payload.name, description=payload.description)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to rename group")
    return {"success": True, "old_name": group_name, "new_name": payload.name}


@router.delete("/groups/{group_name}")
def delete_contact_group(group_name: str, fallback_group: str = Query("Default")):
    """Deletes an audience group and migrates contacts to a fallback group."""
    success = db.delete_group(group_name=group_name, fallback_group=fallback_group)
    return {"success": True, "deleted_group": group_name, "migrated_to": fallback_group}


# --- Global Suppression / Opt-Out Endpoints ---

@router.get("/suppression")
def list_suppression_list(
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Lists all globally suppressed / unsubscribed numbers."""
    items = db.get_suppression_list(search=search, limit=limit, offset=offset)
    total = db.count_suppression(search=search)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/suppression")
def add_phone_to_suppression(payload: SuppressionAddRequest):
    """Adds a phone number to the global suppression list to prevent future messaging."""
    cleaned = DataLoader.clean_phone_number(payload.phone)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Invalid phone number format")

    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="A valid opt-out reason is required")

    success = db.add_to_suppression_list(phone=cleaned, reason=payload.reason, source=payload.source)
    if not success:
        raise HTTPException(status_code=409, detail="Phone number is already on the suppression list")

    db.log_event("WARNING", "Compliance", f"Added phone +{cleaned} to global suppression list (Reason: {payload.reason})")
    return {"success": True, "phone": cleaned, "reason": payload.reason}


@router.delete("/suppression/{suppression_id}")
def remove_phone_from_suppression(suppression_id: int):
    """Removes a phone number from the global suppression list upon explicit re-consent."""
    success = db.remove_from_suppression_list(suppression_id)
    if not success:
        raise HTTPException(status_code=404, detail="Suppression record not found")
    db.log_event("INFO", "Compliance", f"Removed suppression record #{suppression_id}")
    return {"success": True, "deleted_id": suppression_id}


@router.post("/clean", response_model=ContactCleanResponse)
def clean_phone_numbers(payload: ContactCleanRequest):
    """Utility endpoint to test and batch-normalize phone numbers."""
    results = []
    valid_count = 0
    invalid_count = 0

    for raw in payload.raw_phones:
        cleaned = DataLoader.clean_phone_number(raw, payload.default_country_code)
        if cleaned:
            valid_count += 1
            results.append({"raw": raw, "clean": cleaned, "is_valid": True})
        else:
            invalid_count += 1
            results.append({"raw": raw, "clean": "", "is_valid": False})

    return ContactCleanResponse(
        total_input=len(payload.raw_phones),
        valid_count=valid_count,
        invalid_count=invalid_count,
        results=results
    )


@router.get("/export")
def export_contacts_csv(group: Optional[str] = Query(None)):
    """Exports contacts to a downloadable CSV file including consent status."""
    contacts = db.get_contacts(group_name=group, limit=10000, offset=0)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Phone", "Raw Phone", "Group", "Consent Status", "Consent Source", "Created At"])
    for c in contacts:
        writer.writerow([
            c.get("name"),
            c.get("phone"),
            c.get("raw_phone"),
            c.get("group_name"),
            c.get("consent_status", "opted_in"),
            c.get("consent_source", "direct_import"),
            c.get("created_at")
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=whatsapp_contacts_{group or 'all'}.csv"}
    )


@router.get("/{contact_id}")
def get_single_contact(contact_id: int):
    """Retrieves full details for a single contact by ID."""
    c = db.get_contact(contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    return c


@router.put("/{contact_id}")
def update_contact_details(contact_id: int, payload: ContactUpdate):
    """Updates contact fields (name, phone, group, tier, language, consent, custom fields)."""
    clean_phone = None
    if payload.phone:
        clean_phone = DataLoader.clean_phone_number(payload.phone)
        if not clean_phone:
            raise HTTPException(status_code=400, detail="Invalid phone number format")

    updated = db.update_contact(
        contact_id=contact_id,
        name=payload.name,
        phone=clean_phone or payload.phone,
        group_name=payload.group_name,
        customer_tier=payload.customer_tier,
        language=payload.language,
        custom_fields=payload.custom_fields,
        consent_status=payload.consent_status,
        consent_source=payload.consent_source,
        opt_out_reason=payload.opt_out_reason,
        consent_override=payload.consent_override
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Contact not found")
    return updated


@router.put("/{contact_id}/consent")
def update_contact_consent_status(contact_id: int, payload: ContactConsentUpdate):
    """Updates the opt-in / opt-out consent state for an individual contact."""
    success = db.update_contact_consent(
        contact_id=contact_id,
        consent_status=payload.consent_status,
        opt_out_reason=payload.opt_out_reason or ""
    )
    if not success:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.log_event("INFO", "Contacts", f"Updated contact #{contact_id} consent to '{payload.consent_status}'")
    return {
        "success": True,
        "contact_id": contact_id,
        "consent_status": payload.consent_status,
        "opt_out_reason": payload.opt_out_reason or ""
    }


@router.delete("/{contact_id}")
def delete_contact(contact_id: int):
    """Deletes a contact by ID."""
    success = db.delete_contact(contact_id)
    if not success:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"success": True, "deleted_id": contact_id}
