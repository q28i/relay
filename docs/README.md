# Project Documentation Repository (`docs/`)

Welcome to the centralized documentation hub for the **WhatsApp Automation Relay** project. All documentation, system architecture specifications, phase delivery reports, test verification matrices, operational runbooks, and visual screenshot artifacts are kept organized within this directory.

---

## 🗂️ Documentation Directory Structure

```
docs/
├── handoff/                          # The 11-Part Engineering Handoff Documentation Suite
│   ├── README.md                     # Handoff Navigation & Quick-Start Guide
│   ├── 00_EXECUTIVE_SUMMARY.md       # High-Level Project Overview & Metrics
│   ├── 01_SYSTEM_ARCHITECTURE.md     # FastAPI, SQLite Schema, & Data Flow Sequence
│   ├── 02_BROWSER_AUTOMATION_AND_PROFILES.md # Browser Discovery, Lockfile Diagnostics, & Two Models
│   ├── 03_CONNECTION_MONITORING_ENGINE.md    # 10-State Lifecycle Machine & DOM Heuristics
│   ├── 04_CAMPAIGN_QUEUE_AND_EXECUTION.md    # Background Worker, Pre-Flight Gating, & Idempotency
│   ├── 05_UI_UX_AND_DESIGN_SYSTEM.md # Light & Void Themes, WhatsApp Web Preview, & Radio Cards
│   ├── 06_API_AND_WEBSOCKET_REFERENCE.md     # REST Endpoints & WebSocket Event Schemas
│   ├── 07_TESTING_AND_VERIFICATION_MATRIX.md # 49-Test Suite & Playwright E2E Verification
│   ├── 08_OPERATIONS_AND_RUNBOOK.md  # Runbook, Startup Scripts, & Incident Troubleshooting
│   ├── 09_CHRONOLOGICAL_CHANGELOG.md # Chronological Log of All Phases & Fixes
│   └── 10_PERSISTENT_MEDIA_REAL_CONTACTS_AND_CAMPAIGN_ALLOCATION.md # Media, Contacts & Allocation
│
├── reports/                          # Detailed Phase Delivery Reports
│   ├── 01_dashboard_redesign_report.md
│   ├── 02_ship_readiness_audit_report.md
│   ├── 03_messaging_connection_report.md
│   ├── 04_skill_guided_redesign_report.md
│   ├── 05_product_ui_redesign_report.md
│   ├── 06_browser_profile_fix_report.md
│   ├── 07_browser_profile_lock_and_connection_report.md
│   ├── 08_void_theme_delivery_report.md
│   ├── 09_connection_monitoring_and_progress_report.md
│   ├── 10_fake_interactive_cards_fix_report.md
│   └── 11_persistent_media_and_contacts_report.md
│
├── screenshots/                      # 59 Automated Verification Screenshots & Visual Proof
│   ├── screen_theme_cards_void.png
│   ├── screen_theme_cards_light.png
│   ├── screen_connection_model_dedicated.png
│   ├── screen_connection_model_existing.png
│   ├── screen_pace_cards.png
│   ├── screen_conn_waiting_qr.png
│   ├── screen_conn_connected.png
│   ├── screen_conn_blocked_campaign.png
│   ├── screen_conn_resumed_campaign.png
│   ├── screen_void_dashboard.png
│   ├── screen_void_messages.png
│   └── ... (all 59 visual artifacts)
│
├── reference/                        # Technical Specifications & System References
│   ├── ARCHITECTURE.md               # Original System Architecture
│   ├── API_DOCUMENTATION.md          # REST API Detailed Specs
│   ├── DEPLOYMENT.md                 # Deployment & Cloudflare Workers Guide
│   ├── DOCUMENTATION.md              # Core Project Documentation
│   ├── FEATURE_MAP.md                # Feature Inventory & Capabilities
│   ├── PROJECT_DOCUMENTATION.md      # Comprehensive Project Reference
│   ├── SECURITY_REVIEW.md            # Security Hardening & Threat Model
│   ├── TECHNICAL_DEBT.md             # Technical Debt Analysis & Resolution
│   └── TESTING.md                    # Original Test Plan & Strategies
│
└── plans/                            # Migration, Redesign & Planning Documents
    ├── MIGRATION_PLAN.md             # Migration Plan from Legacy Tkinter GUI
    ├── REDESIGN_PLAN.md              # Web Dashboard UX Redesign Plan
    ├── REFACTORING_PLAN.md           # Architecture Refactoring Roadmap
    ├── SKILL_USAGE.md                # Custom Skill Usage Log
    └── 2026-11-02-intelligent-connection-monitoring-and-job-progress.md
```

---

## 🧭 Subdirectory Guides

### 1. [Handoff Documentation Suite](handoff/README.md)
The canonical handoff package detailing the complete modernization of the platform into a web-based, state-driven, resilient automation relay. Covers system architecture, browser automation, the 10-state connection monitor, background job queueing, the accessible design system, and operational runbooks.

### 2. [Phase Delivery Reports](reports/)
Granular engineering delivery reports compiled at the conclusion of each sprint/phase, documenting root-cause diagnoses, specific bug fixes, before/after code comparisons, and automated verification results.

### 3. [Visual Screenshots & Evidence](screenshots/)
A library of 59 high-resolution screenshots captured during headless browser tests (Playwright and Selenium), verifying UI responsiveness, color contrast, theme fidelity, connection states, and modal interactions across both Light and Void themes.

### 4. [Technical Reference Specs](reference/)
Deep-dive reference manuals for specific subsystems, including Cloudflare Worker edge deployment, API contracts, security threat modeling, and technical debt audit logs.

### 5. [Planning & Design Contracts](plans/)
Strategic roadmaps and design contracts that guided the transition from the legacy Tkinter desktop tool to the modern web platform.

