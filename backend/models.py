"""
Pydantic Request & Response Schemas for WhatsApp Automation Web Dashboard.
Includes schemas for Contacts, Consent, Suppression Lists, Media Assets,
Purpose-Driven Message Variants, and Durable Campaign Execution.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# --- Contact Models ---

class ContactCreate(BaseModel):
    name: str = Field(..., description="Recipient full name")
    phone: str = Field(..., description="Recipient phone number (raw or international)")
    group_name: str = Field(default="Default", description="Audience group name")
    consent_status: str = Field(default="opted_in", description="Consent state: opted_in, pending, opted_out")
    consent_source: str = Field(default="direct_import", description="Consent source e.g. store_checkout, web_form")
    customer_tier: str = Field(default="Regular", description="Customer tier: Regular, VIP, Enterprise, etc.")
    language: str = Field(default="en", description="Recipient language code e.g. en, es, fr")
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom variable attributes (e.g. language, tier, company)")
    deduplicate: bool = Field(default=False, description="Whether to reject if a contact with normalized phone already exists")


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    group_name: Optional[str] = None
    customer_tier: Optional[str] = None
    language: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    consent_status: Optional[str] = None
    consent_source: Optional[str] = None
    opt_out_reason: Optional[str] = None
    consent_override: bool = Field(default=False, description="Explicit confirmation required to change opted_out back to opted_in")


class ContactBulkMoveRequest(BaseModel):
    contact_ids: List[int] = Field(..., description="IDs of contacts to move")
    target_group: str = Field(..., description="Target group name")


class ContactBulkEditRequest(BaseModel):
    contact_ids: List[int] = Field(..., description="IDs of contacts to bulk update")
    customer_tier: Optional[str] = None
    language: Optional[str] = None
    consent_status: Optional[str] = None
    consent_override: bool = Field(default=False)


class ContactBulkDeleteRequest(BaseModel):
    contact_ids: List[int] = Field(..., description="IDs of contacts to bulk delete")


class DemoRecordsRemoveRequest(BaseModel):
    confirmed: bool = Field(..., description="Explicit user confirmation to delete demo records")
    ids: Optional[List[int]] = Field(default=None, description="Optional specific demo record IDs to delete")


class ContactMergeRequest(BaseModel):
    primary_id: int = Field(..., description="The contact ID to keep and update")
    duplicate_ids: List[int] = Field(..., description="The contact IDs to merge and delete")
    merged_data: Optional[Dict[str, Any]] = Field(default=None, description="Optional merged field values")


class GroupRenameRequest(BaseModel):
    name: str = Field(..., description="New group name")
    description: Optional[str] = None


class ContactBulkCreate(BaseModel):
    contacts: List[Dict[str, Any]] = Field(..., description="List of contact dictionaries")
    group_name: str = Field(default="Default", description="Target group name")
    consent_source: str = Field(default="spreadsheet_import", description="Recorded origin of opt-in consent")


class ContactConsentUpdate(BaseModel):
    consent_status: str = Field(..., description="New consent state: opted_in or opted_out")
    opt_out_reason: Optional[str] = Field(default="", description="Reason for opt-out or revocation")


class ContactCleanRequest(BaseModel):
    raw_phones: List[str] = Field(..., description="List of raw phone strings to normalize")
    default_country_code: str = Field(default="", description="Optional default country code prefix if missing")


class ContactCleanResponse(BaseModel):
    total_input: int
    valid_count: int
    invalid_count: int
    results: List[Dict[str, Any]]


# --- Suppression / Opt-Out Models ---

class SuppressionAddRequest(BaseModel):
    phone: str = Field(..., description="Phone number to globally suppress")
    reason: str = Field(..., description="Mandatory reason e.g. customer_unsubscribed, invalid_format, do_not_contact")
    source: str = Field(default="manual_entry", description="Source of suppression notice")


# --- Group Models ---

class GroupCreate(BaseModel):
    name: str = Field(..., description="Unique group name")
    description: str = Field(default="", description="Group description")


# --- Media Asset Models ---

class MediaAssetResponse(BaseModel):
    id: int
    title: str
    filename: str
    file_path: str
    file_size: int
    mime_type: str
    asset_type: str
    approval_status: str
    created_at: str
    content_hash: str = ""
    is_available: bool = True
    usage_count: int = 0
    used_by: List[str] = Field(default_factory=list)


# --- Purpose-Driven Message Variant Models ---

class MessageVariantCreate(BaseModel):
    template_id: Optional[int] = Field(default=None, description="Parent template ID (optional in payload if supplied in URL path)")
    variant_name: str = Field(..., description="Name e.g. Spanish Regional, VIP Loyalty")
    purpose: str = Field(..., description="Visible legitimate purpose e.g. Spanish language segment, VIP tier benefit")
    audience_filter_field: str = Field(default="all", description="Recipient attribute to match on e.g. language, tier, all")
    audience_filter_value: str = Field(default="", description="Attribute value required for eligibility e.g. es, VIP")
    content: str = Field(..., description="Message template content")
    media_asset_id: Optional[int] = Field(default=None, description="Optional associated approved media asset")
    approval_status: str = Field(default="approved", description="Approval state: approved or draft")


class MessageVariantUpdate(BaseModel):
    variant_name: str = Field(..., description="Updated variant title")
    purpose: str = Field(..., description="Updated legitimate business purpose")
    audience_filter_field: str = Field(default="all")
    audience_filter_value: str = Field(default="")
    content: str = Field(...)
    media_asset_id: Optional[int] = Field(default=None)
    approval_status: str = Field(default="approved")


# --- Template Models ---

class TemplateCreate(BaseModel):
    name: str = Field(..., description="Unique template name")
    content: Optional[str] = Field(default="Hello {first_name}, ", description="Base message body with {name} or variable tags")
    description: Optional[str] = Field(default="", description="Template description")
    content_selection_mode: Optional[str] = Field(default="mix_variations", description="same_for_everyone or mix_variations")
    message_format: Optional[str] = Field(default="image_with_caption", description="image_with_caption or image_then_text")
    target_group: Optional[str] = Field(default="All", description="Target contact group")


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Updated template name")
    content: Optional[str] = Field(default=None, description="Updated template body")
    description: Optional[str] = Field(default=None, description="Template description")
    content_selection_mode: Optional[str] = Field(default=None, description="same_for_everyone or mix_variations")
    message_format: Optional[str] = Field(default=None, description="image_with_caption or image_then_text")
    target_group: Optional[str] = Field(default=None, description="Target contact group")
    pacing_delay_min: Optional[int] = Field(default=None, description="Min seconds between messages")
    pacing_delay_max: Optional[int] = Field(default=None, description="Max seconds between messages")


class TemplateSaveRequest(BaseModel):
    name: Optional[str] = Field(default=None, description="Template name")
    description: Optional[str] = Field(default="", description="Template description")
    content_selection_mode: Optional[str] = Field(default="mix_variations", description="mix_variations or same_for_everyone")
    message_format: Optional[str] = Field(default="image_with_caption", description="image_with_caption or image_then_text")
    target_group: Optional[str] = Field(default="All", description="Target audience group")
    pacing_delay_min: Optional[int] = Field(default=8)
    pacing_delay_max: Optional[int] = Field(default=16)
    text_variations: Optional[List[Dict[str, Any]]] = Field(default=None, description="List of text variations with content and active status")
    media_assets: Optional[List[Dict[str, Any]]] = Field(default=None, description="List of media assets with active status")
    excluded_contact_ids: Optional[List[int]] = Field(default=None, description="List of manually excluded contact IDs")


class SpintaxTestRequest(BaseModel):
    text: str = Field(..., description="Message string with Spintax syntax like {Hello|Hi|Greetings}")
    sample_count: int = Field(default=5, ge=1, le=20)


class SpintaxTestResponse(BaseModel):
    original_text: str
    sample_count: int
    variations: List[str]


class PreviewResolveRequest(BaseModel):
    template_id: Optional[int] = Field(default=None, description="Template ID to resolve variants from")
    contact_data: Dict[str, Any] = Field(default_factory=dict, description="Sample recipient variables e.g. {'name': 'Alex', 'language': 'es', 'tier': 'VIP'}")
    fallback_content: Optional[str] = Field(default="", description="Fallback content if no template ID is supplied")


class PreviewResolveResponse(BaseModel):
    resolved_variant_id: Optional[int] = None
    variant_name: str
    purpose: str
    eligibility_reason: str
    raw_content: str
    rendered_content: str
    media_asset: Optional[Dict[str, Any]] = None
    placeholders_filled: Dict[str, str] = Field(default_factory=dict)


# --- Campaign Staging, Pre-Flight & Queue Models ---

class CampaignValidateRequest(BaseModel):
    group_name: Optional[str] = Field(default="Default")
    template_content: Optional[str] = Field(default="")
    custom_contacts: Optional[List[Dict[str, Any]]] = Field(default=None)
    min_delay: float = Field(default=8.0, ge=1.0, le=60.0)
    max_delay: float = Field(default=15.0, ge=1.0, le=120.0)
    batch_size: int = Field(default=20, ge=1, le=200)
    batch_pause: float = Field(default=60.0, ge=5.0, le=600.0)
    daily_cap: int = Field(default=100, ge=1, le=1000)
    attachment_path: Optional[str] = Field(default="")


class CampaignDryRunRequest(BaseModel):
    group_name: Optional[str] = Field(default="Default")
    template_content: Optional[str] = Field(default="")
    custom_contacts: Optional[List[Dict[str, Any]]] = Field(default=None)
    min_delay: float = Field(default=8.0, ge=1.0, le=60.0)
    max_delay: float = Field(default=15.0, ge=1.0, le=120.0)
    batch_size: int = Field(default=20, ge=1, le=200)
    batch_pause: float = Field(default=60.0, ge=5.0, le=600.0)
    daily_cap: int = Field(default=100, ge=1, le=1000)
    attachment_path: Optional[str] = Field(default="")
    deduplicate: bool = Field(default=True)


class CampaignReviewRequest(BaseModel):
    group_name: Optional[str] = Field(default="Default", description="Audience group to audit")
    template_id: Optional[int] = Field(default=None, description="Selected message template")
    custom_contacts: Optional[List[Dict[str, Any]]] = Field(default=None)
    template_content: Optional[str] = Field(default="")
    min_delay: float = Field(default=8.0, ge=1.0, le=60.0)
    max_delay: float = Field(default=15.0, ge=1.0, le=120.0)
    batch_size: int = Field(default=20, ge=1, le=200)
    batch_pause: float = Field(default=60.0, ge=5.0, le=600.0)
    daily_cap: int = Field(default=100, ge=1, le=1000)
    attachment_path: Optional[str] = Field(default="")


class CampaignAllocationPreviewRequest(BaseModel):
    group_name: Optional[str] = Field(default=None)
    custom_contacts: Optional[List[Dict[str, Any]]] = Field(default=None)
    template_id: Optional[int] = Field(default=None)
    template_content: Optional[str] = Field(default=None)
    media_asset_id: Optional[int] = Field(default=None)
    collection_id: Optional[int] = Field(default=None)
    text_set_id: Optional[int] = Field(default=None, description="Optional Text Set ID")
    media_set_id: Optional[int] = Field(default=None, description="Optional Media Set ID")
    allocation_mode: str = Field(default="fixed_pair", description="fixed_pair | approved_combinations | balanced_testing | balanced | rules | fixed")


class CampaignLaunchRequest(BaseModel):
    campaign_name: str = Field(..., description="Descriptive campaign title")
    group_name: Optional[str] = Field(default="Default")
    template_id: Optional[int] = Field(default=None)
    template_content: Optional[str] = Field(default="")
    collection_id: Optional[int] = Field(default=None, description="Optional Content Collection ID")
    text_set_id: Optional[int] = Field(default=None, description="Optional Text Set ID")
    media_set_id: Optional[int] = Field(default=None, description="Optional Media Set ID")
    custom_contacts: Optional[List[Dict[str, Any]]] = Field(default=None)
    min_delay: float = Field(default=8.0, ge=1.0, le=60.0)
    max_delay: float = Field(default=15.0, ge=1.0, le=120.0)
    batch_size: int = Field(default=20, ge=1, le=200)
    batch_pause: float = Field(default=60.0, ge=5.0, le=600.0)
    daily_cap: int = Field(default=100, ge=1, le=1000)
    attachment_path: Optional[str] = Field(default="")
    media_asset_id: Optional[int] = Field(default=None, description="Optional associated approved media asset ID")
    allocation_method: str = Field(default="explicit_default", description="Allocation strategy: explicit_default, rule_based, balanced_rotation, reproducible_ab_test")
    allocation_seed: int = Field(default=42, description="Seed for reproducible A/B testing")
    deduplicate: bool = Field(default=True)
    scheduled_at: Optional[str] = Field(default=None, description="Optional ISO timestamp for scheduled delayed dispatch")
    max_retries: int = Field(default=3, ge=0, le=5, description="Maximum retry attempts on transient network/DOM failures")
    use_mock: bool = Field(default=False, description="Run in mock simulation mode for testing")


# --- Job & Queue Models ---

class JobActionRequest(BaseModel):
    action: str = Field(..., description="Action to perform: pause, resume, cancel")


# --- Config Models ---

class ConfigUpdateRequest(BaseModel):
    min_delay: Optional[float] = Field(default=None, ge=1.0, le=60.0)
    max_delay: Optional[float] = Field(default=None, ge=1.0, le=120.0)
    batch_size: Optional[int] = Field(default=None, ge=1, le=200)
    batch_pause: Optional[float] = Field(default=None, ge=5.0, le=600.0)
    daily_cap: Optional[int] = Field(default=None, ge=1, le=1000)
    default_message: Optional[str] = Field(default=None)
    default_country_code: Optional[str] = Field(default=None)
    headless: Optional[bool] = Field(default=None)


class PresetApplyRequest(BaseModel):
    preset_name: str = Field(..., description="Preset key: safe, balanced, or fast")


# --- Browser & Connection Models ---

class ConnectionActionRequest(BaseModel):
    action: str = Field(..., description="Action to perform: open_whatsapp, open_session, cancel, refresh_status, try_again, use_dedicated, restart_connection")


class ProfileSelectRequest(BaseModel):
    browser: str = Field(..., description="Browser key: chrome, edge, brave, firefox")
    profile_dir: str = Field(..., description="Profile directory name or __dedicated__")
    profile_name: str = Field(..., description="Human-readable profile name")
    owner_confirmed: bool = Field(default=False, description="User explicitly confirms account ownership")
    remember_profile: bool = Field(default=True, description="Persist profile selection across restarts")
    auto_connect: bool = Field(default=False, description="Auto-connect to this profile on startup")


class BrowserPreferenceUpdateRequest(BaseModel):
    remember_profile: Optional[bool] = Field(default=None, description="Whether to remember selected profile")
    auto_connect: Optional[bool] = Field(default=None, description="Whether to auto-connect on startup")
    browser: Optional[str] = Field(default=None)
    profile_dir: Optional[str] = Field(default=None)
    profile_name: Optional[str] = Field(default=None)


class TestSendRequest(BaseModel):
    phone: str = Field(..., description="Recipient phone number for test message")
    message: str = Field(default="", description="Content of test message to send")
    media_id: Optional[int] = Field(default=None, description="Optional media asset ID to attach")
    attachment_path: Optional[str] = Field(default=None, description="Optional direct attachment path")


# --- Content Collections Models ---

class CollectionCreate(BaseModel):
    name: str = Field(..., description="Collection name")
    description: str = Field(default="", description="Optional collection description")
    pairing_mode: str = Field(default="fixed_pair", description="fixed_pair | approved_combinations | balanced_testing")
    message_ids: Optional[List[int]] = Field(default_factory=list)
    media_ids: Optional[List[int]] = Field(default_factory=list)
    pairs: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pairing_mode: Optional[str] = None
    message_ids: Optional[List[int]] = None
    media_ids: Optional[List[int]] = None
    pairs: Optional[List[Dict[str, Any]]] = None


class BrowserConflictConfirmRequest(BaseModel):
    browser: Optional[str] = None
    profile_dir: Optional[str] = None
    confirmed: bool = Field(default=False, description="User explicitly confirms closing open personal browser window")


class SessionStartRequest(BaseModel):
    browser: Optional[str] = None
    profile_dir: Optional[str] = None
    profile_name: Optional[str] = None
    force_restart: bool = Field(default=False, description="Force restart even if Relay-owned session is active")
    headless: bool = Field(default=False)


