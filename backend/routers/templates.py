"""
Template Studio API Router.
Provides template CRUD, dynamic variable extraction, and Spintax preview generation.
"""

import re
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import db
from backend.models import (
    TemplateCreate,
    TemplateUpdate,
    MessageVariantCreate,
    MessageVariantUpdate,
    PreviewResolveRequest,
    PreviewResolveResponse,
    SpintaxTestRequest,
    SpintaxTestResponse
)
from whatsapp_engine import process_spintax
from logger import get_logger

logger = get_logger("TemplatesRouter")
router = APIRouter(prefix="/api/templates", tags=["Templates"])


def _extract_variables(content: str) -> List[str]:
    """Extracts unique variable placeholders: {name}, {company}, etc. Excluding Spintax pipes."""
    pattern = re.compile(r"\{([a-zA-Z0-9_]+)\}")
    matches = pattern.findall(content)
    # Deduplicate while preserving order
    seen = set()
    return [m for m in matches if not (m in seen or seen.add(m))]


@router.get("")
def list_templates():
    """Lists all saved message templates."""
    return db.get_templates()


@router.get("/variables-info")
def get_variables_info():
    """
    Returns structured documentation of all supported dynamic placeholders and variables,
    sample values, click-to-insert actions, and missing variable fallback rules.
    """
    return {
        "variables": [
            {
                "token": "{name}",
                "label": "Full Name",
                "description": "Recipient's full display name (e.g. Alice Smith).",
                "example": "Alice Smith",
                "fallback": "Valued Customer"
            },
            {
                "token": "{first_name}",
                "label": "First Name",
                "description": "First word parsed from recipient's name (e.g. Alice).",
                "example": "Alice",
                "fallback": "there"
            },
            {
                "token": "{phone}",
                "label": "Phone Number",
                "description": "International formatted recipient phone number.",
                "example": "+1 415 555 2671",
                "fallback": "your number"
            },
            {
                "token": "{group}",
                "label": "Audience Group",
                "description": "Name of the audience group the recipient belongs to.",
                "example": "VIP Customers",
                "fallback": "our community"
            },
            {
                "token": "{language}",
                "label": "Language Code",
                "description": "Preferred recipient language code (e.g. en, es, fr).",
                "example": "en",
                "fallback": "en"
            },
            {
                "token": "{tier}",
                "label": "Customer Tier",
                "description": "Customer tier classification (Regular, VIP, Enterprise, Partner).",
                "example": "VIP",
                "fallback": "Regular"
            },
            {
                "token": "{custom.key}",
                "label": "Custom Field",
                "description": "Dynamic attribute from contact custom JSON fields (e.g. {custom.company}, {custom.city}).",
                "example": "Acme Corp",
                "fallback": ""
            }
        ],
        "spintax_support": {
            "syntax": "{Option A|Option B|Option C}",
            "description": "Generates randomized phrasing variations per recipient to ensure authentic communication.",
            "example": "{Hi|Hello|Hey} {name}!"
        },
        "fallback_syntax": {
            "syntax": "{variable|Fallback Value}",
            "description": "Specifies an inline default if the recipient does not have that attribute.",
            "example": "Hello {first_name|there}!"
        }
    }


@router.get("/{template_id}")
def get_template(template_id: int):
    """Retrieves a single template by ID."""
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.post("")
def create_template(payload: TemplateCreate):
    """Creates a new message template with auto-extracted variables."""
    content = payload.content or "Hello {first_name}, "
    variables = _extract_variables(content)
    try:
        tid = db.add_template(
            name=payload.name,
            content=content,
            variables=variables,
            description=payload.description or "",
            content_selection_mode=payload.content_selection_mode or "mix_variations",
            target_group=payload.target_group or "All"
        )
        db.log_event("INFO", "Templates", f"Created template '{payload.name}' (Variables: {variables})")
        return db.get_template(tid)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create template: {e}")


@router.put("/{template_id}")
def update_template(template_id: int, payload: TemplateUpdate):
    """Updates an existing message template."""
    variables = _extract_variables(payload.content) if payload.content else None
    success = db.update_template(
        template_id=template_id,
        name=payload.name,
        content=payload.content,
        variables=variables,
        description=payload.description,
        content_selection_mode=payload.content_selection_mode,
        target_group=payload.target_group,
        pacing_delay_min=payload.pacing_delay_min,
        pacing_delay_max=payload.pacing_delay_max
    )
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    db.log_event("INFO", "Templates", f"Updated template #{template_id}")
    return db.get_template(template_id)


@router.delete("/{template_id}")
def delete_template(template_id: int):
    """Deletes a template by ID."""
    success = db.delete_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    db.log_event("INFO", "Templates", f"Deleted template #{template_id}")
    return {"success": True, "deleted_id": template_id}


@router.post("/spintax-test", response_model=SpintaxTestResponse)
def test_spintax_variations(payload: SpintaxTestRequest):
    """Evaluates Spintax syntax and generates sample randomized variations."""
    variations = []
    for _ in range(payload.sample_count):
        variations.append(process_spintax(payload.text))

    return SpintaxTestResponse(
        original_text=payload.text,
        sample_count=payload.sample_count,
        variations=variations
    )


# --- Purpose-Driven Message Variants & Preview Resolution ---

def resolve_variant_and_render(
    template: Optional[Dict[str, Any]],
    contact_data: Dict[str, Any],
    fallback_content: str = ""
) -> Dict[str, Any]:
    """
    Selects the approved message variant that matches the recipient's attributes
    (e.g., language, tier, custom fields) with clear transparency.
    Interpolates {placeholders} with contact values.
    """
    variants = template.get("variants", []) if template else []
    approved_variants = [v for v in variants if v.get("approval_status") == "approved"]

    lower_contact = {str(k).lower(): str(v).strip() for k, v in contact_data.items()}

    selected_variant = None
    eligibility_reason = ""

    # Pass 1: Look for explicit matching filter rule
    for v in approved_variants:
        f_field = (v.get("audience_filter_field") or "").strip().lower()
        f_val = (v.get("audience_filter_value") or "").strip().lower()
        if f_field and f_field != "all" and f_field in lower_contact:
            if lower_contact[f_field].lower() == f_val:
                selected_variant = v
                eligibility_reason = f"Explicit match on recipient attribute '{v['audience_filter_field']}' = '{v['audience_filter_value']}'"
                break

    # Pass 2: Look for 'all' / catch-all approved variant
    if not selected_variant:
        for v in approved_variants:
            f_field = (v.get("audience_filter_field") or "").strip().lower()
            if f_field in ("all", "*", ""):
                selected_variant = v
                eligibility_reason = "Default catch-all approved variant for all audiences"
                break

    # Pass 3: Fall back to first approved variant, or first variant, or raw template content
    if not selected_variant and approved_variants:
        selected_variant = approved_variants[0]
        eligibility_reason = "Default primary approved variant"
    elif not selected_variant and variants:
        selected_variant = variants[0]
        eligibility_reason = "First available variant (draft status)"

    raw_content = selected_variant["content"] if selected_variant else (template.get("content") if template else fallback_content)

    # Dynamic token enrichment and graceful fallbacks (e.g. {name|Customer}, {first_name})
    enriched_data = dict(contact_data)
    raw_name = str(enriched_data.get("name") or "").strip()
    if "first_name" not in enriched_data or not enriched_data["first_name"]:
        enriched_data["first_name"] = raw_name.split()[0] if raw_name else "Customer"
    if not raw_name:
        enriched_data["name"] = "Customer"

    placeholders_filled = {}

    def _replace_placeholder(match):
        var_name = match.group(1).strip()
        custom_fallback = match.group(2)

        # Look up case-insensitively in enriched_data
        for k, v in enriched_data.items():
            if str(k).lower() == var_name.lower():
                val_str = str(v).strip()
                if val_str:
                    placeholders_filled[var_name] = val_str
                    return val_str

        # If missing or blank, use explicit fallback
        if custom_fallback is not None:
            fb = custom_fallback.strip()
            placeholders_filled[var_name] = fb
            return fb

        # Default smart fallbacks
        if var_name.lower() in ("name", "first_name"):
            placeholders_filled[var_name] = "Customer"
            return "Customer"

        return ""

    # Match {var} or {var|fallback}
    var_pattern = re.compile(r"\{([a-zA-Z0-9_]+)(?:\|([^}]+))?\}")
    rendered_content = var_pattern.sub(_replace_placeholder, raw_content or "")

    media_asset = None
    if selected_variant and selected_variant.get("media_asset_id"):
        media_asset = db.get_media_asset(selected_variant["media_asset_id"])

    return {
        "resolved_variant_id": selected_variant["id"] if selected_variant else None,
        "variant_name": selected_variant["variant_name"] if selected_variant else "Default",
        "purpose": selected_variant.get("purpose", "Standard Communication") if selected_variant else "Standard Communication",
        "eligibility_reason": eligibility_reason or "Direct template content fallback",
        "raw_content": raw_content or "",
        "rendered_content": rendered_content or "",
        "media_asset": media_asset,
        "placeholders_filled": placeholders_filled
    }


@router.get("/{template_id}/variants")
def list_template_variants(template_id: int):
    """Lists all purpose-driven variants for a given template."""
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t.get("variants", [])


@router.post("/{template_id}/variants")
def create_template_variant(template_id: int, payload: MessageVariantCreate):
    """Creates a new approved or draft variant with an explicit business purpose."""
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    # Validate media asset if provided
    if payload.media_asset_id:
        asset = db.get_media_asset(payload.media_asset_id)
        if not asset:
            raise HTTPException(status_code=400, detail="Referenced media_asset_id not found")

    vid = db.add_message_variant(
        template_id=template_id,
        variant_name=payload.variant_name,
        purpose=payload.purpose,
        audience_filter_field=payload.audience_filter_field,
        audience_filter_value=payload.audience_filter_value,
        content=payload.content,
        media_asset_id=payload.media_asset_id,
        approval_status=payload.approval_status
    )
    db.log_event("INFO", "Templates", f"Added variant '{payload.variant_name}' to template #{template_id}")
    return db.get_message_variant(vid)


@router.get("/variants/{variant_id}")
def get_message_variant(variant_id: int):
    """Retrieves a single message variant by ID."""
    v = db.get_message_variant(variant_id)
    if not v:
        raise HTTPException(status_code=404, detail="Message variant not found")
    return v


@router.put("/variants/{variant_id}")
def update_message_variant(variant_id: int, payload: MessageVariantUpdate):
    """Updates an existing message variant's content, purpose, filter, or media association."""
    if payload.media_asset_id:
        asset = db.get_media_asset(payload.media_asset_id)
        if not asset:
            raise HTTPException(status_code=400, detail="Referenced media_asset_id not found")

    success = db.update_message_variant(
        variant_id=variant_id,
        variant_name=payload.variant_name,
        purpose=payload.purpose,
        audience_filter_field=payload.audience_filter_field,
        audience_filter_value=payload.audience_filter_value,
        content=payload.content,
        media_asset_id=payload.media_asset_id,
        approval_status=payload.approval_status
    )
    if not success:
        raise HTTPException(status_code=404, detail="Message variant not found")
    db.log_event("INFO", "Templates", f"Updated message variant #{variant_id} '{payload.variant_name}'")
    return db.get_message_variant(variant_id)


@router.delete("/variants/{variant_id}")
def delete_message_variant(variant_id: int):
    """Deletes a message variant by ID."""
    success = db.delete_message_variant(variant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message variant not found")
    db.log_event("INFO", "Templates", f"Deleted message variant #{variant_id}")
    return {"success": True, "deleted_id": variant_id}


class BulkDeleteTemplatesRequest(BaseModel):
    template_ids: List[int]


@router.post("/bulk-delete")
def bulk_delete_templates(payload: BulkDeleteTemplatesRequest):
    """Permanently deletes selected templates in bulk."""
    deleted_count = 0
    for tid in payload.template_ids:
        if db.delete_template(tid):
            deleted_count += 1
    return {"success": True, "deleted_count": deleted_count}


@router.post("/preview-resolve", response_model=PreviewResolveResponse)
def preview_resolve_variant(payload: PreviewResolveRequest):
    """
    Renders the exact message preview and attached media asset that a sample recipient
    will receive based on recipient attributes and variant eligibility rules.
    """
    template = db.get_template(payload.template_id) if payload.template_id else None
    result = resolve_variant_and_render(
        template=template,
        contact_data=payload.contact_data,
        fallback_content=payload.fallback_content or ""
    )
    return PreviewResolveResponse(**result)


# ==============================================================================
# UNIFIED TEMPLATE WORKSPACE API
# ==============================================================================

class AddMediaToTemplateRequest(BaseModel):
    media_asset_ids: Optional[List[int]] = None
    asset_ids: Optional[List[int]] = None


class ToggleMediaInTemplateRequest(BaseModel):
    is_active: bool


class AddTextVariationRequest(BaseModel):
    content: Optional[str] = None
    text_content: Optional[str] = None


class UpdateTextVariationRequest(BaseModel):
    content: Optional[str] = None
    text_content: Optional[str] = None
    is_active: Optional[bool] = None


class PasteMultipleTextsRequest(BaseModel):
    raw_text: str
    separator: Optional[str] = "\n"


class ImportTemplateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    content_selection_mode: Optional[str] = "mix_variations"
    target_group: Optional[str] = "All"
    text_variations: Optional[List[str]] = []
    media_asset_ids: Optional[List[int]] = []


class LaunchTemplateCampaignRequest(BaseModel):
    campaign_name: Optional[str] = None
    target_group: Optional[str] = "All"
    pacing_delay_min: Optional[int] = 8
    pacing_delay_max: Optional[int] = 16


@router.post("/{template_id}/duplicate")
def duplicate_template(template_id: int):
    """Clones a template with all its media assets and text variations."""
    dup = db.duplicate_template(template_id)
    if not dup:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True, "template": dup}


@router.get("/{template_id}/export")
def export_template(template_id: int):
    """Exports a template configuration, text variations, and media metadata into portable JSON."""
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    export_data = {
        "format": "relay_template_v1",
        "name": t["name"],
        "description": t.get("description", ""),
        "content_selection_mode": t.get("content_selection_mode", "mix_variations"),
        "target_group": t.get("target_group", "All"),
        "pacing_delay_min": t.get("pacing_delay_min", 8),
        "pacing_delay_max": t.get("pacing_delay_max", 16),
        "text_variations": [tv["content"] for tv in t.get("text_variations", [])],
        "media_assets": [
            {
                "title": m.get("title", ""),
                "filename": m.get("filename", ""),
                "mime_type": m.get("mime_type", ""),
                "file_size": m.get("file_size", 0)
            }
            for m in t.get("media_assets", [])
        ]
    }
    return export_data


@router.post("/import")
def import_template(payload: ImportTemplateRequest):
    """Imports a template and registers its text variations and media associations."""
    tid = db.add_template(
        name=payload.name,
        content=payload.text_variations[0] if payload.text_variations else "",
        description=payload.description or "",
        content_selection_mode=payload.content_selection_mode or "mix_variations",
        target_group=payload.target_group or "All"
    )

    if payload.text_variations:
        for idx, text in enumerate(payload.text_variations):
            if idx == 0:
                continue  # already added as primary in add_template
            db.add_template_text_variation(tid, text)

    if payload.media_asset_ids:
        db.add_template_media_assets(tid, payload.media_asset_ids)

    return {"success": True, "template": db.get_template(tid)}


@router.post("/{template_id}/media")
def add_media_to_template(template_id: int, payload: AddMediaToTemplateRequest):
    """Associates existing library media assets with a template."""
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    ids = payload.media_asset_ids or payload.asset_ids or []
    added = db.add_template_media_assets(template_id, ids)
    return {"success": True, "added_count": added, "template": db.get_template(template_id)}


@router.delete("/{template_id}/media/{media_asset_id}")
def remove_media_from_template(template_id: int, media_asset_id: int):
    """Removes a media asset from a template without deleting it from the media library."""
    success = db.remove_template_media_asset(template_id, media_asset_id)
    return {"success": success, "template": db.get_template(template_id)}


@router.put("/{template_id}/media/{media_asset_id}/toggle")
def toggle_media_in_template(template_id: int, media_asset_id: int, payload: ToggleMediaInTemplateRequest):
    """Toggles active/excluded status of a media asset in this template."""
    success = db.toggle_template_media_asset(template_id, media_asset_id, payload.is_active)
    return {"success": success, "template": db.get_template(template_id)}


@router.post("/{template_id}/texts")
def add_text_to_template(template_id: int, payload: AddTextVariationRequest):
    """Adds a new text variation directly into a template."""
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    raw_content = payload.content or payload.text_content or "Hello {first_name}, "
    vid = db.add_template_text_variation(template_id, raw_content)
    return {"success": True, "variant_id": vid, "template": db.get_template(template_id)}


@router.put("/{template_id}/texts/{variant_id}")
def update_text_variation(template_id: int, variant_id: int, payload: UpdateTextVariationRequest):
    """Updates the content or active state of a text variation."""
    raw_content = payload.content if payload.content is not None else payload.text_content
    success = db.update_template_text_variation(variant_id, content=raw_content, is_active=payload.is_active)
    if not success:
        raise HTTPException(status_code=404, detail="Text variation not found")
    return {"success": True, "template": db.get_template(template_id)}


@router.delete("/{template_id}/texts/{variant_id}")
def delete_text_variation(template_id: int, variant_id: int):
    """Permanently deletes a text variation from a template."""
    success = db.delete_template_text_variation(variant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Text variation not found")
    return {"success": True, "deleted_id": variant_id, "template": db.get_template(template_id)}


@router.put("/{template_id}/texts/{variant_id}/toggle")
def toggle_text_variation(template_id: int, variant_id: int, payload: ToggleMediaInTemplateRequest):
    """Toggles active/excluded state of a text variation."""
    success = db.update_template_text_variation(variant_id, is_active=payload.is_active)
    return {"success": success, "template": db.get_template(template_id)}


@router.post("/{template_id}/texts/paste-multiple")
def paste_multiple_text_variations(template_id: int, payload: PasteMultipleTextsRequest):
    """Splits raw pasted text by separator (default newline) and adds each non-empty entry as a text variation."""
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    sep = payload.separator or "\n"
    lines = [l.strip() for l in payload.raw_text.split(sep) if l.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="No non-empty text lines found in input")

    added = 0
    for line in lines:
        db.add_template_text_variation(template_id, line)
        added += 1

    return {"success": True, "added_count": added, "template": db.get_template(template_id)}


@router.post("/{template_id}/preview-assignments")
def preview_template_assignments(template_id: int):
    """
    Computes 1-media + 1-text assignment for all eligible recipients.
    Returns preview summary with sample recipient table.
    """
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    assignments = db.compute_template_assignments(template_id, preview_limit=50)
    return assignments


@router.post("/{template_id}/launch")
def launch_template_campaign(template_id: int, payload: LaunchTemplateCampaignRequest):
    """
    Reviews assignments and launches an active messaging campaign directly from a template.
    Generates durable queue items with pre-computed 1-media + 1-text assignments.
    """
    from datetime import datetime
    from backend.job_queue import job_worker

    tpl = db.get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    assignments_data = db.compute_template_assignments(template_id, preview_limit=5000)
    assignments = assignments_data.get("all_assignments", [])
    if not assignments:
        raise HTTPException(
            status_code=400,
            detail="Cannot launch campaign: No eligible contacts found in selected audience."
        )

    active_texts = [t for t in tpl.get("text_variations", []) if t.get("is_active", 1)]
    if not active_texts and not tpl.get("content"):
        raise HTTPException(
            status_code=400,
            detail="Cannot launch campaign: Please add at least one active message variation."
        )

    target_grp = payload.target_group or tpl.get("target_group", "All")
    camp_name = payload.campaign_name or f"{tpl['name']} ({datetime.now().strftime('%b %d, %H:%M')})"

    contacts = db.get_contacts(group_name=target_grp if target_grp != "All" else None, limit=5000)
    eligible_contacts = [c for c in contacts if c.get("consent_status") != "opted_out"]

    # Start campaign in background job worker
    res = job_worker.start_campaign_job(
        campaign_name=camp_name,
        contacts=eligible_contacts,
        template_content=active_texts[0]["content"] if active_texts else (tpl.get("content") or ""),
        min_delay=float(payload.pacing_delay_min or tpl.get("pacing_delay_min", 8)),
        max_delay=float(payload.pacing_delay_max or tpl.get("pacing_delay_max", 16)),
        allocation_method=tpl.get("content_selection_mode", "mix_variations"),
        template_id=template_id
    )

    return {
        "success": True,
        "campaign_name": camp_name,
        "job": res,
        "eligible_count": len(eligible_contacts),
        "mode": tpl.get("content_selection_mode", "mix_variations")
    }

