# 01 — System Architecture & Data Flow

## 1. Architectural Blueprint

The WhatsApp Automation Relay is engineered as a decoupled, multi-layer service. It pairs an asynchronous Python **FastAPI** backend with a lightweight, accessible **Single-Page Application (SPA)** and a thread-safe **Selenium WebDriver Automation Engine**.

```mermaid
flowchart TD
    subgraph Client ["Frontend Layer (Browser SPA)"]
        UI["Web Dashboard UI<br/>(index.html, styles.css)"]
        ClientJS["State & View Controller<br/>(app.js)"]
        WSClient["WebSocket Client<br/>(/ws telemetry)"]
    end

    subgraph API ["Backend API Layer (FastAPI)"]
        App["FastAPI Server Engine<br/>(backend/app.py)"]
        Routers["Modular Routers<br/>(/api/browser, /api/campaigns, etc.)"]
        WSHub["ConnectionManager<br/>(backend/routers/ws.py)"]
    end

    subgraph Core ["Core Automation & Engine Layer"]
        ConnMon["Intelligent Connection Monitor<br/>(backend/connection_monitor.py)"]
        JobWorker["Background Job Worker<br/>(backend/job_queue.py)"]
        BrowserMgr["Browser Profile Manager<br/>(browser_manager.py)"]
        WhatsAppAdapter["WhatsApp Web Adapter<br/>(backend/adapter.py)"]
    end

    subgraph Persistence ["Persistence & File Storage Layer"]
        SQLite[("SQLite Database<br/>whatsapp_web.db")]
        ConfigJSON["JSON Configuration<br/>config.json"]
        SessionStore["Dedicated Profile Store<br/>whatsapp_browser_session/"]
    end

    UI --> ClientJS
    ClientJS <-->|REST API JSON| Routers
    WSClient <-->|Real-Time Push| WSHub
    Routers --> App
    WSHub --> App
    Routers --> JobWorker
    Routers --> ConnMon
    Routers --> BrowserMgr
    JobWorker <--> ConnMon
    JobWorker --> WhatsAppAdapter
    ConnMon --> WhatsAppAdapter
    WhatsAppAdapter --> BrowserMgr
    JobWorker <--> SQLite
    Routers <--> SQLite
    Routers <--> ConfigJSON
    BrowserMgr <--> SessionStore
```

---

## 2. Component & Directory Hierarchy

```
whatsapp automation/
├── backend/                        # Backend Application Package
│   ├── app.py                      # FastAPI initialization, static mount, lifespan, exception hooks
│   ├── database.py                 # SQLite database layer, schemas, indexes, and migrations
│   ├── connection_monitor.py       # 10-state lifecycle observer and state machine
│   ├── job_queue.py                # Background campaign queue worker, retries, and rate limiting
│   ├── models.py                   # Pydantic schemas for request/response validation
│   ├── adapter.py                  # Messaging provider abstraction (WhatsApp Web vs Mock)
│   ├── routers/                    # Modular API route controllers
│   │   ├── browser.py              # Profile scanning, locking checks, session launches
│   │   ├── campaigns.py            # Campaign CRUD, queue dispatching, and pre-flight checks
│   │   ├── contacts.py             # Contact import/export, grouping, and consent tracking
│   │   ├── templates.py            # Template CRUD, variable extraction, and dynamic previews
│   │   ├── jobs.py                 # Job inspection, pause, resume, cancel, drawer modal details
│   │   ├── logs.py                 # Activity event querying and KPI aggregations
│   │   ├── config.py               # Application configuration and safety limits
│   │   ├── media.py                # Media asset upload and mime-type validation
│   │   └── ws.py                   # WebSocket connection pool and telemetry broadcaster
│   └── static/                     # Frontend Client Bundle
│       ├── index.html              # Semantic HTML5 dashboard, forms, and modal drawers
│       ├── styles.css              # Design tokens, Light & Void themes, accessible radio cards
│       └── app.js                  # Vanilla JS SPA controller, reactive bindings, and toast notifications
├── browser_manager.py              # Local browser profile detection (Chrome, Edge, Brave, Firefox)
├── config_manager.py               # Atomic JSON configuration reader/writer
├── logger.py                       # Structured rotating logger with phone number masking
├── whatsapp_engine.py              # Low-level Selenium WhatsApp Web automation driver
├── start_dashboard.bat             # One-click Windows startup script
└── tests/                          # Automated Pytest Suite (49 tests)
    ├── test_api.py                 # REST endpoint integration tests
    └── test_connection_monitoring.py # Connection state machine and queue recovery tests
```

---

## 3. Database Schema Design (`whatsapp_web.db`)

All data is stored locally in SQLite with full foreign keys, write-ahead logging (WAL), and optimized indexes.

```mermaid
erDiagram
    CONTACT_GROUPS ||--o{ CONTACTS : contains
    TEMPLATES ||--o{ MESSAGE_VARIANTS : has
    TEMPLATES ||--o{ CAMPAIGNS : configures
    CAMPAIGNS ||--o{ JOBS : executes
    JOBS ||--o{ CAMPAIGN_QUEUE_ITEMS : processes
    JOBS ||--o{ JOB_RESULTS : records

    CONTACTS {
        int id PK
        string name
        string phone
        string raw_phone
        json custom_fields_json
        string group_name FK
        string consent_status
        string consent_source
        timestamp created_at
    }

    SUPPRESSION_LIST {
        int id PK
        string phone UK
        string reason
        timestamp created_at
    }

    TEMPLATES {
        int id PK
        string name UK
        string content
        json variables_json
        timestamp created_at
    }

    MESSAGE_VARIANTS {
        int id PK
        int template_id FK
        string variant_name
        string purpose
        string content
    }

    CAMPAIGNS {
        int id PK
        string name
        int template_id FK
        string group_name
        float min_delay
        float max_delay
        int batch_size
        float batch_pause
        int daily_cap
        string status
    }

    JOBS {
        string id PK
        string campaign_name
        string status
        int total_count
        int sent_count
        int failed_count
        int suppressed_count
        string current_recipient
        timestamp started_at
        timestamp completed_at
    }

    CAMPAIGN_QUEUE_ITEMS {
        int id PK
        string job_id FK
        string idempotency_key UK
        string recipient_name
        string recipient_phone
        string resolved_message
        string status
        int retry_count
        int max_retries
    }

    JOB_RESULTS {
        int id PK
        string job_id FK
        string name
        string phone
        string status
        string error_message
        timestamp timestamp
    }
```

### Table Definitions & Purpose
1. **`contacts` & `contact_groups`**: Stores audience records with phone normalization (E.164 compliance), arbitrary custom field JSON payloads, and consent audit trails (`opted_in`, `opted_out`).
2. **`suppression_list`**: Global DNC (Do Not Call / Opt-Out) blacklist. Checked deterministically before any message dispatch.
3. **`templates` & `message_variants`**: Reusable message blueprints with template variables (`{{name}}`, `{{company}}`) and purpose-driven A/B/C variants.
4. **`campaigns`**: Configuration recipes specifying pace delays, batch sizes, audience filters, and attachments.
5. **`jobs`**: Historical and active execution instances tracking progress counters, timestamps, and execution states.
6. **`campaign_queue_items`**: Durable item queue with unique SHA-256 idempotency keys. Protects against duplicate deliveries during connection interruption.
7. **`job_results`**: Immutable delivery audit trail with error codes, timestamps, and message payloads.
8. **`logs`**: Structured application event logs for KPI calculation and audit investigations.

---

## 4. End-to-End Data & Execution Flow

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant UI as Browser SPA (app.js)
    participant API as FastAPI Router
    participant Queue as BackgroundJobWorker
    participant Mon as ConnectionMonitor
    participant Chrome as Chrome WhatsApp Web
    participant DB as SQLite Database
    participant WS as WebSocket Hub

    Operator->>UI: Clicks "Launch Campaign"
    UI->>API: POST /api/campaigns/{id}/run
    API->>Mon: Check connection status
    alt Session is NOT connected (e.g. waiting_for_qr)
        API->>DB: Create Job (status='WAITING_FOR_CONNECTION')
        API-->>UI: 200 OK (Job queued, waiting for scan)
        UI->>UI: Show Amber "Waiting for QR" Banner
        Note over Operator,Chrome: Operator scans QR with phone
        Mon->>Chrome: Observes chat list container
        Mon->>Queue: Notify state change -> 'connected'
        Queue->>DB: Update Job status -> 'RUNNING'
        Queue->>WS: Broadcast {event: 'job_resumed'}
        WS-->>UI: Live update to Running state
    else Session is connected
        API->>DB: Create Job (status='RUNNING')
        API-->>UI: 200 OK (Job started)
    end

    loop For Each Recipient in Queue
        Queue->>DB: Check suppression list & idempotency key
        Queue->>Mon: Verify browser session still alive
        Queue->>Chrome: Navigate to wa.me/{phone} & send text
        Chrome-->>Queue: Message delivered / tick detected
        Queue->>DB: Record item status='SENT' in job_results
        Queue->>WS: Broadcast {sent_count, current_recipient}
        WS-->>UI: Update progress bar & activity ticker
        Queue->>Queue: Sleep randomized anti-ban delay (e.g. 8-15s)
    end

    Queue->>DB: Update Job status -> 'COMPLETED'
    Queue->>WS: Broadcast {status: 'COMPLETED'}
    WS-->>UI: Display completion toast & summary metrics
```

