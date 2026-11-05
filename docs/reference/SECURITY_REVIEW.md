# Security Review and Threat Analysis

This document details the security posture, threat modeling, input validation, file handling protections, and local host boundaries established for the WhatsApp Automation Web Dashboard.

---

## 1. Threat Model & Risk Analysis

The transition from a standalone desktop GUI to a local web server (FastAPI + browser frontend) shifts the security boundary from purely OS-process execution to HTTP/WebSocket networking. Even when operated on a single user workstation, web applications face distinct risk vectors that must be actively mitigated.

| Threat Category | Potential Attack Vector | Impact Level | Mitigation Implemented |
| :--- | :--- | :--- | :--- |
| **Remote Network Exposure** | Binding to `0.0.0.0` or open network interfaces | Critical | Server is bound strictly to `127.0.0.1` (localhost). It does not accept remote network traffic by default. |
| **Cross-Origin Resource Sharing (CORS)** | Malicious websites sending cross-origin requests to `http://localhost:8000` | High | Strict CORS policy allowing only `http://localhost:8000`, `http://127.0.0.1:8000`, and Vite development ports (`5173`). Wildcard `*` origins are rejected for credentialed requests. |
| **Arbitrary File Upload & Overwrite** | Malicious filenames in contact/media uploads attempting path traversal (`../../`) | High | Filenames are sanitized via `os.path.basename()`. File uploads are saved with UUIDs or quarantined in dedicated directories. File size limits are enforced. |
| **Stored Cross-Site Scripting (XSS)** | Injection of script tags into recipient names, messages, or custom fields | High | Web frontend strictly renders user text using safe DOM text bindings (`textContent`, `innerText`) or frameworks with auto-escaping. Raw HTML rendering (`innerHTML`) of unsanitized contact data is forbidden. |
| **Denial of Service (DoS) via Large Payloads** | Massive CSV/Excel files overloading memory or hung threads | Medium | Maximum file upload size capped at 15 MB. Streaming parsers and bounded batch sizes protect server memory. |
| **Credential & Session Theft** | WhatsApp Web cookies / Chrome user profile directory extraction | High | Browser profile data is stored in the local OS user directory. The Web API never serves or exposes Chrome profile tokens, authentication cookies, or session storage to client-side JavaScript. |
| **Command Injection** | Manipulating parameters passed to sub-processes | Medium | All background operations execute within in-process Python workers; no unescaped OS shell commands (`shell=True`) are invoked from API endpoints. |

---

## 2. Input Validation and Data Sanitization

### 2.1 File Upload Validation
All incoming file uploads (contacts and media attachments) pass through multi-layered checks:
1. **Extension Verification:**
   - Contact lists: strictly `.csv`, `.xlsx`, `.xls`.
   - Media attachments: strictly image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`), document (`.pdf`, `.docx`, `.txt`), or video (`.mp4`).
2. **Path Traversal Mitigation:**
   - Every file path input is resolved using `os.path.abspath()` and verified to reside inside the intended upload or project directory.
   - Any path containing `..` or null bytes is rejected with an HTTP 400 Bad Request.
3. **Payload Size Guard:**
   - Maximum upload size is enforced at 15 MB. Payloads exceeding this threshold are rejected immediately before reading into system RAM.

### 2.2 Phone Number Sanitization
- Phone numbers undergo rigorous normalization via `DataLoader.clean_phone_number()`.
- Strips unwanted characters (`-`, `(`, `)`, spaces, dots).
- Validates E.164 compliance and international prefix format.
- Invalid phone numbers are flagged and segregated before transmission, preventing malformed URL queries to WhatsApp Web.

### 2.3 Configuration Bounds Enforcement
The API enforces strict type and range boundaries on all configuration settings:
- `min_delay`: Range [1.0, 60.0] seconds.
- `max_delay`: Range [min_delay, 120.0] seconds.
- `batch_size`: Range [1, 200] messages.
- `batch_pause`: Range [5.0, 600.0] seconds.
- `daily_cap`: Range [1, 1000] messages.

Any payload violating these constraints returns HTTP 422 Unprocessable Entity with a descriptive error message.

---

## 3. Privacy & Data Masking

### 3.1 Log Masking
To prevent Personally Identifiable Information (PII) leakage into log files:
- All phone numbers written to system log files and WebSocket streams are masked: `mask_phone("+919876543210")` outputs `+91 98*** **210`.
- The full phone number is only retained in the local database and used internally by the Selenium driver for direct navigation.

### 3.2 Audit Logging
- Every action (importing contacts, creating templates, launching campaigns, pausing, cancelling) creates an immutable audit log record with timestamps, user agent, and action status.

---

## 4. Local Deployment Security Checklist

| Checkpoint | Status | Implementation Details |
| :--- | :--- | :--- |
| **Localhost-Only Binding** | PASS | FastAPI binds exclusively to `127.0.0.1`. |
| **No External Dependency CDNs** | PASS | Frontend CSS/JS is bundled or self-contained without mandatory cloud dependencies. |
| **Safe Error Envelopes** | PASS | Internal Python tracebacks are caught by exception handlers and logged server-side; API returns structured error codes and user-friendly messages. |
| **Process Isolation** | PASS | Background jobs run in isolated worker threads with thread-safe cancellation flags (`threading.Event`). |
| **Rate-Limiting on WebSockets** | PASS | WebSocket broadcast throttles high-frequency progress updates to avoid saturating browser rendering loops. |

