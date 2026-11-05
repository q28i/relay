# API Documentation: WhatsApp Bulk Messenger Pro

This document provides complete, definitive API reference documentation for all RESTful endpoints and the real-time WebSocket protocol powering the WhatsApp Automation Web Dashboard.

---

## 1. General API Information

- **Base URL:** `http://127.0.0.1:8000`
- **Interactive Swagger UI:** `http://127.0.0.1:8000/api/docs`
- **ReDoc Specification:** `http://127.0.0.1:8000/api/redoc`
- **OpenAPI JSON Contract:** `http://127.0.0.1:8000/api/openapi.json`
- **Transport Protocols:** HTTP/1.1, WebSocket (`ws://`)
- **Default Content-Type:** `application/json`

### Standard Error Responses
All REST endpoints return standardized JSON error envelopes when an exception occurs:
```json
{
  "detail": "Descriptive human-readable explanation of the validation or system error."
}
```

---

## 2. Health & System Endpoints

### 2.1 System Health Check
- **Endpoint:** `GET /api/health`
- **Description:** Verifies service uptime, database connectivity, and active worker status.
- **Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "database": "connected",
  "total_contacts": 142,
  "active_jobs": 0
}
```

---

## 3. Contacts & Audience Management (`/api/contacts`)

### 3.1 Upload & Preview Contacts File
- **Endpoint:** `POST /api/contacts/upload-preview`
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `file` (File, required): `.csv`, `.xlsx`, or `.xls` spreadsheet (max 15 MB).
- **Response (200 OK):**
```json
{
  "temp_file_id": "upload_a8f93e12.xlsx",
  "filename": "Customer_List.xlsx",
  "total_rows": 250,
  "columns": ["Phone Number", "Customer Name", "Company", "City"],
  "detected_mappings": {
    "phone": "Phone Number",
    "name": "Customer Name",
    "message": null,
    "attachment": null
  },
  "sample_rows": [
    { "Phone Number": "+919876543210", "Customer Name": "Alex Mercer", "Company": "Apex Corp", "City": "Mumbai" }
  ]
}
```

### 3.2 Commit Upload to Group
- **Endpoint:** `POST /api/contacts/commit-upload`
- **Content-Type:** `application/x-www-form-urlencoded`
- **Parameters:**
  - `temp_file_id` (string, required): Temporary file identifier returned from preview.
  - `group_name` (string, required): Target contact audience group.
  - `phone_col` (string, required): Name of the column containing phone numbers.
  - `name_col` (string, optional): Name of the column containing names.
  - `default_country_code` (string, optional): Country prefix if numbers lack international code.
- **Response (200 OK):**
```json
{
  "success": true,
  "inserted": 248,
  "skipped": 2,
  "group_name": "Wholesale Clients"
}
```

### 3.3 List Contacts
- **Endpoint:** `GET /api/contacts`
- **Query Parameters:**
  - `group` (string, optional): Filter by audience group name.
  - `search` (string, optional): Search substring in name or phone.
  - `limit` (integer, default: 100): Page limit (1-500).
  - `offset` (integer, default: 0): Page offset.
- **Response (200 OK):**
```json
{
  "items": [
    {
      "id": 1,
      "name": "Alex Mercer",
      "phone": "919876543210",
      "raw_phone": "+91 98765-43210",
      "custom_fields_json": "{\"company\": \"Apex Corp\"}",
      "group_name": "Default",
      "created_at": "2026-11-01T20:30:00"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### 3.4 Add Single Contact
- **Endpoint:** `POST /api/contacts`
- **Request Body:**
```json
{
  "name": "Sarah Connor",
  "phone": "+1 (415) 555-2671",
  "group_name": "VIP Customers",
  "custom_fields": { "account_tier": "Enterprise" }
}
```
- **Response (200 OK):**
```json
{
  "id": 2,
  "name": "Sarah Connor",
  "phone": "14155552671",
  "group_name": "VIP Customers"
}
```

### 3.5 Delete Contact
- **Endpoint:** `DELETE /api/contacts/{contact_id}`
- **Response (200 OK):**
```json
{ "success": true, "deleted_id": 2 }
```

### 3.6 Clear Contacts Group
- **Endpoint:** `DELETE /api/contacts?group={group_name}`
- **Response (200 OK):**
```json
{ "success": true, "cleared_group": "VIP Customers" }
```

### 3.7 List Audience Groups
- **Endpoint:** `GET /api/contacts/groups`
- **Response (200 OK):**
```json
[
  { "id": 1, "name": "Default", "description": "Standard audience", "contact_count": 140 },
  { "id": 2, "name": "VIP Customers", "description": "Enterprise partners", "contact_count": 2 }
]
```

### 3.8 Phone Number Normalization / Cleaner
- **Endpoint:** `POST /api/contacts/clean`
- **Request Body:**
```json
{
  "raw_phones": ["09876-543-210", "+1 (415) 555-2671", "invalid-phone"],
  "default_country_code": "91"
}
```
- **Response (200 OK):**
```json
{
  "total_input": 3,
  "valid_count": 2,
  "invalid_count": 1,
  "results": [
    { "raw": "09876-543-210", "clean": "919876543210", "is_valid": true },
    { "raw": "+1 (415) 555-2671", "clean": "14155552671", "is_valid": true },
    { "raw": "invalid-phone", "clean": "", "is_valid": false }
  ]
}
```

### 3.9 Update Contact Consent Status
- **Endpoint:** `PUT /api/contacts/{id}/consent`
- **Request Body:**
```json
{
  "consent_status": "opted_out",
  "opt_out_reason": "Customer sent STOP keyword via SMS"
}
```
- **Response (200 OK):**
```json
{
  "success": true,
  "contact_id": 1,
  "consent_status": "opted_out",
  "opt_out_reason": "Customer sent STOP keyword via SMS"
}
```

### 3.10 List Global Suppression Numbers
- **Endpoint:** `GET /api/contacts/suppression?search={phone}&limit=100&offset=0`
- **Response (200 OK):**
```json
{
  "total": 1,
  "items": [
    {
      "id": 1,
      "phone": "14155552671",
      "reason": "customer_unsubscribed",
      "source": "manual_entry",
      "created_at": "2026-11-01T21:00:00"
    }
  ]
}
```

### 3.11 Add Number to Global Suppression List
- **Endpoint:** `POST /api/contacts/suppression`
- **Request Body:**
```json
{
  "phone": "+1 415 555 2671",
  "reason": "Explicit GDPR/TCPA opt-out notice",
  "source": "compliance_officer"
}
```
- **Response (200 OK):** Normalized phone added to suppression list.

### 3.12 Remove Number from Suppression List
- **Endpoint:** `DELETE /api/contacts/suppression/{id}`
- **Response (200 OK):** `{ "success": true, "deleted_id": 1 }`

### 3.13 Export Contacts CSV
- **Endpoint:** `GET /api/contacts/export?group={group_name}`
- **Response:** Downloadable CSV file with headers: `Name`, `Phone`, `Raw Phone`, `Group`, `Consent Status`, `Consent Source`, `Created At`.

---

## 4. Approved Media Assets (`/api/media`)

### 4.1 List Media Assets
- **Endpoint:** `GET /api/media`
- **Response (200 OK):**
```json
[
  {
    "id": 1,
    "title": "Autumn Loyalty Flyer",
    "filename": "media_a8f93e12.png",
    "file_path": "c:\\...\\backend\\static\\uploads\\media_a8f93e12.png",
    "file_size": 245120,
    "mime_type": "image/png",
    "asset_type": "banner",
    "approval_status": "approved",
    "created_at": "2026-11-01T21:30:00"
  }
]
```

### 4.2 Upload Approved Media Asset
- **Endpoint:** `POST /api/media/upload`
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `file`: Image (PNG/JPEG/WebP) or PDF brochure (max 15MB).
  - `title`: Descriptive asset label.
  - `asset_type`: `banner`, `product_card`, `brochure`, or `image`.
- **Response (200 OK):** Created `MediaAssetResponse`.

### 4.3 Retrieve Media File
- **Endpoint:** `GET /api/media/file/{filename}`
- **Response (200 OK):** Returns raw image/PDF file bytes with appropriate mime-type header for phone preview rendering.

### 4.4 Delete Media Asset
- **Endpoint:** `DELETE /api/media/{id}`
- **Response (200 OK):** `{ "success": true, "deleted_id": 1 }`

---

## 5. Message Templates & Purpose-Driven Variants (`/api/templates`)

### 4.1 List Templates
- **Endpoint:** `GET /api/templates`
- **Response (200 OK):**
```json
[
  {
    "id": 1,
    "name": "Friendly Welcome",
    "content": "{Hi|Hello|Hey} {name}, thank you for connecting with us!",
    "variables": ["name"],
    "created_at": "2026-11-01T20:00:00",
    "updated_at": "2026-11-01T20:00:00"
  }
]
```

### 4.2 Create Template
- **Endpoint:** `POST /api/templates`
- **Request Body:**
```json
{
  "name": "Quarterly Billing Update",
  "content": "Greetings {name}! Your quarterly statement for {company} is ready."
}
```
- **Response (200 OK):** Auto-extracts variables `["name", "company"]`.
```json
{
  "id": 2,
  "name": "Quarterly Billing Update",
  "content": "Greetings {name}! Your quarterly statement for {company} is ready.",
  "variables": ["name", "company"]
}
```

### 4.3 Update Template
- **Endpoint:** `PUT /api/templates/{id}`
- **Request Body:**
```json
{
  "name": "Updated Billing Statement",
  "content": "Hello {name}, your updated invoice is #{invoice_id}."
}
```
- **Response (200 OK):** Auto-updates extracted variables to `["name", "invoice_id"]`.

### 4.4 Delete Template
- **Endpoint:** `DELETE /api/templates/{id}`
- **Response (200 OK):** `{ "success": true, "deleted_id": 2 }`

### 4.5 Spintax Variation Tester
- **Endpoint:** `POST /api/templates/spintax-test`
- **Request Body:**
```json
{
  "text": "{Good morning|Greetings|Hello} {name}, special offer for you!",
  "sample_count": 3
}
```
- **Response (200 OK):**
```json
{
  "original_text": "{Good morning|Greetings|Hello} {name}, special offer for you!",
  "sample_count": 3,
  "variations": [
    "Good morning {name}, special offer for you!",
    "Hello {name}, special offer for you!",
    "Greetings {name}, special offer for you!"
  ]
}
```

### 5.6 Purpose-Driven Message Variants
- **List Variants:** `GET /api/templates/{id}/variants`
- **Create Variant:** `POST /api/templates/{id}/variants`
- **Request Body:**
```json
{
  "template_id": 1,
  "variant_name": "Spanish Localization",
  "purpose": "Native language messaging for Spanish-speaking clientele",
  "audience_filter_field": "language",
  "audience_filter_value": "es",
  "content": "Hola {name}, gracias por su compra!",
  "media_asset_id": 1,
  "approval_status": "approved"
}
```
- **Update Variant:** `PUT /api/templates/variants/{variant_id}`
- **Delete Variant:** `DELETE /api/templates/variants/{variant_id}`

### 5.7 Transparent Preview Resolution
- **Endpoint:** `POST /api/templates/preview-resolve`
- **Request Body:**
```json
{
  "template_id": 1,
  "contact_data": { "name": "Mateo", "language": "es" },
  "fallback_content": "Hello {name}!"
}
```
- **Response (200 OK):**
```json
{
  "resolved_variant_id": 2,
  "variant_name": "Spanish Localization",
  "purpose": "Native language messaging for Spanish-speaking clientele",
  "eligibility_reason": "Explicit match on recipient attribute 'language' = 'es'",
  "raw_content": "Hola {name}, gracias por su compra!",
  "rendered_content": "Hola Mateo, gracias por su compra!",
  "media_asset": { "id": 1, "filename": "flyer.png", "title": "Flyer" },
  "placeholders_filled": { "name": "Mateo" }
}
```

---

## 6. Campaign Staging & Audits (`/api/campaigns`)

### 6.1 Pre-Flight Review & Suppression Audit
- **Endpoint:** `POST /api/campaigns/review`
- **Request Body:** `CampaignReviewRequest`
- **Response (200 OK):**
```json
{
  "total_contacts": 50,
  "eligible_contacts": 48,
  "suppressed_count": 2,
  "suppressed_contacts": [
    { "name": "John", "phone_masked": "+1 415***2671", "reason": "On global suppression list" }
  ],
  "consent_breakdown": { "opted_in": 48, "pending_opt_in": 0, "opted_out": 2 },
  "variant_distribution": {
    "Primary Variant (Standard)": 38,
    "Spanish Localization (Language)": 10
  },
  "estimated_duration_minutes": 12.5,
  "recommendations": ["2 contacts will be safely bypassed due to suppression/opt-out rules."],
  "is_ready_to_send": true
}
```

### 6.2 Pre-Flight Safety Audit
- **Endpoint:** `POST /api/campaigns/validate`
- **Request Body:**
```json
{
  "group_name": "Default",
  "template_content": "Hello {name}, here is your notification.",
  "min_delay": 8.0,
  "max_delay": 15.0,
  "batch_size": 20,
  "batch_pause": 60.0,
  "daily_cap": 100,
  "attachment_path": ""
}
```
- **Response (200 OK):**
```json
{
  "total_contacts": 45,
  "valid_contacts": 45,
  "duplicate_count": 2,
  "duplicates": [{ "phone": "919876543210", "rows": [1, 14] }],
  "invalid_phone_count": 0,
  "invalid_phones": [],
  "missing_name_count": 0,
  "empty_message_count": 0,
  "attachment_issues": [],
  "estimated_duration_minutes": 11.2,
  "recommendations": ["2 duplicate phone numbers detected. Enabling deduplication is recommended."],
  "is_ready_to_send": true
}
```

### 5.2 Dry-Run Simulation
- **Endpoint:** `POST /api/campaigns/dry-run`
- **Request Body:**
```json
{
  "group_name": "Default",
  "template_content": "{Hi|Hello} {name}! Your tracking code is ready.",
  "min_delay": 8.0,
  "max_delay": 15.0,
  "deduplicate": true
}
```
- **Response (200 OK):**
```json
{
  "total_simulated": 43,
  "results": [
    {
      "name": "Alex Mercer",
      "phone": "+91 98*** **210",
      "message": "Hello Alex Mercer! Your tracking code is ready.",
      "simulated_delay_s": 11.5
    }
  ]
}
```

### 5.3 Launch Campaign Job
- **Endpoint:** `POST /api/campaigns/launch`
- **Request Body:**
```json
{
  "campaign_name": "Q4 Enterprise Outreach",
  "group_name": "VIP Customers",
  "template_content": "Greetings {name}! Here is your quarterly review.",
  "min_delay": 8.0,
  "max_delay": 15.0,
  "batch_size": 20,
  "batch_pause": 60.0,
  "daily_cap": 100,
  "deduplicate": true,
  "use_mock": false
}
```
- **Response (200 OK):**
```json
{
  "success": true,
  "job_id": "a4f89b1c",
  "campaign_name": "Q4 Enterprise Outreach",
  "total_recipients": 43,
  "status": "RUNNING"
}
```

---

## 6. Job Monitor & Controls (`/api/jobs`)

### 6.1 List Jobs
- **Endpoint:** `GET /api/jobs?limit=50`
- **Response (200 OK):** List of historical and active background jobs.

### 6.2 Get Active Job
- **Endpoint:** `GET /api/jobs/active`
- **Response (200 OK):**
```json
{
  "active_job": {
    "id": "a4f89b1c",
    "campaign_name": "Q4 Enterprise Outreach",
    "status": "RUNNING",
    "total_count": 43,
    "sent_count": 12,
    "failed_count": 0,
    "current_recipient": "Alex Mercer (919876543210)",
    "started_at": "2026-11-01T22:00:00"
  }
}
```

### 6.3 Job Control Actions (Pause, Resume, Cancel)
- **Endpoint:** `POST /api/jobs/{job_id}/action`
- **Request Body:** `{ "action": "pause" }` (or `"resume"`, `"cancel"`)
- **Response (200 OK):** `{ "success": true, "action": "pause", "job_id": "a4f89b1c" }`

### 6.4 Durable Queue Inspection
- **Endpoint:** `GET /api/jobs/{job_id}/queue?status={status}&limit=100&offset=0`
- **Response (200 OK):**
```json
{
  "job_id": "a4f89b1c",
  "total_queued": 43,
  "stats": { "PENDING": 10, "DISPATCHED": 30, "SUPPRESSED": 2, "FAILED_PERMANENT": 1 },
  "items": [
    {
      "id": 1,
      "idempotency_key": "3a7b9e...",
      "recipient_name": "Alice",
      "recipient_phone": "14155552671",
      "variant_purpose": "Spanish Localization",
      "retry_count": 0,
      "max_retries": 3,
      "status": "DISPATCHED",
      "dispatched_at": "2026-11-01T22:05:00"
    }
  ]
}
```

### 6.5 Export Job Report CSV
- **Endpoint:** `GET /api/jobs/{job_id}/export`
- **Response:** Downloadable CSV file containing delivery log rows: `Job ID`, `Campaign`, `Recipient Name`, `Phone`, `Status`, `Error Details`, `Attachment`, `Timestamp`.

---

## 7. Configuration & System Diagnostics (`/api/config`)

### 7.1 Get Configuration
- **Endpoint:** `GET /api/config`
- **Response (200 OK):** Current delay settings, active preset, and available presets.

### 7.2 Update Configuration
- **Endpoint:** `PUT /api/config`
- **Request Body:**
```json
{
  "min_delay": 8.0,
  "max_delay": 15.0,
  "batch_size": 20,
  "batch_pause": 60.0,
  "daily_cap": 150
}
```
- **Response (200 OK):** `{ "success": true, "message": "Configuration updated successfully" }`

### 7.3 Apply Anti-Ban Preset
- **Endpoint:** `POST /api/config/preset`
- **Request Body:** `{ "preset_name": "safe" }` (or `"balanced"`, `"fast"`)
- **Response (200 OK):**
```json
{
  "success": true,
  "applied_preset": "safe",
  "preset_details": {
    "name": "🛡️ Safe Warm-up",
    "min_delay": 12.0,
    "max_delay": 20.0,
    "batch_size": 15,
    "batch_pause": 90.0,
    "daily_cap": 30
  }
}
```

### 7.4 Hardware System Diagnostics
- **Endpoint:** `GET /api/config/system-info`
- **Response (200 OK):**
```json
{
  "device_id": "HWID-A48F9B1C-E3D2",
  "system": "Windows",
  "machine": "AMD64",
  "processor": "AMD64 Family 25 Model 80 Stepping 0",
  "ram_total_gb": 16.0
}
```

---

## 8. Real-time WebSocket Protocol (`/ws`)

- **URL:** `ws://127.0.0.1:8000/ws`
- **Protocol:** JSON message streams

### Handshake & Connection Established
Immediately upon connection, the server sends:
```json
{
  "type": "connection_established",
  "active_job": null
}
```

### Heartbeat Ping-Pong
Clients send string `"ping"` every 15 seconds; server responds with `"pong"`.

### Live Job Progress Broadcast
```json
{
  "type": "job_progress",
  "job_id": "a4f89b1c",
  "current": 14,
  "total": 50,
  "percentage": 28.0,
  "sent": 14,
  "failed": 0,
  "contact": {
    "name": "Sarah Connor",
    "phone": "14155552671",
    "status": "SENT",
    "error": ""
  }
}
```

### Live Log Event Broadcast
```json
{
  "type": "log_event",
  "timestamp": "22:15:30",
  "level": "INFO",
  "message": "[14/50] Dispatching to Sarah Connor (+1 415*** **71)..."
}
```

