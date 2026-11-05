"""
Campaigns & Pre-Flight Validation API Router.
Handles campaign staging, consent and suppression audits, message variant distribution,
pre-flight reviews, dry-run simulations, and durable queue job dispatches.
"""

import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException

from backend.database import db
from backend.models import (
    CampaignValidateRequest,
    CampaignDryRunRequest,
    CampaignLaunchRequest,
    CampaignReviewRequest,
    CampaignAllocationPreviewRequest
)
from backend.job_queue import job_worker
from backend.routers.templates import resolve_variant_and_render
from validator import PreFlightValidator, DryRunEngine
from config_manager import AppConfig
from logger import get_logger, mask_phone

logger = get_logger("CampaignsRouter")
router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])


def _resolve_contacts(
    group_name: Optional[str],
    custom_contacts: Optional[List[Dict[str, Any]]],
    template_content: str = "",
    template_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Resolves contacts from database group or direct custom payload, parsing custom attributes."""
    raw_contacts = []
    if custom_contacts:
        raw_contacts = custom_contacts
    elif group_name:
        raw_contacts = db.get_contacts(group_name=group_name, limit=10000, offset=0)

    template = db.get_template(template_id) if template_id else None

    prepared = []
    for c in raw_contacts:
        contact_dict = dict(c)
        name = contact_dict.get("name", "Customer")
        phone = str(contact_dict.get("phone", "")).strip()

        # Parse custom JSON fields into dictionary attributes
        cf_raw = contact_dict.get("custom_fields_json")
        if isinstance(cf_raw, str) and cf_raw:
            try:
                parsed = json.loads(cf_raw)
                if isinstance(parsed, dict):
                    contact_dict.update(parsed)
            except Exception:
                pass

        # Resolve variant and render message
        resolution = resolve_variant_and_render(
            template=template,
            contact_data=contact_dict,
            fallback_content=contact_dict.get("message") or template_content
        )

        contact_dict["phone"] = phone
        contact_dict["name"] = name
        contact_dict["message"] = resolution["rendered_content"]
        contact_dict["resolved_variant_id"] = resolution["resolved_variant_id"]
        contact_dict["variant_name"] = resolution["variant_name"]
        contact_dict["variant_purpose"] = resolution["purpose"]
        contact_dict["eligibility_reason"] = resolution["eligibility_reason"]
        if resolution.get("media_asset") and resolution["media_asset"].get("file_path"):
            contact_dict["attachment"] = resolution["media_asset"]["file_path"]

        prepared.append(contact_dict)

    return prepared


def _audit_campaign_audience(
    contacts: List[Dict[str, Any]],
    cfg: AppConfig,
    template_id: Optional[int] = None
) -> Dict[str, Any]:
    """Performs deep consent, suppression, variant distribution, and duration preflight audit."""
    total_contacts = len(contacts)
    suppressed_contacts = []
    eligible_contacts = []

    consent_counts = {"opted_in": 0, "pending_opt_in": 0, "opted_out": 0}
    variant_distribution = {}

    for c in contacts:
        phone = c.get("phone", "")
        consent = c.get("consent_status", "opted_in")
        if consent in consent_counts:
            consent_counts[consent] += 1

        is_suppressed = db.is_phone_suppressed(phone) or (consent == "opted_out")
        if is_suppressed:
            suppressed_contacts.append({
                "name": c.get("name", "Customer"),
                "phone_masked": mask_phone(phone),
                "reason": "On global suppression list" if db.is_phone_suppressed(phone) else "Contact opted out"
            })
        else:
            eligible_contacts.append(c)
            var_label = f"{c.get('variant_name', 'Default')} ({c.get('variant_purpose', 'General')})"
            variant_distribution[var_label] = variant_distribution.get(var_label, 0) + 1

    # Standard syntax & duplicate audit
    report = PreFlightValidator.audit_contacts(contacts=eligible_contacts or contacts, config=cfg)

    # Estimate duration: average delay + batch cooldowns
    avg_delay = (cfg.min_delay + cfg.max_delay) / 2.0
    effective_count = min(len(eligible_contacts), cfg.daily_cap)
    batch_count = (effective_count // cfg.batch_size) if cfg.batch_size > 0 else 0
    total_seconds = (effective_count * avg_delay) + (batch_count * cfg.batch_pause)
    estimated_minutes = round(total_seconds / 60.0, 1)

    recommendations = list(report.recommendations)
    if suppressed_contacts:
        recommendations.append(f"{len(suppressed_contacts)} contacts will be safely bypassed due to suppression/opt-out rules.")
    if consent_counts["pending_opt_in"] > 0:
        recommendations.append(f"{consent_counts['pending_opt_in']} contacts have pending consent status; ensure compliance with local opt-in laws.")

    return {
        "total_contacts": total_contacts,
        "valid_contacts": len(eligible_contacts),
        "eligible_contacts": len(eligible_contacts),
        "suppressed_count": len(suppressed_contacts),
        "suppressed_contacts": suppressed_contacts[:15],
        "consent_breakdown": consent_counts,
        "variant_distribution": variant_distribution,
        "duplicate_count": report.duplicate_count,
        "duplicates": report.duplicates[:10],
        "invalid_phone_count": report.invalid_phone_count,
        "invalid_phones": report.invalid_phones[:10],
        "missing_name_count": report.missing_name_count,
        "empty_message_count": report.empty_message_count,
        "estimated_duration_minutes": estimated_minutes,
        "recommendations": recommendations,
        "is_ready_to_send": len(eligible_contacts) > 0 and report.invalid_phone_count == 0
    }


@router.post("/allocation-preview")
def preview_campaign_allocations(payload: CampaignAllocationPreviewRequest):
    """
    Generates a deterministic pre-send Allocation Preview Table showing exact
    assigned Message and Media per recipient before launching.
    """
    raw_contacts = []
    if payload.custom_contacts:
        raw_contacts = payload.custom_contacts
    elif payload.group_name:
        raw_contacts = db.get_contacts(group_name=payload.group_name, limit=10000, offset=0)
    else:
        raw_contacts = db.get_contacts(limit=10000, offset=0)

    total_selected = len(raw_contacts)
    if total_selected == 0:
        return {
            "total_selected_contacts": 0,
            "eligible_contacts_count": 0,
            "excluded_optouts_count": 0,
            "excluded_duplicates_count": 0,
            "invalid_numbers_count": 0,
            "estimated_duration_minutes": 0,
            "allocations": []
        }

    # Deduplication and suppression check
    seen_phones = set()
    dup_count = 0
    optout_count = 0
    invalid_count = 0
    eligible_contacts = []

    for c in raw_contacts:
        c_dict = dict(c)
        phone = c_dict.get("phone", "").strip()
        consent = c_dict.get("consent_status", "opted_in")

        if not phone or len(phone) < 7:
            invalid_count += 1
            continue

        if phone in seen_phones:
            dup_count += 1
            continue
        seen_phones.add(phone)

        if consent == "opted_out" or db.is_phone_suppressed(phone):
            optout_count += 1
            continue

        eligible_contacts.append(c_dict)

    # Resolve Text Set & Media Set if specified
    eligible_set_texts = []
    if payload.text_set_id:
        t_set = db.get_content_set(payload.text_set_id)
        if t_set:
            eligible_set_texts = [it for it in t_set.get("items", []) if it.get("is_included", 1) == 1]

    eligible_set_media = []
    if payload.media_set_id:
        m_set = db.get_content_set(payload.media_set_id)
        if m_set:
            eligible_set_media = [it for it in m_set.get("items", []) if it.get("is_included", 1) == 1]

    # Resolve collection or single assets
    collection = db.get_collection(payload.collection_id) if payload.collection_id else None
    col_mode = payload.allocation_mode or (collection["pairing_mode"] if collection else "fixed_pair")

    col_messages = collection["messages"] if collection else []
    col_media = collection["media"] if collection else []
    col_pairs = collection["pairs"] if collection else []

    # Single fallback
    single_template = db.get_template(payload.template_id) if payload.template_id else None
    single_media = db.get_media_asset(payload.media_asset_id) if payload.media_asset_id else None

    allocations = []
    for idx, c in enumerate(eligible_contacts):
        assigned_template = None
        assigned_media = None
        pair_label = ""

        if eligible_set_texts:
            assigned_template = eligible_set_texts[idx % len(eligible_set_texts)]
            pair_label = f"Text Set ({assigned_template.get('title', 'Msg')})"
        elif col_mode == "fixed_pair":
            assigned_template = col_messages[0] if col_messages else single_template
            pair_label = "Fixed Pair"
        elif col_mode in ("approved_combinations", "rules") and col_pairs:
            c_tier = (c.get("customer_tier") or "").lower()
            c_lang = (c.get("language") or "").lower()
            matched_pair = None
            for p in col_pairs:
                rule = (p.get("audience_rule") or p.get("pair_label") or "").lower()
                if (c_tier and c_tier in rule) or (c_lang and c_lang in rule):
                    matched_pair = p
                    break
            if not matched_pair:
                matched_pair = col_pairs[idx % len(col_pairs)]
            assigned_template = db.get_template(matched_pair["template_id"])
            pair_label = matched_pair.get("pair_label") or "Approved Pair"
        elif col_mode in ("balanced_testing", "balanced") and col_pairs:
            matched_pair = col_pairs[idx % len(col_pairs)]
            assigned_template = db.get_template(matched_pair["template_id"])
            pair_label = f"Balanced Rotation #{idx % len(col_pairs) + 1}"
        else:
            assigned_template = single_template
            pair_label = "Default"

        if eligible_set_media:
            assigned_media = eligible_set_media[idx % len(eligible_set_media)]
        elif col_mode == "fixed_pair":
            assigned_media = col_media[0] if col_media else single_media
        elif col_pairs and (col_mode in ("approved_combinations", "rules", "balanced_testing", "balanced")):
            p_obj = locals().get("matched_pair")
            if p_obj and p_obj.get("media_asset_id"):
                assigned_media = db.get_media_asset(p_obj["media_asset_id"])
        else:
            assigned_media = single_media

        raw_content = assigned_template.get("content") if assigned_template else (payload.template_content or "Hello {name}")
        first_name = (c.get("name") or "Customer").split()[0]
        group_val = c.get("group_name") or c.get("group") or "Community"
        lang_val = c.get("language") or "en"
        tier_val = c.get("customer_tier") or c.get("tier") or "Regular"

        rendered = raw_content.replace("{name}", c.get("name", "Customer"))
        rendered = rendered.replace("{first_name}", first_name)
        rendered = rendered.replace("{phone}", c.get("phone", ""))
        rendered = rendered.replace("{group}", group_val)
        rendered = rendered.replace("{language}", lang_val)
        rendered = rendered.replace("{tier}", tier_val)

        msg_title = assigned_template.get("name") or assigned_template.get("title") or "Custom Message"
        med_title = assigned_media.get("title") or assigned_media.get("filename") if assigned_media else "None"
        med_url = f"/api/media/file/{assigned_media.get('filename')}" if (assigned_media and assigned_media.get("filename")) else None
        med_id = assigned_media.get("id") if assigned_media else (assigned_media.get("media_asset_id") if assigned_media else None)

        allocations.append({
            "contact_id": c.get("id"),
            "contact_name": c.get("name", "Customer"),
            "recipient_name": c.get("name", "Customer"),
            "phone": c.get("phone", ""),
            "recipient_phone": c.get("phone", ""),
            "phone_masked": mask_phone(c.get("phone", "")),
            "customer_tier": c.get("customer_tier", "Regular"),
            "language": c.get("language", "en"),
            "pair_label": pair_label,
            "pairing_mode": pair_label,
            "message_title": msg_title,
            "rendered_message": rendered,
            "media_title": med_title,
            "media_asset_id": med_id,
            "media_preview_url": med_url
        })

    avg_delay = 10.0
    est_duration_mins = round((len(allocations) * avg_delay) / 60.0, 1)

    return {
        "total_selected_contacts": total_selected,
        "eligible_contacts_count": len(eligible_contacts),
        "excluded_optouts_count": optout_count,
        "excluded_duplicates_count": dup_count,
        "invalid_numbers_count": invalid_count,
        "estimated_duration_minutes": est_duration_mins,
        "allocations": allocations
    }


@router.post("/validate")
def validate_campaign(payload: CampaignValidateRequest):
    """Executes pre-flight audit: checks suppression, consent, variants, duplicates, and timing."""
    contacts = _resolve_contacts(payload.group_name, payload.custom_contacts, payload.template_content)
    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts found in selected audience")

    cfg = AppConfig(
        min_delay=payload.min_delay,
        max_delay=payload.max_delay,
        batch_size=payload.batch_size,
        batch_pause=payload.batch_pause,
        daily_cap=payload.daily_cap,
        attachment_path=payload.attachment_path or "",
        attach_enabled=bool(payload.attachment_path)
    )

    return _audit_campaign_audience(contacts=contacts, cfg=cfg)


@router.post("/review")
def review_campaign_preflight(payload: CampaignReviewRequest):
    """Comprehensive 5-stage campaign wizard review audit with variant distribution and suppression."""
    contacts = _resolve_contacts(
        payload.group_name,
        payload.custom_contacts,
        payload.template_content or "",
        payload.template_id
    )
    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts found for review audit")

    cfg = AppConfig(
        min_delay=payload.min_delay,
        max_delay=payload.max_delay,
        batch_size=payload.batch_size,
        batch_pause=payload.batch_pause,
        daily_cap=payload.daily_cap,
        attachment_path=payload.attachment_path or "",
        attach_enabled=bool(payload.attachment_path)
    )

    return _audit_campaign_audience(contacts=contacts, cfg=cfg, template_id=payload.template_id)


@router.post("/dry-run")
def simulate_campaign_dry_run(payload: CampaignDryRunRequest):
    """
    Simulates campaign execution safely in memory without opening Chrome.
    Returns preview of simulated recipient dispatches, resolved variants, and pacing.
    """
    contacts = _resolve_contacts(payload.group_name, payload.custom_contacts, payload.template_content)
    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts available for simulation")

    if payload.deduplicate:
        contacts, _ = PreFlightValidator.deduplicate_contacts(contacts)

    cfg = AppConfig(
        min_delay=payload.min_delay,
        max_delay=payload.max_delay,
        batch_size=payload.batch_size,
        batch_pause=payload.batch_pause,
        daily_cap=payload.daily_cap,
        attachment_path=payload.attachment_path or "",
        attach_enabled=bool(payload.attachment_path)
    )

    simulation = DryRunEngine.simulate_campaign(contacts=contacts, config=cfg, sample_size=50)
    return {
        "total_simulated": simulation["total_recipients"],
        "results": [
            {
                "name": s["name"],
                "phone": s["phone_masked"],
                "message": s["simulated_message"],
                "simulated_delay_s": round((cfg.min_delay + cfg.max_delay) / 2, 1)
            }
            for s in simulation["sample_messages"]
        ]
    }


@router.post("/launch")
def launch_campaign(payload: CampaignLaunchRequest):
    """
    Initiates an asynchronous messaging campaign job in the background worker
    with durable queue items, idempotency keys, and suppression safeguards.
    """
    template_content = payload.template_content
    if payload.template_id and not template_content:
        t = db.get_template(payload.template_id)
        if t:
            template_content = t["content"]

    if not template_content and not payload.template_id and not payload.collection_id:
        raise HTTPException(status_code=400, detail="Template content, template ID, or Collection ID is required")

    contacts = _resolve_contacts(
        group_name=payload.group_name,
        custom_contacts=payload.custom_contacts,
        template_content=template_content or "",
        template_id=payload.template_id
    )
    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts found for campaign audience")

    if payload.deduplicate:
        contacts, _ = PreFlightValidator.deduplicate_contacts(contacts)

    try:
        job = job_worker.start_campaign_job(
            campaign_name=payload.campaign_name,
            contacts=contacts,
            template_content=template_content or "",
            min_delay=payload.min_delay,
            max_delay=payload.max_delay,
            batch_size=payload.batch_size,
            batch_pause=payload.batch_pause,
            daily_cap=payload.daily_cap,
            attachment_path=payload.attachment_path,
            media_asset_id=payload.media_asset_id,
            allocation_method=payload.allocation_method,
            allocation_seed=payload.allocation_seed,
            use_mock=payload.use_mock,
            max_retries=payload.max_retries,
            template_id=payload.template_id,
            collection_id=payload.collection_id,
            text_set_id=payload.text_set_id,
            media_set_id=payload.media_set_id,
            scheduled_at=payload.scheduled_at
        )

        db.create_campaign(
            name=payload.campaign_name,
            template_id=payload.template_id,
            group_name=payload.group_name or "Default",
            min_delay=payload.min_delay,
            max_delay=payload.max_delay,
            batch_size=payload.batch_size,
            batch_pause=payload.batch_pause,
            daily_cap=payload.daily_cap,
            attachment_path=payload.attachment_path or "",
            media_asset_id=payload.media_asset_id,
            allocation_method=payload.allocation_method,
            allocation_seed=payload.allocation_seed,
            status=job["status"]
        )

        return {
            "success": True,
            "job_id": job["id"],
            "campaign_name": payload.campaign_name,
            "total_recipients": job["total_count"],
            "suppressed_recipients": job.get("suppressed_count", 0),
            "status": job["status"]
        }
    except RuntimeError as re:
        raise HTTPException(status_code=409, detail=str(re))
    except Exception as e:
        logger.error(f"Failed to launch campaign: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to launch campaign: {str(e)}")


@router.get("")
def list_campaigns(limit: int = 50, offset: int = 0):
    """Lists historical and active campaigns."""
    return db.get_campaigns(limit=limit, offset=offset)


@router.get("/{campaign_id}")
def get_campaign_detail(campaign_id: int):
    """Retrieves full details of a single campaign."""
    camp = db.get_campaign(campaign_id)
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return camp


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: int):
    """Deletes a campaign record."""
    success = db.delete_campaign(campaign_id)
    if not success:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"success": True, "deleted_id": campaign_id}

