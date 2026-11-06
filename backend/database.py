"""
Database Manager for WhatsApp Automation Web Dashboard.
Uses SQLite for zero-configuration, thread-safe, resilient local persistence.
Provides schemas and query helpers for contacts, groups, consent, suppression lists,
media assets, purpose-driven message variants, durable queue items, jobs, and logs.
"""

import os
import re
import json
import sqlite3
import threading
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime

DB_PATH = os.environ.get("RELAY_DB_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "whatsapp_web.db")
_lock = threading.RLock()


def normalize_phone(raw: str) -> str:
    """Normalizes phone number to purely digits, stripping leading '+' and non-digit characters."""
    if not raw:
        return ""
    cleaned = re.sub(r"[^\d]", "", str(raw))
    return cleaned


class DatabaseManager:
    """Thread-safe SQLite database manager for web dashboard state."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("RELAY_DB_PATH") or DB_PATH
        self._init_db()

    def set_db_path(self, new_path: str):
        """Switches the database file path dynamically (useful for test isolation)."""
        with _lock:
            self.db_path = new_path
            self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a sqlite3 connection configured with row dict access."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes tables and default seed data if not present."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 1. Contact Groups
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS contact_groups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT DEFAULT '',
                        created_at TEXT NOT NULL
                    )
                """)

                # 2. Contacts
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        raw_phone TEXT DEFAULT '',
                        custom_fields_json TEXT DEFAULT '{}',
                        group_name TEXT DEFAULT 'Default',
                        customer_tier TEXT DEFAULT 'Regular',
                        language TEXT DEFAULT 'en',
                        consent_status TEXT DEFAULT 'opted_in',
                        consent_source TEXT DEFAULT 'direct_import',
                        consent_timestamp TEXT,
                        opt_out_timestamp TEXT,
                        opt_out_reason TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (group_name) REFERENCES contact_groups (name) ON DELETE SET DEFAULT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts (phone)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_group ON contacts (group_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_consent ON contacts (consent_status)")

                # Backward compatibility check: Add missing columns if missing from earlier schema
                cursor.execute("PRAGMA table_info(contacts)")
                existing_cols = {row["name"] for row in cursor.fetchall()}
                if "customer_tier" not in existing_cols:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN customer_tier TEXT DEFAULT 'Regular'")
                if "language" not in existing_cols:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN language TEXT DEFAULT 'en'")
                if "consent_status" not in existing_cols:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN consent_status TEXT DEFAULT 'opted_in'")
                if "consent_source" not in existing_cols:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN consent_source TEXT DEFAULT 'direct_import'")
                if "consent_timestamp" not in existing_cols:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN consent_timestamp TEXT")
                if "opt_out_timestamp" not in existing_cols:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN opt_out_timestamp TEXT")
                if "opt_out_reason" not in existing_cols:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN opt_out_reason TEXT DEFAULT ''")

                # 3. Global Suppression / Opt-Out List
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS suppression_list (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone TEXT UNIQUE NOT NULL,
                        reason TEXT NOT NULL,
                        source TEXT DEFAULT 'manual',
                        created_at TEXT NOT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppression_phone ON suppression_list (phone)")

                # 4. Approved Media Assets Library
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS media_assets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        mime_type TEXT NOT NULL,
                        asset_type TEXT NOT NULL,
                        content_hash TEXT DEFAULT '',
                        approval_status TEXT DEFAULT 'approved',
                        created_at TEXT NOT NULL
                    )
                """)
                cursor.execute("PRAGMA table_info(media_assets)")
                media_cols = {row["name"] for row in cursor.fetchall()}
                if "content_hash" not in media_cols:
                    cursor.execute("ALTER TABLE media_assets ADD COLUMN content_hash TEXT DEFAULT ''")

                # 5. Templates (Unified Bulk Messaging Engine)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS templates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        content TEXT NOT NULL,
                        variables_json TEXT DEFAULT '[]',
                        description TEXT DEFAULT '',
                        content_selection_mode TEXT DEFAULT 'mix_variations',
                        message_format TEXT DEFAULT 'image_with_caption',
                        target_group TEXT DEFAULT 'All',
                        pacing_delay_min INTEGER DEFAULT 8,
                        pacing_delay_max INTEGER DEFAULT 16,
                        is_archived INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                cursor.execute("PRAGMA table_info(templates)")
                tpl_cols = {row["name"] for row in cursor.fetchall()}
                if "content_selection_mode" not in tpl_cols:
                    cursor.execute("ALTER TABLE templates ADD COLUMN content_selection_mode TEXT DEFAULT 'mix_variations'")
                if "message_format" not in tpl_cols:
                    cursor.execute("ALTER TABLE templates ADD COLUMN message_format TEXT DEFAULT 'image_with_caption'")
                if "description" not in tpl_cols:
                    cursor.execute("ALTER TABLE templates ADD COLUMN description TEXT DEFAULT ''")
                if "target_group" not in tpl_cols:
                    cursor.execute("ALTER TABLE templates ADD COLUMN target_group TEXT DEFAULT 'All'")
                if "pacing_delay_min" not in tpl_cols:
                    cursor.execute("ALTER TABLE templates ADD COLUMN pacing_delay_min INTEGER DEFAULT 8")
                if "pacing_delay_max" not in tpl_cols:
                    cursor.execute("ALTER TABLE templates ADD COLUMN pacing_delay_max INTEGER DEFAULT 16")
                if "is_archived" not in tpl_cols:
                    cursor.execute("ALTER TABLE templates ADD COLUMN is_archived INTEGER DEFAULT 0")

                # Unified Template Child Tables
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS template_media_assets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        template_id INTEGER NOT NULL,
                        media_asset_id INTEGER NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        sort_order INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE,
                        FOREIGN KEY (media_asset_id) REFERENCES media_assets (id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_tpl_media ON template_media_assets (template_id)")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS template_text_variations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        template_id INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        sort_order INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_tpl_text ON template_text_variations (template_id)")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS template_contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        template_id INTEGER NOT NULL,
                        contact_id INTEGER NOT NULL,
                        is_excluded INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE,
                        FOREIGN KEY (contact_id) REFERENCES contacts (id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_tpl_contact ON template_contacts (template_id)")

                # 6. Purpose-Driven Message Variants
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS message_variants (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        template_id INTEGER,
                        variant_name TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        audience_filter_field TEXT DEFAULT '',
                        audience_filter_value TEXT DEFAULT '',
                        content TEXT NOT NULL,
                        media_asset_id INTEGER,
                        approval_status TEXT DEFAULT 'approved',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE,
                        FOREIGN KEY (media_asset_id) REFERENCES media_assets (id) ON DELETE SET NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_variants_template ON message_variants (template_id)")

                # 7. Campaigns
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS campaigns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        template_id INTEGER,
                        group_name TEXT DEFAULT 'Default',
                        min_delay REAL DEFAULT 8.0,
                        max_delay REAL DEFAULT 15.0,
                        batch_size INTEGER DEFAULT 20,
                        batch_pause REAL DEFAULT 60.0,
                        daily_cap INTEGER DEFAULT 100,
                        attachment_path TEXT DEFAULT '',
                        media_asset_id INTEGER,
                        allocation_method TEXT DEFAULT 'explicit_default',
                        allocation_seed INTEGER DEFAULT 42,
                        status TEXT DEFAULT 'draft',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE SET NULL,
                        FOREIGN KEY (media_asset_id) REFERENCES media_assets (id) ON DELETE SET NULL
                    )
                """)
                cursor.execute("PRAGMA table_info(campaigns)")
                camp_cols = {row["name"] for row in cursor.fetchall()}
                if "media_asset_id" not in camp_cols:
                    cursor.execute("ALTER TABLE campaigns ADD COLUMN media_asset_id INTEGER")
                if "allocation_method" not in camp_cols:
                    cursor.execute("ALTER TABLE campaigns ADD COLUMN allocation_method TEXT DEFAULT 'explicit_default'")
                if "allocation_seed" not in camp_cols:
                    cursor.execute("ALTER TABLE campaigns ADD COLUMN allocation_seed INTEGER DEFAULT 42")

                # 8. Jobs
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        campaign_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        total_count INTEGER DEFAULT 0,
                        sent_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        suppressed_count INTEGER DEFAULT 0,
                        current_recipient TEXT DEFAULT '',
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        error_message TEXT DEFAULT ''
                    )
                """)

                # Backward compatibility check for jobs table
                cursor.execute("PRAGMA table_info(jobs)")
                job_cols = {row["name"] for row in cursor.fetchall()}
                if "suppressed_count" not in job_cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN suppressed_count INTEGER DEFAULT 0")
                if "scheduled_at" not in job_cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN scheduled_at TEXT")
                if "updated_at" not in job_cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN updated_at TEXT")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)")

                # 9. Durable Campaign Queue Items with Idempotency
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS campaign_queue_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        campaign_id INTEGER,
                        job_id TEXT NOT NULL,
                        idempotency_key TEXT UNIQUE NOT NULL,
                        recipient_name TEXT NOT NULL,
                        recipient_phone TEXT NOT NULL,
                        variant_id INTEGER,
                        variant_purpose TEXT DEFAULT '',
                        resolved_message TEXT NOT NULL,
                        media_path TEXT DEFAULT '',
                        media_asset_id INTEGER,
                        allocation_rule TEXT DEFAULT '',
                        message_format TEXT DEFAULT 'image_with_caption',
                        status TEXT NOT NULL,
                        retry_count INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 3,
                        error_message TEXT DEFAULT '',
                        dispatched_at TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("PRAGMA table_info(campaign_queue_items)")
                queue_cols = {row["name"] for row in cursor.fetchall()}
                if "media_asset_id" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN media_asset_id INTEGER")
                if "allocation_rule" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN allocation_rule TEXT DEFAULT ''")
                if "message_format" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN message_format TEXT DEFAULT 'image_with_caption'")
                if "media_status" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN media_status TEXT DEFAULT 'PENDING'")
                if "text_status" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN text_status TEXT DEFAULT 'PENDING'")
                if "overall_status" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN overall_status TEXT DEFAULT 'PENDING'")
                if "last_successful_stage" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN last_successful_stage TEXT DEFAULT 'none'")
                if "recovery_eligibility" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN recovery_eligibility TEXT DEFAULT 'retry_all'")
                if "stage_retry_count" not in queue_cols:
                    cursor.execute("ALTER TABLE campaign_queue_items ADD COLUMN stage_retry_count INTEGER DEFAULT 0")

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_job_status ON campaign_queue_items (job_id, status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_idempotency ON campaign_queue_items (idempotency_key)")

                # 10. Job Results (Detailed history)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS job_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        status TEXT NOT NULL,
                        error TEXT DEFAULT '',
                        attachment TEXT DEFAULT '',
                        media_status TEXT DEFAULT '',
                        text_status TEXT DEFAULT '',
                        overall_status TEXT DEFAULT '',
                        last_successful_stage TEXT DEFAULT '',
                        recovery_eligibility TEXT DEFAULT '',
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results (job_id)")
                cursor.execute("PRAGMA table_info(job_results)")
                jr_cols = {row["name"] for row in cursor.fetchall()}
                if "media_status" not in jr_cols:
                    cursor.execute("ALTER TABLE job_results ADD COLUMN media_status TEXT DEFAULT ''")
                if "text_status" not in jr_cols:
                    cursor.execute("ALTER TABLE job_results ADD COLUMN text_status TEXT DEFAULT ''")
                if "overall_status" not in jr_cols:
                    cursor.execute("ALTER TABLE job_results ADD COLUMN overall_status TEXT DEFAULT ''")
                if "last_successful_stage" not in jr_cols:
                    cursor.execute("ALTER TABLE job_results ADD COLUMN last_successful_stage TEXT DEFAULT ''")
                if "recovery_eligibility" not in jr_cols:
                    cursor.execute("ALTER TABLE job_results ADD COLUMN recovery_eligibility TEXT DEFAULT ''")

                # 11. Audit Logs
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        module TEXT NOT NULL,
                        message TEXT NOT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs (timestamp DESC)")

                # 12. Content Collections
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS content_collections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        pairing_mode TEXT DEFAULT 'fixed_pair',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS collection_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collection_id INTEGER NOT NULL,
                        item_type TEXT NOT NULL,
                        template_id INTEGER,
                        media_asset_id INTEGER,
                        FOREIGN KEY (collection_id) REFERENCES content_collections (id) ON DELETE CASCADE,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE,
                        FOREIGN KEY (media_asset_id) REFERENCES media_assets (id) ON DELETE CASCADE
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS collection_pairs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collection_id INTEGER NOT NULL,
                        template_id INTEGER NOT NULL,
                        media_asset_id INTEGER,
                        pair_label TEXT DEFAULT '',
                        audience_rule TEXT DEFAULT '',
                        FOREIGN KEY (collection_id) REFERENCES content_collections (id) ON DELETE CASCADE,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE,
                        FOREIGN KEY (media_asset_id) REFERENCES media_assets (id) ON DELETE SET NULL
                    )
                """)

                # 13. Reusable Content Sets (Text Sets & Media Sets)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS content_sets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        set_type TEXT NOT NULL, -- 'text' or 'media'
                        description TEXT DEFAULT '',
                        allocation_mode TEXT DEFAULT 'balanced', -- 'balanced', 'random', 'rules', 'fixed'
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS content_set_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        set_id INTEGER NOT NULL,
                        item_type TEXT NOT NULL, -- 'text' or 'media'
                        template_id INTEGER,
                        media_asset_id INTEGER,
                        is_included INTEGER DEFAULT 1, -- 1 = Included in campaign, 0 = Excluded / Skipped
                        sort_order INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (set_id) REFERENCES content_sets (id) ON DELETE CASCADE,
                        FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE,
                        FOREIGN KEY (media_asset_id) REFERENCES media_assets (id) ON DELETE CASCADE
                    )
                """)

                # 14. Persistent Browser Profile Preferences
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS browser_profile_preferences (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        browser_id TEXT NOT NULL DEFAULT 'chrome',
                        browser_family TEXT NOT NULL DEFAULT 'chrome',
                        browser_exe_path TEXT DEFAULT '',
                        profile_display_name TEXT NOT NULL DEFAULT 'whatsapp auto',
                        canonical_profile_dir TEXT NOT NULL DEFAULT 'Profile 10',
                        connection_mode TEXT NOT NULL DEFAULT 'existing_profile',
                        remember_profile INTEGER NOT NULL DEFAULT 1,
                        auto_connect INTEGER NOT NULL DEFAULT 0,
                        last_selected_at TEXT,
                        last_connected_at TEXT,
                        schema_version INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Ensure separate persistence columns exist for preferred personal profile vs active automation session
                new_pref_cols = [
                    ("preferred_personal_browser", "TEXT DEFAULT 'chrome'"),
                    ("preferred_personal_profile_dir", "TEXT DEFAULT 'Profile 10'"),
                    ("preferred_personal_profile_name", "TEXT DEFAULT 'whatsapp auto'"),
                    ("preferred_personal_is_supported", "INTEGER DEFAULT 0"),
                    ("selected_automation_mode", "TEXT DEFAULT 'dedicated'"),
                    ("active_relay_session_dir", "TEXT DEFAULT '__dedicated__'"),
                    ("active_relay_session_name", "TEXT DEFAULT 'Relay Automation Session'"),
                    ("last_connected_browser", "TEXT DEFAULT 'chrome'"),
                    ("last_connected_profile_dir", "TEXT DEFAULT '__dedicated__'"),
                    ("last_connected_profile_name", "TEXT DEFAULT 'Relay Automation Session'"),
                    ("last_connected_mode", "TEXT DEFAULT 'dedicated'"),
                    ("last_connected_was_authenticated", "INTEGER DEFAULT 1"),
                ]
                for col_name, col_def in new_pref_cols:
                    try:
                        cursor.execute(f"ALTER TABLE browser_profile_preferences ADD COLUMN {col_name} {col_def}")
                    except sqlite3.OperationalError:
                        pass

                # Seed default audience group if empty
                cursor.execute("SELECT COUNT(*) as count FROM contact_groups")
                if cursor.fetchone()["count"] == 0:
                    now = datetime.now().isoformat()
                    cursor.execute("INSERT INTO contact_groups (name, description, created_at) VALUES (?, ?, ?)",
                                   ("Default", "Standard contacts list", now))

                conn.commit()

    # --- Contact Operations ---

    def get_contacts(self, group_name: Optional[str] = None, search: Optional[str] = None, consent_status: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM contacts WHERE 1=1"
            params = []
            if group_name and group_name != "All":
                query += " AND group_name = ?"
                params.append(group_name)
            if consent_status and consent_status != "All":
                query += " AND consent_status = ?"
                params.append(consent_status)
            if search:
                query += " AND (name LIKE ? OR phone LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def count_contacts(self, group_name: Optional[str] = None, search: Optional[str] = None, consent_status: Optional[str] = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) as count FROM contacts WHERE 1=1"
            params = []
            if group_name and group_name != "All":
                query += " AND group_name = ?"
                params.append(group_name)
            if consent_status and consent_status != "All":
                query += " AND consent_status = ?"
                params.append(consent_status)
            if search:
                query += " AND (name LIKE ? OR phone LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            cursor.execute(query, params)
            return cursor.fetchone()["count"]

    def add_contact(
        self,
        name: str,
        phone: str,
        raw_phone: str = "",
        custom_fields: Optional[Dict[str, Any]] = None,
        group_name: str = "Default",
        consent_status: str = "opted_in",
        consent_source: str = "direct_import",
        customer_tier: str = "Regular",
        language: str = "en",
        deduplicate: bool = False
    ) -> int:
        norm_phone = normalize_phone(phone)
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if deduplicate and norm_phone:
                    cursor.execute("SELECT id, name, phone FROM contacts")
                    for row in cursor.fetchall():
                        if normalize_phone(row["phone"]) == norm_phone:
                            raise ValueError(f"Contact with phone number '{phone}' already exists (matches contact #{row['id']} '{row['name']}').")

                now = datetime.now().isoformat()
                fields_json = json.dumps(custom_fields or {})
                cursor.execute("""
                    INSERT INTO contacts (name, phone, raw_phone, custom_fields_json, group_name, consent_status, consent_source, customer_tier, language, consent_timestamp, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, phone, raw_phone, fields_json, group_name, consent_status, consent_source, customer_tier, language, now, now))
                conn.commit()
                return cursor.lastrowid

    def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_campaigns(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            return [dict(r) for r in cursor.fetchall()]

    def delete_campaign(self, campaign_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
                conn.commit()
                return cursor.rowcount > 0

    def bulk_add_contacts(
        self,
        contacts: List[Dict[str, Any]],
        group_name: str = "Default",
        consent_source: str = "spreadsheet_import"
    ) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                inserted = 0
                for c in contacts:
                    name = c.get("name", "Customer")
                    phone = c.get("phone", "")
                    raw_phone = c.get("raw_phone", phone)
                    consent = c.get("consent_status", "opted_in")
                    tier = c.get("customer_tier", "Regular")
                    lang = c.get("language", "en")
                    custom = {k: v for k, v in c.items() if k not in ("name", "phone", "raw_phone", "message", "attachment", "consent_status", "consent_source", "customer_tier", "language")}
                    cursor.execute("""
                        INSERT INTO contacts (name, phone, raw_phone, custom_fields_json, group_name, consent_status, consent_source, customer_tier, language, consent_timestamp, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (name, phone, raw_phone, json.dumps(custom), group_name, consent, consent_source, tier, lang, now, now))
                    inserted += 1
                conn.commit()
                return inserted

    def get_contact(self, contact_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("custom_fields_json"):
                try:
                    res["custom_fields"] = json.loads(res["custom_fields_json"])
                except Exception:
                    res["custom_fields"] = {}
            else:
                res["custom_fields"] = {}
            return res

    def update_contact(
        self,
        contact_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        group_name: Optional[str] = None,
        customer_tier: Optional[str] = None,
        language: Optional[str] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        consent_status: Optional[str] = None,
        consent_source: Optional[str] = None,
        opt_out_reason: Optional[str] = None,
        consent_override: bool = False
    ) -> Optional[Dict[str, Any]]:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
                current = cursor.fetchone()
                if not current:
                    return None
                current = dict(current)
                now = datetime.now().isoformat()

                # Preserve opt-out protection:
                # If currently opted_out, consent_status can only be changed to opted_in if consent_override is explicitly True.
                target_consent = current.get("consent_status", "opted_in")
                if consent_status is not None:
                    if current.get("consent_status") == "opted_out" and consent_status != "opted_out" and not consent_override:
                        target_consent = "opted_out"
                    else:
                        target_consent = consent_status

                new_name = name if name is not None else current["name"]
                new_phone = phone if phone is not None else current["phone"]
                new_group = group_name if group_name is not None else current["group_name"]
                new_tier = customer_tier if customer_tier is not None else current.get("customer_tier", "Regular")
                new_lang = language if language is not None else current.get("language", "en")
                new_source = consent_source if consent_source is not None else current.get("consent_source", "direct_import")
                new_opt_reason = opt_out_reason if opt_out_reason is not None else current.get("opt_out_reason", "")
                opt_out_ts = current.get("opt_out_timestamp")
                if target_consent == "opted_out" and not opt_out_ts:
                    opt_out_ts = now
                elif target_consent != "opted_out":
                    opt_out_ts = None

                # Custom fields update
                existing_custom = {}
                if current.get("custom_fields_json"):
                    try:
                        existing_custom = json.loads(current["custom_fields_json"])
                    except Exception:
                        pass
                if custom_fields is not None:
                    existing_custom.update(custom_fields)
                fields_json = json.dumps(existing_custom)

                cursor.execute("""
                    UPDATE contacts
                    SET name = ?, phone = ?, group_name = ?, customer_tier = ?, language = ?,
                        custom_fields_json = ?, consent_status = ?, consent_source = ?,
                        opt_out_reason = ?, opt_out_timestamp = ?
                    WHERE id = ?
                """, (new_name, new_phone, new_group, new_tier, new_lang, fields_json, target_consent, new_source, new_opt_reason, opt_out_ts, contact_id))
                conn.commit()

                # Sync with suppression list
                if target_consent == "opted_out":
                    cursor.execute("""
                        INSERT OR IGNORE INTO suppression_list (phone, reason, source, created_at)
                        VALUES (?, ?, 'contact_opt_out', ?)
                    """, (new_phone, new_opt_reason or "Contact marked as opted-out", now))
                    conn.commit()
                elif target_consent == "opted_in" and consent_override:
                    cursor.execute("DELETE FROM suppression_list WHERE phone = ?", (new_phone,))
                    conn.commit()

                self.log_event("INFO", "Contacts", f"Updated contact #{contact_id} '{new_name}' (Tier: {new_tier}, Group: {new_group}, Lang: {new_lang}, Consent: {target_consent})")
                return self.get_contact(contact_id)

    def rename_group(self, old_name: str, new_name: str, description: Optional[str] = None) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("SELECT id FROM contact_groups WHERE name = ?", (new_name,))
                existing = cursor.fetchone()
                if existing:
                    if description is not None:
                        cursor.execute("UPDATE contact_groups SET description = ? WHERE name = ?", (description, new_name))
                    cursor.execute("DELETE FROM contact_groups WHERE name = ?", (old_name,))
                else:
                    if description is not None:
                        cursor.execute("UPDATE contact_groups SET name = ?, description = ? WHERE name = ?", (new_name, description, old_name))
                    else:
                        cursor.execute("UPDATE contact_groups SET name = ? WHERE name = ?", (new_name, old_name))
                cursor.execute("UPDATE contacts SET group_name = ? WHERE group_name = ?", (new_name, old_name))
                conn.commit()
                self.log_event("INFO", "Contacts", f"Renamed contact group '{old_name}' to '{new_name}'")
                return True

    def delete_group(self, group_name: str, fallback_group: str = "Default") -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO contact_groups (name, description, created_at)
                    VALUES (?, 'Default audience', ?)
                    ON CONFLICT(name) DO NOTHING
                """, (fallback_group, now))
                cursor.execute("UPDATE contacts SET group_name = ? WHERE group_name = ?", (fallback_group, group_name))
                cursor.execute("DELETE FROM contact_groups WHERE name = ?", (group_name,))
                conn.commit()
                self.log_event("WARNING", "Contacts", f"Deleted contact group '{group_name}', contacts migrated to '{fallback_group}'")
                return True

    def bulk_move_contacts(self, contact_ids: List[int], target_group: str) -> int:
        if not contact_ids:
            return 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("INSERT OR IGNORE INTO contact_groups (name, description, created_at) VALUES (?, 'Audience group', ?)", (target_group, now))
                placeholders = ",".join("?" for _ in contact_ids)
                cursor.execute(f"UPDATE contacts SET group_name = ? WHERE id IN ({placeholders})", [target_group] + list(contact_ids))
                updated = cursor.rowcount
                conn.commit()
                self.log_event("INFO", "Contacts", f"Bulk moved {updated} contact(s) to group '{target_group}'")
                return updated

    def bulk_copy_contacts(self, contact_ids: List[int], target_group: str) -> int:
        if not contact_ids:
            return 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("INSERT OR IGNORE INTO contact_groups (name, description, created_at) VALUES (?, 'Audience group', ?)", (target_group, now))
                copied_count = 0
                for cid in contact_ids:
                    cursor.execute("SELECT * FROM contacts WHERE id = ?", (cid,))
                    c = cursor.fetchone()
                    if not c:
                        continue
                    c = dict(c)
                    cursor.execute("""
                        INSERT INTO contacts (name, phone, raw_phone, custom_fields_json, group_name, consent_status, consent_source, customer_tier, language, consent_timestamp, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (c["name"], c["phone"], c.get("raw_phone", c["phone"]), c.get("custom_fields_json", "{}"), target_group, c.get("consent_status", "opted_in"), c.get("consent_source", "direct_import"), c.get("customer_tier", "Regular"), c.get("language", "en"), now, now))
                    copied_count += 1
                conn.commit()
                self.log_event("INFO", "Contacts", f"Bulk copied {copied_count} contact(s) to group '{target_group}'")
                return copied_count

    def bulk_edit_contacts(
        self,
        contact_ids: List[int],
        customer_tier: Optional[str] = None,
        language: Optional[str] = None,
        consent_status: Optional[str] = None,
        consent_override: bool = False
    ) -> int:
        if not contact_ids:
            return 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                updated_count = 0
                for cid in contact_ids:
                    cursor.execute("SELECT * FROM contacts WHERE id = ?", (cid,))
                    row = cursor.fetchone()
                    if not row:
                        continue
                    row = dict(row)
                    target_consent = row.get("consent_status", "opted_in")
                    if consent_status is not None:
                        if row.get("consent_status") == "opted_out" and consent_status != "opted_out" and not consent_override:
                            target_consent = "opted_out"
                        else:
                            target_consent = consent_status

                    new_tier = customer_tier if customer_tier is not None else row.get("customer_tier", "Regular")
                    new_lang = language if language is not None else row.get("language", "en")
                    cursor.execute("""
                        UPDATE contacts
                        SET customer_tier = ?, language = ?, consent_status = ?
                        WHERE id = ?
                    """, (new_tier, new_lang, target_consent, cid))
                    if target_consent == "opted_out":
                        cursor.execute("""
                            INSERT OR IGNORE INTO suppression_list (phone, reason, source, created_at)
                            VALUES (?, 'Bulk opt-out update', 'contact_bulk_edit', ?)
                        """, (row["phone"], now))
                    elif target_consent == "opted_in" and consent_override:
                        cursor.execute("DELETE FROM suppression_list WHERE phone = ?", (row["phone"],))
                    updated_count += 1
                conn.commit()
                self.log_event("INFO", "Contacts", f"Bulk edited {updated_count} contact(s) (Tier: {customer_tier}, Lang: {language}, Consent: {consent_status})")
                return updated_count

    def update_contact_consent(self, contact_id: int, consent_status: str, opt_out_reason: str = "") -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT phone FROM contacts WHERE id = ?", (contact_id,))
                row = cursor.fetchone()
                phone = row["phone"] if row else None

                now = datetime.now().isoformat()
                opt_out_time = now if consent_status == "opted_out" else None
                cursor.execute("""
                    UPDATE contacts
                    SET consent_status = ?, opt_out_timestamp = ?, opt_out_reason = ?
                    WHERE id = ?
                """, (consent_status, opt_out_time, opt_out_reason, contact_id))
                conn.commit()
                updated = cursor.rowcount > 0

                if updated and phone:
                    if consent_status == "opted_out":
                        cursor.execute("""
                            INSERT OR IGNORE INTO suppression_list (phone, reason, source, created_at)
                            VALUES (?, ?, 'contact_opt_out', ?)
                        """, (phone, opt_out_reason or "Contact marked as opted-out", now))
                        conn.commit()
                    elif consent_status == "opted_in":
                        cursor.execute("DELETE FROM suppression_list WHERE phone = ?", (phone,))
                        conn.commit()

                return updated

    def delete_contact(self, contact_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
                conn.commit()
                return cursor.rowcount > 0

    def clear_contacts(self, group_name: Optional[str] = None):
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if group_name and group_name != "All":
                    cursor.execute("DELETE FROM contacts WHERE group_name = ?", (group_name,))
                else:
                    cursor.execute("DELETE FROM contacts")
                conn.commit()

    def bulk_delete_contacts(self, contact_ids: List[int]) -> int:
        if not contact_ids:
            return 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in contact_ids)
                cursor.execute(f"DELETE FROM contacts WHERE id IN ({placeholders})", list(contact_ids))
                deleted = cursor.rowcount
                conn.commit()
                self.log_event("WARNING", "Contacts", f"Bulk deleted {deleted} contact(s)")
                return deleted

    def get_identified_demo_records(self) -> List[Dict[str, Any]]:
        """
        Identifies synthetic test fixture contacts (Jane Doe, Beta User, Bulk 1/2/3, Opted Out User,
        or test phone numbers starting with 1415555), while strictly protecting genuine contacts.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts ORDER BY id ASC")
            all_contacts = [dict(r) for r in cursor.fetchall()]

            demo_records = []
            for c in all_contacts:
                name = (c.get("name") or "").strip()
                phone = normalize_phone(c.get("phone") or "")

                # Strict real user safeguard: Never classify genuine users as demo
                if name.lower() in ("gaurav", "me") or phone.startswith("9176"):
                    continue

                # Synthetic criteria
                is_synthetic_name = any(syn in name.lower() for syn in [
                    "jane doe", "beta user", "bulk 1", "bulk 2", "bulk 3", "opted out user", "demo"
                ])
                is_synthetic_phone = phone.startswith("1415555")

                if is_synthetic_name or is_synthetic_phone:
                    demo_records.append(c)

            return demo_records

    def remove_identified_demo_records(self, confirmed_ids: Optional[List[int]] = None) -> int:
        """
        Safely removes confirmed demo records after verification.
        Refuses to delete any record that is not verified as synthetic.
        """
        demo_records = self.get_identified_demo_records()
        valid_demo_ids = {r["id"] for r in demo_records}

        if confirmed_ids is not None:
            ids_to_delete = [cid for cid in confirmed_ids if cid in valid_demo_ids]
        else:
            ids_to_delete = list(valid_demo_ids)

        if not ids_to_delete:
            return 0

        return self.bulk_delete_contacts(ids_to_delete)

    def get_duplicate_contacts(self) -> List[Dict[str, Any]]:
        """
        Detects duplicate contacts grouped by normalized phone number.
        Returns clusters of duplicates with contact IDs and full record details.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts ORDER BY id ASC")
            all_contacts = [dict(r) for r in cursor.fetchall()]

            clusters = {}
            for c in all_contacts:
                norm = normalize_phone(c.get("phone") or "")
                if not norm:
                    continue
                if norm not in clusters:
                    clusters[norm] = []
                clusters[norm].append(c)

            result = []
            for norm, records in clusters.items():
                if len(records) > 1:
                    result.append({
                        "normalized_phone": norm,
                        "count": len(records),
                        "contact_ids": [r["id"] for r in records],
                        "records": records
                    })
            return result

    def merge_contacts(self, primary_id: int, duplicate_ids: List[int], merged_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Merges duplicate contacts into primary_id transactionally, updating fields and deleting duplicate records.
        """
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM contacts WHERE id = ?", (primary_id,))
                primary = cursor.fetchone()
                if not primary:
                    return False

                # Apply merged data if provided
                if merged_data:
                    for field in ("name", "group_name", "customer_tier", "language", "consent_status"):
                        if field in merged_data and merged_data[field] is not None:
                            cursor.execute(f"UPDATE contacts SET {field} = ? WHERE id = ?", (merged_data[field], primary_id))
                    if "custom_fields" in merged_data and isinstance(merged_data["custom_fields"], dict):
                        existing_custom = json.loads(primary["custom_fields_json"] or "{}")
                        existing_custom.update(merged_data["custom_fields"])
                        cursor.execute("UPDATE contacts SET custom_fields_json = ? WHERE id = ?", (json.dumps(existing_custom), primary_id))

                # Delete duplicate records
                dups_to_delete = [d for d in duplicate_ids if d != primary_id]
                if dups_to_delete:
                    placeholders = ",".join("?" for _ in dups_to_delete)
                    cursor.execute(f"DELETE FROM contacts WHERE id IN ({placeholders})", dups_to_delete)

                conn.commit()
                self.log_event("INFO", "Contacts", f"Merged {len(dups_to_delete)} duplicate(s) into primary contact #{primary_id}")
                return True

    # --- Suppression List Operations ---

    def get_suppression_list(self, search: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM suppression_list WHERE 1=1"
            params = []
            if search:
                query += " AND phone LIKE ?"
                params.append(f"%{search}%")
            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def count_suppression(self, search: Optional[str] = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) as count FROM suppression_list WHERE 1=1"
            params = []
            if search:
                query += " AND phone LIKE ?"
                params.append(f"%{search}%")
            cursor.execute(query, params)
            return cursor.fetchone()["count"]

    def add_to_suppression_list(self, phone: str, reason: str, source: str = "manual") -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                try:
                    cursor.execute("""
                        INSERT INTO suppression_list (phone, reason, source, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (phone, reason, source, now))
                    # Also update contact record consent status if present
                    cursor.execute("""
                        UPDATE contacts
                        SET consent_status = 'opted_out', opt_out_timestamp = ?, opt_out_reason = ?
                        WHERE phone = ?
                    """, (now, reason, phone))
                    conn.commit()
                    return True
                except sqlite3.IntegrityError:
                    return False

    def remove_from_suppression_list(self, suppression_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM suppression_list WHERE id = ?", (suppression_id,))
                conn.commit()
                return cursor.rowcount > 0

    def get_suppressed_phones_set(self) -> Set[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT phone FROM suppression_list")
            return {row["phone"] for row in cursor.fetchall()}

    def is_phone_suppressed(self, phone: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM suppression_list WHERE phone = ? LIMIT 1", (phone,))
            return cursor.fetchone() is not None

    # --- Media Assets Operations ---

    def _enrich_media_asset(self, conn, asset_dict: Dict[str, Any]) -> Dict[str, Any]:
        res = dict(asset_dict)
        file_path = res.get("file_path", "")
        res["content_hash"] = res.get("content_hash") or ""
        res["is_available"] = bool(file_path and os.path.isfile(file_path))

        size = res.get("file_size") or 0
        if size < 1024:
            res["file_size_formatted"] = f"{size} B"
        elif size < 1024 * 1024:
            res["file_size_formatted"] = f"{(size / 1024):.1f} KB"
        else:
            res["file_size_formatted"] = f"{(size / (1024 * 1024)):.1f} MB"

        res["original_filename"] = res.get("filename") or res.get("title") or "media_file"
        res["media_type"] = res.get("asset_type") or ("image" if (res.get("mime_type") or "").startswith("image/") else "document")

        cursor = conn.cursor()
        asset_id = res["id"]
        used_by = []

        # 1. Campaigns
        cursor.execute("SELECT name FROM campaigns WHERE media_asset_id = ? OR (attachment_path != '' AND attachment_path = ?)", (asset_id, file_path))
        for r in cursor.fetchall():
            used_by.append(f"Campaign: {r['name']}")

        # 2. Variants
        cursor.execute("SELECT variant_name FROM message_variants WHERE media_asset_id = ?", (asset_id,))
        for r in cursor.fetchall():
            used_by.append(f"Variant: {r['variant_name']}")

        # 3. Queue items
        cursor.execute("SELECT DISTINCT campaign_id FROM campaign_queue_items WHERE (media_asset_id = ? OR (media_path != '' AND media_path = ?)) AND status IN ('PENDING', 'SCHEDULED', 'RUNNING')", (asset_id, file_path))
        for r in cursor.fetchall():
            cname = r['campaign_id'] or "Active Job"
            used_by.append(f"Queue: {cname}")

        res["used_by"] = used_by
        res["usage_count"] = len(used_by)
        return res

    def get_media_assets(self, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM media_assets WHERE 1=1"
            params = []
            if asset_type and asset_type != "All":
                query += " AND asset_type = ?"
                params.append(asset_type)
            query += " ORDER BY id DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._enrich_media_asset(conn, dict(r)) for r in rows]

    def get_media_asset(self, asset_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM media_assets WHERE id = ?", (asset_id,))
            row = cursor.fetchone()
            return self._enrich_media_asset(conn, dict(row)) if row else None

    def get_media_asset_by_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        if not content_hash:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM media_assets WHERE content_hash = ? ORDER BY id ASC LIMIT 1", (content_hash,))
            row = cursor.fetchone()
            return self._enrich_media_asset(conn, dict(row)) if row else None

    def add_media_asset(
        self,
        title: str,
        filename: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        asset_type: str,
        content_hash: str = "",
        approval_status: str = "approved"
    ) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO media_assets (title, filename, file_path, file_size, mime_type, asset_type, content_hash, approval_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (title, filename, file_path, file_size, mime_type, asset_type, content_hash, approval_status, now))
                conn.commit()
                return cursor.lastrowid

    def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_campaigns(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            return [dict(r) for r in cursor.fetchall()]

    def delete_campaign(self, campaign_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
                conn.commit()
                return cursor.rowcount > 0

    def delete_media_asset(self, asset_id: int, force: bool = False) -> Tuple[bool, str]:
        with _lock:
            with self.get_connection() as conn:
                asset = self.get_media_asset(asset_id)
                if not asset:
                    return False, "Media asset not found"

                if asset.get("usage_count", 0) > 0 and not force:
                    refs = ", ".join(asset.get("used_by", []))
                    return False, f"Media asset is currently referenced by {asset['usage_count']} campaign(s) or variant(s): {refs}. Use force=true to delete."

                cursor = conn.cursor()
                file_path = asset.get("file_path", "")
                if file_path and os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                cursor.execute("DELETE FROM media_assets WHERE id = ?", (asset_id,))
                conn.commit()
                return True, "Media asset deleted successfully"

    # --- Campaign Operations ---

    def create_campaign(
        self,
        name: str,
        template_id: Optional[int] = None,
        group_name: str = "Default",
        min_delay: float = 8.0,
        max_delay: float = 15.0,
        batch_size: int = 20,
        batch_pause: float = 60.0,
        daily_cap: int = 100,
        attachment_path: str = "",
        media_asset_id: Optional[int] = None,
        allocation_method: str = "explicit_default",
        allocation_seed: int = 42,
        status: str = "draft"
    ) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO campaigns (
                        name, template_id, group_name, min_delay, max_delay, batch_size,
                        batch_pause, daily_cap, attachment_path, media_asset_id,
                        allocation_method, allocation_seed, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, template_id, group_name, min_delay, max_delay, batch_size,
                    batch_pause, daily_cap, attachment_path, media_asset_id,
                    allocation_method, allocation_seed, status, now
                ))
                conn.commit()
                return cursor.lastrowid

    def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_campaigns(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            return [dict(r) for r in cursor.fetchall()]

    def delete_campaign(self, campaign_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
                conn.commit()
                return cursor.rowcount > 0

    # --- Group Operations ---

    def get_groups(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT g.id, g.name, g.description, g.created_at, COUNT(c.id) as contact_count,
                       SUM(CASE WHEN c.consent_status = 'opted_in' THEN 1 ELSE 0 END) as opted_in_count,
                       SUM(CASE WHEN c.consent_status = 'opted_out' THEN 1 ELSE 0 END) as opted_out_count
                FROM contact_groups g
                LEFT JOIN contacts c ON g.name = c.group_name
                GROUP BY g.id, g.name
                ORDER BY g.name ASC
            """)
            return [dict(r) for r in cursor.fetchall()]

    def add_group(self, name: str, description: str = "") -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO contact_groups (name, description, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET description = excluded.description
                """, (name, description, now))
                conn.commit()
                cursor.execute("SELECT id FROM contact_groups WHERE name = ?", (name,))
                return cursor.fetchone()["id"]

    # --- Template & Purpose-Driven Variant Operations ---

    def get_message_variants(self, template_id: int) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT v.*, m.title as media_title, m.filename as media_filename, m.file_path as media_path, m.asset_type as media_type
                FROM message_variants v
                LEFT JOIN media_assets m ON v.media_asset_id = m.id
                WHERE v.template_id = ?
                ORDER BY v.id ASC
            """, (template_id,))
            return [dict(v) for v in cursor.fetchall()]

    def get_templates(self, search: Optional[str] = None, target_group: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM templates WHERE is_archived = 0"
            params = []
            if search:
                query += " AND (name LIKE ? OR description LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            if target_group and target_group != "All":
                query += " AND target_group = ?"
                params.append(target_group)
            query += " ORDER BY id DESC"
            cursor.execute(query, params)
            templates = []
            for row in cursor.fetchall():
                d = dict(row)
                d["variables"] = json.loads(d.get("variables_json", "[]"))
                tid = d["id"]

                # Text variations
                cursor.execute("""
                    SELECT id, template_id, content, is_active, sort_order, created_at, updated_at
                    FROM template_text_variations
                    WHERE template_id = ?
                    ORDER BY sort_order ASC, id ASC
                """, (tid,))
                texts = [dict(v) for v in cursor.fetchall()]
                d["text_variations"] = texts
                d["text_count"] = len(texts)
                d["active_text_count"] = sum(1 for t in texts if t.get("is_active", 1))

                # Media assets
                cursor.execute("""
                    SELECT tma.id as link_id, tma.is_active, tma.sort_order,
                           m.id, m.title, m.filename, m.file_path, m.file_size, m.mime_type, m.asset_type
                    FROM template_media_assets tma
                    JOIN media_assets m ON tma.media_asset_id = m.id
                    WHERE tma.template_id = ?
                    ORDER BY tma.sort_order ASC, tma.id ASC
                """, (tid,))
                media = [dict(m) for m in cursor.fetchall()]
                d["media_assets"] = media
                d["media_count"] = len(media)
                d["active_media_count"] = sum(1 for m in media if m.get("is_active", 1))

                # Audience count
                grp = d.get("target_group", "All")
                if grp and grp != "All":
                    cursor.execute("SELECT COUNT(*) as cnt FROM contacts WHERE group_name = ? AND consent_status != 'opted_out'", (grp,))
                else:
                    cursor.execute("SELECT COUNT(*) as cnt FROM contacts WHERE consent_status != 'opted_out'")
                d["recipient_count"] = cursor.fetchone()["cnt"]

                # Legacy backward compatibility: attach variants
                cursor.execute("""
                    SELECT v.*, m.title as media_title, m.filename as media_filename, m.asset_type as media_type
                    FROM message_variants v
                    LEFT JOIN media_assets m ON v.media_asset_id = m.id
                    WHERE v.template_id = ?
                    ORDER BY v.id ASC
                """, (tid,))
                d["variants"] = [dict(v) for v in cursor.fetchall()]

                templates.append(d)
            return templates

    def get_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["variables"] = json.loads(d.get("variables_json", "[]"))

            # Text variations
            cursor.execute("""
                SELECT id, template_id, content, is_active, sort_order, created_at, updated_at
                FROM template_text_variations
                WHERE template_id = ?
                ORDER BY sort_order ASC, id ASC
            """, (template_id,))
            texts = [dict(v) for v in cursor.fetchall()]
            d["text_variations"] = texts
            d["text_count"] = len(texts)
            d["active_text_count"] = sum(1 for t in texts if t.get("is_active", 1))

            # Media assets with disk validation
            cursor.execute("""
                SELECT tma.id as link_id, tma.is_active, tma.sort_order,
                       m.id, m.title, m.filename, m.file_path, m.file_size, m.mime_type, m.asset_type
                FROM template_media_assets tma
                JOIN media_assets m ON tma.media_asset_id = m.id
                WHERE tma.template_id = ?
                ORDER BY tma.sort_order ASC, tma.id ASC
            """, (template_id,))
            media = []
            for m_row in cursor.fetchall():
                m_dict = dict(m_row)
                m_dict["exists_on_disk"] = os.path.exists(m_dict.get("file_path", ""))
                media.append(m_dict)
            d["media_assets"] = media
            d["media_count"] = len(media)
            d["active_media_count"] = sum(1 for m in media if m.get("is_active", 1))

            # Contacts summary
            grp = d.get("target_group", "All")
            if grp and grp != "All":
                cursor.execute("SELECT COUNT(*) as cnt FROM contacts WHERE group_name = ?", (grp,))
                tot = cursor.fetchone()["cnt"]
                cursor.execute("SELECT COUNT(*) as cnt FROM contacts WHERE group_name = ? AND consent_status != 'opted_out'", (grp,))
                elig = cursor.fetchone()["cnt"]
            else:
                cursor.execute("SELECT COUNT(*) as cnt FROM contacts")
                tot = cursor.fetchone()["cnt"]
                cursor.execute("SELECT COUNT(*) as cnt FROM contacts WHERE consent_status != 'opted_out'")
                elig = cursor.fetchone()["cnt"]

            cursor.execute("SELECT contact_id FROM template_contacts WHERE template_id = ? AND is_excluded = 1", (template_id,))
            excl_ids = [r["contact_id"] for r in cursor.fetchall()]
            d["excluded_contact_ids"] = excl_ids

            d["contacts_summary"] = {
                "total_selected": tot,
                "eligible": max(0, elig - len(excl_ids)),
                "excluded": (tot - elig) + len(excl_ids)
            }

            # Legacy backward compatibility: attach variants
            cursor.execute("""
                SELECT v.*, m.title as media_title, m.filename as media_filename, m.file_path as media_path, m.asset_type as media_type
                FROM message_variants v
                LEFT JOIN media_assets m ON v.media_asset_id = m.id
                WHERE v.template_id = ?
                ORDER BY v.id ASC
            """, (template_id,))
            d["message_format"] = d.get("message_format") or "image_with_caption"
            d["variants"] = [dict(v) for v in cursor.fetchall()]
            return d

    def add_template(
        self,
        name: str,
        content: str,
        variables: Optional[List[str]] = None,
        description: str = "",
        content_selection_mode: str = "mix_variations",
        target_group: str = "All",
        message_format: str = "image_with_caption"
    ) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                vars_json = json.dumps(variables or [])
                cursor.execute("""
                    INSERT INTO templates (name, content, variables_json, description, content_selection_mode, message_format, target_group, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, content, vars_json, description, content_selection_mode, message_format, target_group, now, now))
                tid = cursor.lastrowid

                # Create initial text variation
                if content and content.strip():
                    cursor.execute("""
                        INSERT INTO template_text_variations (template_id, content, is_active, sort_order, created_at, updated_at)
                        VALUES (?, ?, 1, 0, ?, ?)
                    """, (tid, content, now, now))

                # Automatically create default variant for legacy compatibility
                cursor.execute("""
                    INSERT INTO message_variants (template_id, variant_name, purpose, audience_filter_field, audience_filter_value, content, approval_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (tid, "Primary Variant", "Standard default communication", "all", "", content, "approved", now, now))
                conn.commit()
                return tid

    def update_template(
        self,
        template_id: int,
        name: Optional[str] = None,
        content: Optional[str] = None,
        variables: Optional[List[str]] = None,
        description: Optional[str] = None,
        content_selection_mode: Optional[str] = None,
        message_format: Optional[str] = None,
        target_group: Optional[str] = None,
        pacing_delay_min: Optional[int] = None,
        pacing_delay_max: Optional[int] = None
    ) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                fields = ["updated_at = ?"]
                params = [now]
                if name is not None:
                    fields.append("name = ?")
                    params.append(name)
                if content is not None:
                    fields.append("content = ?")
                    params.append(content)
                if variables is not None:
                    fields.append("variables_json = ?")
                    params.append(json.dumps(variables))
                if description is not None:
                    fields.append("description = ?")
                    params.append(description)
                if content_selection_mode is not None:
                    fields.append("content_selection_mode = ?")
                    params.append(content_selection_mode)
                if message_format is not None:
                    fields.append("message_format = ?")
                    params.append(message_format)
                if target_group is not None:
                    fields.append("target_group = ?")
                    params.append(target_group)
                if pacing_delay_min is not None:
                    fields.append("pacing_delay_min = ?")
                    params.append(pacing_delay_min)
                if pacing_delay_max is not None:
                    fields.append("pacing_delay_max = ?")
                    params.append(pacing_delay_max)

                params.append(template_id)
                query = f"UPDATE templates SET {', '.join(fields)} WHERE id = ?"
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0

    def delete_template(self, template_id: int) -> bool:
        """
        Permanently deletes a template.
        Safely unlinks associated campaigns and legacy collections so historical records are preserved.
        """
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # 1. Preserve historical campaign dispatch records by unlinking foreign key
                cursor.execute("UPDATE campaigns SET template_id = NULL WHERE template_id = ?", (template_id,))
                cursor.execute("UPDATE collection_items SET template_id = NULL WHERE template_id = ?", (template_id,))
                cursor.execute("UPDATE content_set_items SET template_id = NULL WHERE template_id = ?", (template_id,))

                # 2. Delete child template associations
                cursor.execute("DELETE FROM template_media_assets WHERE template_id = ?", (template_id,))
                cursor.execute("DELETE FROM template_text_variations WHERE template_id = ?", (template_id,))
                cursor.execute("DELETE FROM template_contacts WHERE template_id = ?", (template_id,))
                cursor.execute("DELETE FROM message_variants WHERE template_id = ?", (template_id,))

                # 3. Delete the template itself
                cursor.execute("DELETE FROM templates WHERE id = ?", (template_id,))
                conn.commit()
                return cursor.rowcount > 0

    def duplicate_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Clones a template with all its media assets and text variations."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                orig = dict(row)
                now = datetime.now().isoformat()
                new_name = f"{orig['name']} (Copy)"

                cursor.execute("SELECT id FROM templates WHERE name = ?", (new_name,))
                if cursor.fetchone():
                    new_name = f"{orig['name']} (Copy {int(time.time()) % 10000})"

                cursor.execute("""
                    INSERT INTO templates (name, content, variables_json, description, content_selection_mode, message_format, target_group, pacing_delay_min, pacing_delay_max, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    new_name,
                    orig.get("content", ""),
                    orig.get("variables_json", "[]"),
                    orig.get("description", ""),
                    orig.get("content_selection_mode", "mix_variations"),
                    orig.get("message_format", "image_with_caption"),
                    orig.get("target_group", "All"),
                    orig.get("pacing_delay_min", 8),
                    orig.get("pacing_delay_max", 16),
                    now, now
                ))
                new_tid = cursor.lastrowid

                # Copy text variations
                cursor.execute("""
                    SELECT content, is_active, sort_order
                    FROM template_text_variations
                    WHERE template_id = ?
                    ORDER BY sort_order ASC
                """, (template_id,))
                for tv in cursor.fetchall():
                    cursor.execute("""
                        INSERT INTO template_text_variations (template_id, content, is_active, sort_order, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (new_tid, tv["content"], tv["is_active"], tv["sort_order"], now, now))

                # Copy media assets
                cursor.execute("""
                    SELECT media_asset_id, is_active, sort_order
                    FROM template_media_assets
                    WHERE template_id = ?
                    ORDER BY sort_order ASC
                """, (template_id,))
                for ma in cursor.fetchall():
                    cursor.execute("""
                        INSERT INTO template_media_assets (template_id, media_asset_id, is_active, sort_order, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (new_tid, ma["media_asset_id"], ma["is_active"], ma["sort_order"], now))

                conn.commit()
                return self.get_template(new_tid)

    def save_complete_template(self, template_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Atomically saves full template configuration from the editor toolbar:
        name, description, mode, message_format, target_group, pacing delays,
        text variations (contents and active flags), media assets (active flags), and excluded contacts.
        """
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                # 1. Update templates base row
                name = data.get("name")
                desc = data.get("description", "")
                mode = data.get("content_selection_mode", "mix_variations")
                msg_format = data.get("message_format", "image_with_caption")
                grp = data.get("target_group", "All")
                p_min = data.get("pacing_delay_min", 8)
                p_max = data.get("pacing_delay_max", 16)

                cursor.execute("""
                    UPDATE templates
                    SET name = COALESCE(?, name),
                        description = ?,
                        content_selection_mode = ?,
                        message_format = ?,
                        target_group = ?,
                        pacing_delay_min = ?,
                        pacing_delay_max = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (name, desc, mode, msg_format, grp, p_min, p_max, now, template_id))

                # 2. Text variations: if supplied in data, synchronize them
                if "text_variations" in data and isinstance(data["text_variations"], list):
                    incoming_texts = data["text_variations"]
                    cursor.execute("SELECT id FROM template_text_variations WHERE template_id = ?", (template_id,))
                    existing_text_ids = {r["id"] for r in cursor.fetchall()}
                    retained_text_ids = set()

                    first_text_content = ""
                    for idx, tv in enumerate(incoming_texts):
                        tv_content = tv.get("content", "") if isinstance(tv, dict) else str(tv)
                        tv_active = 1 if (isinstance(tv, dict) and tv.get("is_active", True)) else 1
                        tv_id = tv.get("id") if isinstance(tv, dict) else None

                        if not first_text_content and tv_content.strip():
                            first_text_content = tv_content

                        if tv_id and tv_id in existing_text_ids:
                            cursor.execute("""
                                UPDATE template_text_variations
                                SET content = ?, is_active = ?, sort_order = ?, updated_at = ?
                                WHERE id = ? AND template_id = ?
                            """, (tv_content, tv_active, idx, now, tv_id, template_id))
                            retained_text_ids.add(tv_id)
                        elif tv_content.strip():
                            cursor.execute("""
                                INSERT INTO template_text_variations (template_id, content, is_active, sort_order, created_at, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (template_id, tv_content, tv_active, idx, now, now))
                            retained_text_ids.add(cursor.lastrowid)

                    to_delete = existing_text_ids - retained_text_ids
                    if to_delete:
                        cursor.execute(f"DELETE FROM template_text_variations WHERE template_id = ? AND id IN ({','.join(['?']*len(to_delete))})", [template_id, *to_delete])

                    if first_text_content:
                        cursor.execute("UPDATE templates SET content = ? WHERE id = ?", (first_text_content, template_id))

                # 3. Media assets: if supplied, synchronize active status & links
                if "media_assets" in data and isinstance(data["media_assets"], list):
                    for idx, ma in enumerate(data["media_assets"]):
                        if isinstance(ma, dict) and "id" in ma:
                            mid = ma["id"]
                            is_act = 1 if ma.get("is_active", True) else 0
                            cursor.execute("SELECT id FROM template_media_assets WHERE template_id = ? AND media_asset_id = ?", (template_id, mid))
                            existing_link = cursor.fetchone()
                            if existing_link:
                                cursor.execute("""
                                    UPDATE template_media_assets
                                    SET is_active = ?, sort_order = ?
                                    WHERE id = ?
                                """, (is_act, idx, existing_link["id"]))
                            else:
                                cursor.execute("""
                                    INSERT INTO template_media_assets (template_id, media_asset_id, is_active, sort_order, created_at)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (template_id, mid, is_act, idx, now))

                # 4. Excluded contacts: if supplied, synchronize template_contacts
                if "excluded_contact_ids" in data and isinstance(data["excluded_contact_ids"], list):
                    cursor.execute("DELETE FROM template_contacts WHERE template_id = ?", (template_id,))
                    for cid in data["excluded_contact_ids"]:
                        cursor.execute("""
                            INSERT INTO template_contacts (template_id, contact_id, is_excluded, created_at)
                            VALUES (?, ?, 1, ?)
                        """, (template_id, cid, now))

                conn.commit()
                return self.get_template(template_id)

    def rename_media_asset(self, asset_id: int, new_title: str) -> bool:
        """Renames a media asset's display title."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE media_assets SET title = ? WHERE id = ?", (new_title.strip(), asset_id))
                conn.commit()
                return cursor.rowcount > 0

    def add_template_text_variation(self, template_id: int, content: str) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("SELECT MAX(sort_order) as m FROM template_text_variations WHERE template_id = ?", (template_id,))
                row = cursor.fetchone()
                order = (row["m"] or 0) + 1 if row else 0
                cursor.execute("""
                    INSERT INTO template_text_variations (template_id, content, is_active, sort_order, created_at, updated_at)
                    VALUES (?, ?, 1, ?, ?, ?)
                """, (template_id, content, order, now, now))
                vid = cursor.lastrowid
                conn.commit()
                return vid

    def update_template_text_variation(self, variant_id: int, content: Optional[str] = None, is_active: Optional[int] = None) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                fields = ["updated_at = ?"]
                params = [now]
                if content is not None:
                    fields.append("content = ?")
                    params.append(content)
                if is_active is not None:
                    fields.append("is_active = ?")
                    params.append(1 if is_active else 0)
                params.append(variant_id)
                cursor.execute(f"UPDATE template_text_variations SET {', '.join(fields)} WHERE id = ?", params)
                conn.commit()
                return cursor.rowcount > 0

    def delete_template_text_variation(self, variant_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM template_text_variations WHERE id = ?", (variant_id,))
                conn.commit()
                return cursor.rowcount > 0

    def add_template_media_assets(self, template_id: int, media_asset_ids: List[int]) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                added = 0
                for mid in media_asset_ids:
                    cursor.execute("SELECT id FROM template_media_assets WHERE template_id = ? AND media_asset_id = ?", (template_id, mid))
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO template_media_assets (template_id, media_asset_id, is_active, sort_order, created_at)
                            VALUES (?, ?, 1, 0, ?)
                        """, (template_id, mid, now))
                        added += 1
                conn.commit()
                return added

    def remove_template_media_asset(self, template_id: int, media_asset_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM template_media_assets WHERE template_id = ? AND media_asset_id = ?", (template_id, media_asset_id))
                conn.commit()
                return cursor.rowcount > 0

    def toggle_template_media_asset(self, template_id: int, media_asset_id: int, is_active: bool) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE template_media_assets
                    SET is_active = ?
                    WHERE template_id = ? AND media_asset_id = ?
                """, (1 if is_active else 0, template_id, media_asset_id))
                conn.commit()
                return cursor.rowcount > 0

    def compute_template_assignments(self, template_id: int, preview_limit: int = 50) -> Dict[str, Any]:
        """
        Computes 1 media asset + 1 text variation per eligible contact.
        - Mode 1: same_for_everyone -> user picks 1 media + 1 text for all.
        - Mode 2: mix_variations -> reproducible seeded random assignment per contact.
        """
        import random
        tpl = self.get_template(template_id)
        if not tpl:
            raise ValueError(f"Template {template_id} not found.")

        grp = tpl.get("target_group", "All")
        contacts = self.get_contacts(group_name=grp if grp != "All" else None, limit=5000)

        excluded_ids = set(tpl.get("excluded_contact_ids", []))
        eligible_contacts = []
        excluded_contacts = []
        for c in contacts:
            if c.get("consent_status") == "opted_out" or c["id"] in excluded_ids:
                excluded_contacts.append(c)
            else:
                eligible_contacts.append(c)

        active_texts = [t for t in tpl.get("text_variations", []) if t.get("is_active", 1)]
        active_media = [m for m in tpl.get("media_assets", []) if m.get("is_active", 1)]

        mode = tpl.get("content_selection_mode", "mix_variations")
        rng = random.Random(template_id + 42)

        assignments = []
        for c in eligible_contacts:
            contact_name = c.get("name", "Friend")
            first_name = contact_name.split()[0] if contact_name else "Friend"
            phone = c.get("phone", "")

            # Resolve text
            if not active_texts:
                resolved_text = tpl.get("content", "")
                text_id = None
            elif mode == "same_for_everyone":
                text_obj = active_texts[0]
                resolved_text = text_obj["content"]
                text_id = text_obj["id"]
            else:
                text_obj = rng.choice(active_texts)
                resolved_text = text_obj["content"]
                text_id = text_obj["id"]

            rendered = (resolved_text
                        .replace("{name}", contact_name)
                        .replace("{first_name}", first_name)
                        .replace("{phone}", phone))

            # Resolve media
            if not active_media:
                media_id = None
                media_title = "None (Text Only)"
                media_file = ""
            elif mode == "same_for_everyone":
                media_obj = active_media[0]
                media_id = media_obj["id"]
                media_title = media_obj.get("title") or media_obj.get("filename", "")
                media_file = media_obj.get("filename", "")
            else:
                media_obj = rng.choice(active_media)
                media_id = media_obj["id"]
                media_title = media_obj.get("title") or media_obj.get("filename", "")
                media_file = media_obj.get("filename", "")

            assignments.append({
                "contact_id": c["id"],
                "contact_name": contact_name,
                "phone": phone,
                "text_id": text_id,
                "rendered_text": rendered,
                "media_asset_id": media_id,
                "media_title": media_title,
                "media_file": media_file
            })

        return {
            "template_id": template_id,
            "template_name": tpl.get("name", ""),
            "mode": mode,
            "total_selected": len(contacts),
            "eligible_count": len(eligible_contacts),
            "excluded_count": len(excluded_contacts),
            "active_media_count": len(active_media),
            "active_text_count": len(active_texts),
            "preview_assignments": assignments[:preview_limit],
            "all_assignments": assignments
        }

    def bulk_delete_media_assets(self, asset_ids: List[int]) -> Dict[str, Any]:
        """Bulk deletes media assets from SQLite and removes physical files from uploads/media."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                deleted_count = 0
                for aid in asset_ids:
                    cursor.execute("SELECT file_path FROM media_assets WHERE id = ?", (aid,))
                    row = cursor.fetchone()
                    if row and row["file_path"] and os.path.exists(row["file_path"]):
                        try:
                            os.remove(row["file_path"])
                        except Exception:
                            pass
                    cursor.execute("DELETE FROM template_media_assets WHERE media_asset_id = ?", (aid,))
                    cursor.execute("DELETE FROM content_set_items WHERE media_asset_id = ?", (aid,))
                    cursor.execute("DELETE FROM collection_items WHERE media_asset_id = ?", (aid,))
                    cursor.execute("UPDATE message_variants SET media_asset_id = NULL WHERE media_asset_id = ?", (aid,))
                    cursor.execute("UPDATE campaigns SET media_asset_id = NULL WHERE media_asset_id = ?", (aid,))
                    cursor.execute("DELETE FROM media_assets WHERE id = ?", (aid,))
                    deleted_count += cursor.rowcount
                conn.commit()
                return {"success": True, "deleted_count": deleted_count}

    def add_message_variant(
        self,
        template_id: int,
        variant_name: str,
        purpose: str,
        audience_filter_field: str,
        audience_filter_value: str,
        content: str,
        media_asset_id: Optional[int] = None,
        approval_status: str = "approved"
    ) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO message_variants (template_id, variant_name, purpose, audience_filter_field, audience_filter_value, content, media_asset_id, approval_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (template_id, variant_name, purpose, audience_filter_field, audience_filter_value, content, media_asset_id, approval_status, now, now))
                conn.commit()
                return cursor.lastrowid

    def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_campaigns(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            return [dict(r) for r in cursor.fetchall()]

    def delete_campaign(self, campaign_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
                conn.commit()
                return cursor.rowcount > 0

    def update_message_variant(
        self,
        variant_id: int,
        variant_name: str,
        purpose: str,
        audience_filter_field: str,
        audience_filter_value: str,
        content: str,
        media_asset_id: Optional[int] = None,
        approval_status: str = "approved"
    ) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    UPDATE message_variants
                    SET variant_name = ?, purpose = ?, audience_filter_field = ?, audience_filter_value = ?,
                        content = ?, media_asset_id = ?, approval_status = ?, updated_at = ?
                    WHERE id = ?
                """, (variant_name, purpose, audience_filter_field, audience_filter_value, content, media_asset_id, approval_status, now, variant_id))
                conn.commit()
                return cursor.rowcount > 0

    def delete_message_variant(self, variant_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM message_variants WHERE id = ?", (variant_id,))
                conn.commit()
                return cursor.rowcount > 0

    def get_message_variant(self, variant_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT v.*, m.title as media_title, m.filename as media_filename, m.file_path as media_path, m.asset_type as media_type
                FROM message_variants v
                LEFT JOIN media_assets m ON v.media_asset_id = m.id
                WHERE v.id = ?
            """, (variant_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # --- Job & Queue Operations ---

    def create_job(self, job_id: str, campaign_name: str, total_count: int, suppressed_count: int = 0, scheduled_at: Optional[str] = None) -> Dict[str, Any]:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                initial_status = "SCHEDULED" if scheduled_at else "QUEUED"
                cursor.execute("""
                    INSERT INTO jobs (id, campaign_name, status, total_count, sent_count, failed_count, suppressed_count, started_at, scheduled_at)
                    VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?)
                """, (job_id, campaign_name, initial_status, total_count, suppressed_count, now, scheduled_at))
                conn.commit()
                return {
                    "id": job_id,
                    "campaign_name": campaign_name,
                    "status": initial_status,
                    "total_count": total_count,
                    "sent_count": 0,
                    "failed_count": 0,
                    "suppressed_count": suppressed_count,
                    "started_at": now,
                    "scheduled_at": scheduled_at
                }

    def update_job_status(self, job_id: str, status: str, error_message: str = ""):
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                completed_at = now if status in ("COMPLETED", "FAILED", "CANCELLED") else None
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, completed_at = COALESCE(?, completed_at), error_message = ?, updated_at = ?
                    WHERE id = ?
                """, (status, completed_at, error_message, now, job_id))
                conn.commit()

    def update_job_progress(self, job_id: str, sent_count: int, failed_count: int, current_recipient: str = "", suppressed_count: Optional[int] = None):
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                if suppressed_count is not None:
                    cursor.execute("""
                        UPDATE jobs
                        SET sent_count = ?, failed_count = ?, current_recipient = ?, suppressed_count = ?, updated_at = ?
                        WHERE id = ?
                    """, (sent_count, failed_count, current_recipient, suppressed_count, now, job_id))
                else:
                    cursor.execute("""
                        UPDATE jobs
                        SET sent_count = ?, failed_count = ?, current_recipient = ?, updated_at = ?
                        WHERE id = ?
                    """, (sent_count, failed_count, current_recipient, now, job_id))
                conn.commit()

    def record_job_result(
        self,
        job_id: str,
        name: str,
        phone: str,
        status: str,
        error: str = "",
        attachment: str = "",
        media_status: str = "",
        text_status: str = "",
        overall_status: str = "",
        last_successful_stage: str = "",
        recovery_eligibility: str = ""
    ):
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO job_results (
                        job_id, name, phone, status, error, attachment, timestamp,
                        media_status, text_status, overall_status, last_successful_stage, recovery_eligibility
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id, name, phone, status, error, attachment, now,
                    media_status, text_status, overall_status or status, last_successful_stage, recovery_eligibility
                ))
                conn.commit()

    def create_queue_items(self, job_id: str, campaign_id: Optional[int], items: List[Dict[str, Any]]) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                inserted = 0
                for item in items:
                    med_p = item.get("media_path", "")
                    has_media = bool(med_p and str(med_p).strip())
                    msg_txt = item.get("resolved_message", "")
                    has_text = bool(msg_txt and str(msg_txt).strip())

                    med_init = item.get("media_status") or ("PENDING" if has_media else "SKIPPED")
                    txt_init = item.get("text_status") or ("PENDING" if has_text else "SKIPPED")
                    ov_init = item.get("overall_status") or item.get("status", "PENDING")
                    last_st = item.get("last_successful_stage", "none")
                    rec_el = item.get("recovery_eligibility", "retry_all")

                    cursor.execute("""
                        INSERT OR IGNORE INTO campaign_queue_items (
                            campaign_id, job_id, idempotency_key, recipient_name, recipient_phone,
                            variant_id, variant_purpose, resolved_message, media_path, media_asset_id,
                            allocation_rule, status, retry_count, max_retries, error_message, message_format,
                            media_status, text_status, overall_status, last_successful_stage, recovery_eligibility,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        campaign_id,
                        job_id,
                        item["idempotency_key"],
                        item["recipient_name"],
                        item["recipient_phone"],
                        item.get("variant_id"),
                        item.get("variant_purpose", ""),
                        item["resolved_message"],
                        med_p,
                        item.get("media_asset_id"),
                        item.get("allocation_rule", ""),
                        item.get("status", "PENDING"),
                        item.get("retry_count", 0),
                        item.get("max_retries", 3),
                        item.get("error_message", ""),
                        item.get("message_format", "image_with_caption"),
                        med_init,
                        txt_init,
                        ov_init,
                        last_st,
                        rec_el,
                        now
                    ))
                    if cursor.rowcount > 0:
                        inserted += 1
                conn.commit()
                return inserted

    def bulk_enqueue_items(self, campaign_id: Any, job_id: str, items: List[Dict[str, Any]]) -> int:
        cid = None if isinstance(campaign_id, str) else campaign_id
        return self.create_queue_items(job_id=job_id, campaign_id=cid, items=items)

    def get_recipient_activity_items(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieves recipient-level history records with media thumbnail info,
        exact rendered text, honest delivery semantics, and timestamps.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT q.*,
                       m.title as media_title, m.filename as media_filename, m.mime_type as media_mime_type, m.file_size as media_file_size,
                       j.campaign_name as job_campaign_name, j.started_at as job_started_at
                FROM campaign_queue_items q
                LEFT JOIN media_assets m ON q.media_asset_id = m.id
                LEFT JOIN jobs j ON q.job_id = j.id
                WHERE 1=1
            """
            params = []
            if job_id:
                query += " AND q.job_id = ?"
                params.append(job_id)
            if status and status.upper() != "ALL":
                st_up = status.upper()
                if st_up == "SENT":
                    query += " AND q.status IN ('SENT', 'DISPATCHED')"
                elif st_up == "FAILED":
                    query += " AND q.status IN ('FAILED', 'FAILED_PERMANENT', 'FAILED_MAX_RETRIES')"
                elif st_up == "UNCERTAIN":
                    query += " AND q.status = 'UNCERTAIN'"
                elif st_up == "PENDING":
                    query += " AND q.status IN ('PENDING', 'RETRYING', 'SCHEDULED')"
                else:
                    query += " AND q.status = ?"
                    params.append(status)
            if search:
                query += " AND (q.recipient_name LIKE ? OR q.recipient_phone LIKE ? OR q.resolved_message LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
            query += " ORDER BY q.id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            items = []
            for r in rows:
                d = dict(r)
                st = (d.get("status") or "PENDING").upper()
                ov_st = (d.get("overall_status") or st).upper()
                med_st = (d.get("media_status") or "").upper()
                txt_st = (d.get("text_status") or "").upper()

                if st in ("DISPATCHED", "SENT") or ov_st == "SENT":
                    d["display_status"] = "SENT"
                    d["delivery_label"] = "Sent (Delivered)"
                    d["delivery_explanation"] = "Message and media successfully submitted to WhatsApp Web and outgoing chat opened."
                    d["read_label"] = "Read not confirmed"
                    d["read_explanation"] = "WhatsApp Web does not broadcast read receipts for external broadcast messages without webhooks."
                    d["recovery_action"] = "none"
                elif st in ("PARTIAL", "PARTIALLY_SENT") or ov_st in ("PARTIAL", "PARTIALLY_SENT") or (med_st == "SENT" and (txt_st in ("FAILED", "FAILED_MAX_RETRIES", "FAILED_PERMANENT") or d.get("last_successful_stage") == "media" or d.get("recovery_eligibility") == "retry_text_only")):
                    d["display_status"] = "PARTIALLY_SENT" if st != "PENDING" else "PENDING"
                    d["delivery_label"] = "Partially Sent (Image Sent, Text Failed)" if st != "PENDING" else "Pending (Retrying Text Only)"
                    d["delivery_explanation"] = d.get("error_message") or "Image was delivered to recipient, but follow-up text failed."
                    d["read_label"] = "Partially Delivered"
                    d["read_explanation"] = "Media was successfully sent; text component failed."
                    d["recovery_action"] = "retry_text_only"
                    d["recovery_action_label"] = "Retry Text Only"
                elif st == "UNCERTAIN" or ov_st == "UNCERTAIN":
                    d["display_status"] = "UNCERTAIN"
                    d["delivery_label"] = "Uncertain Delivery"
                    d["delivery_explanation"] = "Browser timeout or network hiccup during send. Relay prevented duplicate re-send. Verify manually in WhatsApp."
                    d["read_label"] = "Unconfirmed"
                    d["read_explanation"] = "Message transmission outcome could not be verified by browser DOM."
                    d["recovery_action"] = "reconcile_manual"
                    d["recovery_action_label"] = "Reconcile / Check WhatsApp"
                elif "FAIL" in st:
                    d["display_status"] = "FAILED"
                    d["delivery_label"] = "Failed"
                    d["delivery_explanation"] = d.get("error_message") or "Message delivery encountered an error."
                    d["read_label"] = "Not delivered"
                    d["read_explanation"] = "Message was not sent."
                    d["recovery_action"] = "retry_all"
                    d["recovery_action_label"] = "Retry Recipient"
                elif st == "SUPPRESSED":
                    d["display_status"] = "SUPPRESSED"
                    d["delivery_label"] = "Suppressed"
                    d["delivery_explanation"] = "Contact is on suppression or opt-out list."
                    d["read_label"] = "Not sent"
                    d["read_explanation"] = "Safety suppression."
                    d["recovery_action"] = "none"
                else:
                    rec_act = d.get("recovery_eligibility") or "none"
                    d["display_status"] = "PENDING"
                    d["delivery_label"] = "Pending in Queue"
                    d["delivery_explanation"] = "Waiting for dispatch worker turn."
                    d["read_label"] = "Pending"
                    d["read_explanation"] = "Not sent yet."
                    d["recovery_action"] = rec_act
                    d["recovery_action_label"] = "Retry Text Only" if rec_act == "retry_text_only" else ("Retry Recipient" if rec_act == "retry_all" else "none")

                if d.get("media_filename"):
                    d["media_thumbnail_url"] = f"/api/media/file/{d['media_filename']}"
                else:
                    d["media_thumbnail_url"] = None

                # Convenience aliases for frontend and consumers
                d["contact_name"] = d.get("recipient_name") or "Recipient"
                d["phone"] = d.get("recipient_phone") or ""
                d["message"] = d.get("resolved_message") or ""
                d["raw_status"] = st
                d["status"] = d["display_status"]
                d["campaign_name"] = d.get("job_campaign_name") or ""

                items.append(d)
            return items

    def get_recipient_activity_detail(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves full detail for a single recipient queue item including contact metadata and audit trace."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT q.*,
                       m.title as media_title, m.filename as media_filename, m.mime_type as media_mime_type, m.file_size as media_file_size,
                       j.campaign_name as job_campaign_name, j.started_at as job_started_at,
                       c.group_name as contact_group, c.consent_status as contact_consent
                FROM campaign_queue_items q
                LEFT JOIN media_assets m ON q.media_asset_id = m.id
                LEFT JOIN jobs j ON q.job_id = j.id
                LEFT JOIN contacts c ON q.recipient_phone = c.phone
                WHERE q.id = ?
            """, (item_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            st = (d.get("status") or "PENDING").upper()
            ov_st = (d.get("overall_status") or st).upper()
            med_st = (d.get("media_status") or "").upper()
            txt_st = (d.get("text_status") or "").upper()

            if st in ("DISPATCHED", "SENT") or ov_st == "SENT":
                d["display_status"] = "SENT"
                d["delivery_label"] = "Sent (Delivered)"
                d["delivery_explanation"] = "Message successfully submitted to WhatsApp Web."
                d["read_label"] = "Read not confirmed"
                d["read_explanation"] = "WhatsApp Web does not broadcast read receipts for external broadcast messages."
                d["recovery_action"] = "none"
            elif st in ("PARTIAL", "PARTIALLY_SENT") or ov_st in ("PARTIAL", "PARTIALLY_SENT") or (med_st == "SENT" and (txt_st in ("FAILED", "FAILED_MAX_RETRIES", "FAILED_PERMANENT") or d.get("last_successful_stage") == "media" or d.get("recovery_eligibility") == "retry_text_only")):
                d["display_status"] = "PARTIALLY_SENT" if st != "PENDING" else "PENDING"
                d["delivery_label"] = "Partially Sent (Image Sent, Text Failed)" if st != "PENDING" else "Pending (Retrying Text Only)"
                d["delivery_explanation"] = d.get("error_message") or "Image was delivered to recipient, but follow-up text failed."
                d["read_label"] = "Partially Delivered"
                d["read_explanation"] = "Media was successfully sent; text component failed."
                d["recovery_action"] = "retry_text_only"
                d["recovery_action_label"] = "Retry Text Only"
            elif st == "UNCERTAIN" or ov_st == "UNCERTAIN":
                d["display_status"] = "UNCERTAIN"
                d["delivery_label"] = "Uncertain Delivery"
                d["delivery_explanation"] = "Browser timeout or network hiccup during send. Relay prevented duplicate re-send."
                d["read_label"] = "Unconfirmed"
                d["read_explanation"] = "Transmission outcome unconfirmed by DOM."
                d["recovery_action"] = "reconcile_manual"
                d["recovery_action_label"] = "Reconcile / Check WhatsApp"
            elif "FAIL" in st:
                d["display_status"] = "FAILED"
                d["delivery_label"] = "Failed"
                d["delivery_explanation"] = d.get("error_message") or "Message delivery encountered an error."
                d["read_label"] = "Not delivered"
                d["read_explanation"] = "Message was not sent."
                d["recovery_action"] = "retry_all"
                d["recovery_action_label"] = "Retry Recipient"
            else:
                rec_act = d.get("recovery_eligibility") or "none"
                d["display_status"] = "PENDING"
                d["delivery_label"] = "Pending in Queue"
                d["delivery_explanation"] = "Waiting for dispatch worker turn."
                d["read_label"] = "Pending"
                d["read_explanation"] = "Not sent yet."
                d["recovery_action"] = rec_act
                d["recovery_action_label"] = "Retry Text Only" if rec_act == "retry_text_only" else ("Retry Recipient" if rec_act == "retry_all" else "none")

            if d.get("media_filename"):
                d["media_thumbnail_url"] = f"/api/media/file/{d['media_filename']}"
            else:
                d["media_thumbnail_url"] = None

            # Convenience aliases
            d["contact_name"] = d.get("recipient_name") or "Recipient"
            d["phone"] = d.get("recipient_phone") or ""
            d["message"] = d.get("resolved_message") or ""
            d["raw_status"] = st
            d["status"] = d["display_status"]
            d["campaign_name"] = d.get("job_campaign_name") or ""
            d["group_name"] = d.get("contact_group") or "General"

            return d

    def reset_queue_item_for_retry(self, item_id: int, mode: str = "auto") -> Optional[Dict[str, Any]]:
        """
        Resets a single queue item to PENDING for individual recipient retry.
        If mode is 'text_only' or if media was already confirmed SENT:
        Leaves media_status='SENT', last_successful_stage='media', and resets text_status to 'PENDING'.
        """
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM campaign_queue_items WHERE id = ?", (item_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                item = dict(row)
                med_st = (item.get("media_status") or "").upper()
                last_stage = item.get("last_successful_stage") or ""

                if mode == "text_only" or (med_st == "SENT" and last_stage in ("media", "partial")):
                    cursor.execute("""
                        UPDATE campaign_queue_items
                        SET status = 'PENDING',
                            overall_status = 'PENDING',
                            text_status = 'PENDING',
                            media_status = 'SENT',
                            last_successful_stage = 'media',
                            recovery_eligibility = 'retry_text_only',
                            error_message = '',
                            stage_retry_count = COALESCE(stage_retry_count, 0) + 1
                        WHERE id = ?
                    """, (item_id,))
                else:
                    cursor.execute("""
                        UPDATE campaign_queue_items
                        SET status = 'PENDING',
                            overall_status = 'PENDING',
                            media_status = CASE WHEN media_path != '' THEN 'PENDING' ELSE 'SKIPPED' END,
                            text_status = CASE WHEN resolved_message != '' THEN 'PENDING' ELSE 'SKIPPED' END,
                            last_successful_stage = 'none',
                            recovery_eligibility = 'retry_all',
                            error_message = '',
                            retry_count = 0,
                            stage_retry_count = 0
                        WHERE id = ?
                    """, (item_id,))
                conn.commit()
                return self.get_recipient_activity_detail(item_id)

    def get_queue_items(self, job_id: str, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM campaign_queue_items WHERE job_id = ?"
            params = [job_id]
            if status and status != "ALL":
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY id ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def update_queue_item_status(
        self,
        item_id: int,
        status: str,
        error_message: str = "",
        dispatched_at: Optional[str] = None,
        retry_count: Optional[int] = None,
        media_status: Optional[str] = None,
        text_status: Optional[str] = None,
        overall_status: Optional[str] = None,
        last_successful_stage: Optional[str] = None,
        recovery_eligibility: Optional[str] = None,
        stage_retry_count: Optional[int] = None
    ):
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                disp_time = dispatched_at or (now if status in ("DISPATCHED", "SENT") else None)

                updates = ["status = ?", "error_message = ?", "dispatched_at = COALESCE(?, dispatched_at)"]
                params = [status, error_message, disp_time]

                if retry_count is not None:
                    updates.append("retry_count = ?")
                    params.append(retry_count)
                if media_status is not None:
                    updates.append("media_status = ?")
                    params.append(media_status)
                if text_status is not None:
                    updates.append("text_status = ?")
                    params.append(text_status)
                if overall_status is not None:
                    updates.append("overall_status = ?")
                    params.append(overall_status)
                else:
                    updates.append("overall_status = ?")
                    params.append(status)
                if last_successful_stage is not None:
                    updates.append("last_successful_stage = ?")
                    params.append(last_successful_stage)
                if recovery_eligibility is not None:
                    updates.append("recovery_eligibility = ?")
                    params.append(recovery_eligibility)
                if stage_retry_count is not None:
                    updates.append("stage_retry_count = ?")
                    params.append(stage_retry_count)

                params.append(item_id)
                sql = f"UPDATE campaign_queue_items SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(sql, params)
                conn.commit()

    def get_queue_stats(self, job_id: str) -> Dict[str, int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM campaign_queue_items
                WHERE job_id = ?
                GROUP BY status
            """, (job_id,))
            stats = {row["status"]: row["count"] for row in cursor.fetchall()}
            return {
                "total": sum(stats.values()),
                "pending": stats.get("PENDING", 0),
                "dispatched": stats.get("DISPATCHED", 0),
                "suppressed": stats.get("SUPPRESSED", 0),
                "retrying": stats.get("RETRYING", 0),
                "failed_permanent": stats.get("FAILED_PERMANENT", 0)
            }

    def get_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            job = dict(row)
            cursor.execute("SELECT * FROM job_results WHERE job_id = ? ORDER BY id ASC", (job_id,))
            job["results"] = [dict(r) for r in cursor.fetchall()]
            job["queue_stats"] = self.get_queue_stats(job_id)
            return job

    # --- Audit Log Operations ---

    def log_event(self, level: str, module: str, message: str):
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO audit_logs (timestamp, level, module, message)
                    VALUES (?, ?, ?, ?)
                """, (now, level.upper(), module, message))
                conn.commit()

    def get_audit_logs(self, level: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM audit_logs WHERE 1=1"
            params = []
            if level and level != "ALL":
                query += " AND level = ?"
                params.append(level.upper())
            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def create_collection(
        self,
        name: str,
        description: str = "",
        pairing_mode: str = "fixed_pair",
        message_ids: Optional[List[int]] = None,
        media_ids: Optional[List[int]] = None,
        pairs: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO content_collections (name, description, pairing_mode, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, description, pairing_mode, now, now))
                col_id = cursor.lastrowid

                # Items
                if message_ids:
                    for mid in message_ids:
                        cursor.execute("INSERT INTO collection_items (collection_id, item_type, template_id) VALUES (?, 'message', ?)", (col_id, mid))
                if media_ids:
                    for med_id in media_ids:
                        cursor.execute("INSERT INTO collection_items (collection_id, item_type, media_asset_id) VALUES (?, 'media', ?)", (col_id, med_id))

                # Pairs
                if pairs:
                    for p in pairs:
                        cursor.execute("""
                            INSERT INTO collection_pairs (collection_id, template_id, media_asset_id, pair_label, audience_rule)
                            VALUES (?, ?, ?, ?, ?)
                        """, (col_id, p["template_id"], p.get("media_asset_id"), p.get("pair_label", ""), p.get("audience_rule", "")))

                conn.commit()
                self.log_event("INFO", "Collections", f"Created content collection #{col_id} '{name}' (Mode: {pairing_mode})")
                return col_id

    def get_collections(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM content_collections ORDER BY id DESC")
            rows = cursor.fetchall()
            return [self.get_collection(r["id"]) for r in rows]

    def get_collection(self, collection_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM content_collections WHERE id = ?", (collection_id,))
            col = cursor.fetchone()
            if not col:
                return None
            res = dict(col)

            # Messages
            cursor.execute("""
                SELECT t.* FROM templates t
                JOIN collection_items ci ON ci.template_id = t.id
                WHERE ci.collection_id = ? AND ci.item_type = 'message'
            """, (collection_id,))
            res["messages"] = [dict(r) for r in cursor.fetchall()]

            # Media
            cursor.execute("""
                SELECT m.* FROM media_assets m
                JOIN collection_items ci ON ci.media_asset_id = m.id
                WHERE ci.collection_id = ? AND ci.item_type = 'media'
            """, (collection_id,))
            res["media"] = [self._enrich_media_asset(conn, dict(r)) for r in cursor.fetchall()]

            # Pairs
            cursor.execute("SELECT * FROM collection_pairs WHERE collection_id = ?", (collection_id,))
            res["pairs"] = [dict(r) for r in cursor.fetchall()]

            return res

    def update_collection(
        self,
        collection_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        pairing_mode: Optional[str] = None,
        message_ids: Optional[List[int]] = None,
        media_ids: Optional[List[int]] = None,
        pairs: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM content_collections WHERE id = ?", (collection_id,))
                col = cursor.fetchone()
                if not col:
                    return None

                now = datetime.now().isoformat()
                new_name = name if name is not None else col["name"]
                new_desc = description if description is not None else col["description"]
                new_mode = pairing_mode if pairing_mode is not None else col["pairing_mode"]

                cursor.execute("""
                    UPDATE content_collections
                    SET name = ?, description = ?, pairing_mode = ?, updated_at = ?
                    WHERE id = ?
                """, (new_name, new_desc, new_mode, now, collection_id))

                if message_ids is not None:
                    cursor.execute("DELETE FROM collection_items WHERE collection_id = ? AND item_type = 'message'", (collection_id,))
                    for mid in message_ids:
                        cursor.execute("INSERT INTO collection_items (collection_id, item_type, template_id) VALUES (?, 'message', ?)", (collection_id, mid))

                if media_ids is not None:
                    cursor.execute("DELETE FROM collection_items WHERE collection_id = ? AND item_type = 'media'", (collection_id,))
                    for med_id in media_ids:
                        cursor.execute("INSERT INTO collection_items (collection_id, item_type, media_asset_id) VALUES (?, 'media', ?)", (collection_id, med_id))

                if pairs is not None:
                    cursor.execute("DELETE FROM collection_pairs WHERE collection_id = ?", (collection_id,))
                    for p in pairs:
                        cursor.execute("""
                            INSERT INTO collection_pairs (collection_id, template_id, media_asset_id, pair_label, audience_rule)
                            VALUES (?, ?, ?, ?, ?)
                        """, (collection_id, p["template_id"], p.get("media_asset_id"), p.get("pair_label", ""), p.get("audience_rule", "")))

                conn.commit()
                return self.get_collection(collection_id)

    def delete_collection(self, collection_id: int) -> bool:
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM collection_items WHERE collection_id = ?", (collection_id,))
                cursor.execute("DELETE FROM collection_pairs WHERE collection_id = ?", (collection_id,))
                cursor.execute("DELETE FROM content_collections WHERE id = ?", (collection_id,))
                conn.commit()
                return cursor.rowcount > 0

    # --- Reusable Content Sets (Text Sets & Media Sets) ---

    def create_content_set(self, name: str, set_type: str, description: str = "", allocation_mode: str = "balanced") -> Dict[str, Any]:
        """Creates a new reusable Text Set or Media Set."""
        now = datetime.now().isoformat()
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO content_sets (name, set_type, description, allocation_mode, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name.strip(), set_type.lower(), description.strip(), allocation_mode.lower(), now, now))
                set_id = cursor.lastrowid
                conn.commit()
                self.log_event("INFO", "ContentSets", f"Created {set_type} set '{name}' (ID {set_id})")
                return self.get_content_set(set_id)

    def get_content_sets(self, set_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all content sets, optionally filtered by type ('text' or 'media')."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM content_sets WHERE 1=1"
            params = []
            if set_type and set_type.lower() != "all":
                query += " AND set_type = ?"
                params.append(set_type.lower())
            query += " ORDER BY id DESC"
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]

            for s in rows:
                sid = s["id"]
                cursor.execute("SELECT COUNT(*) as count FROM content_set_items WHERE set_id = ?", (sid,))
                s["total_items"] = cursor.fetchone()["count"]
                cursor.execute("SELECT COUNT(*) as count FROM content_set_items WHERE set_id = ? AND is_included = 1", (sid,))
                s["included_items"] = cursor.fetchone()["count"]
            return rows

    def get_content_set(self, set_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single content set with its full item contents and inclusion states."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM content_sets WHERE id = ?", (set_id,))
            row = cursor.fetchone()
            if not row:
                return None
            s = dict(row)

            # Retrieve items ordered by sort_order and id
            cursor.execute("SELECT * FROM content_set_items WHERE set_id = ? ORDER BY sort_order ASC, id ASC", (set_id,))
            raw_items = [dict(r) for r in cursor.fetchall()]
            enriched_items = []

            for item in raw_items:
                if item["item_type"] == "text" and item["template_id"]:
                    cursor.execute("SELECT * FROM templates WHERE id = ?", (item["template_id"],))
                    t = cursor.fetchone()
                    if t:
                        t_dict = dict(t)
                        item["title"] = t_dict["name"]
                        item["content"] = t_dict["content"]
                        item["variables"] = json.loads(t_dict.get("variables_json") or "[]")
                        enriched_items.append(item)
                elif item["item_type"] == "media" and item["media_asset_id"]:
                    cursor.execute("SELECT * FROM media_assets WHERE id = ?", (item["media_asset_id"],))
                    m = cursor.fetchone()
                    if m:
                        m_enriched = self._enrich_media_asset(conn, dict(m))
                        item["title"] = m_enriched["title"]
                        item["filename"] = m_enriched["filename"]
                        item["file_path"] = m_enriched["file_path"]
                        item["file_size"] = m_enriched["file_size"]
                        item["file_size_formatted"] = m_enriched["file_size_formatted"]
                        item["mime_type"] = m_enriched["mime_type"]
                        item["asset_type"] = m_enriched["asset_type"]
                        item["is_available"] = m_enriched["is_available"]
                        item["content_hash"] = m_enriched["content_hash"]
                        enriched_items.append(item)

            s["items"] = enriched_items
            s["total_items"] = len(enriched_items)
            s["included_items"] = len([it for it in enriched_items if it.get("is_included", 1) == 1])
            return s

    def update_content_set(self, set_id: int, name: Optional[str] = None, description: Optional[str] = None, allocation_mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Updates content set metadata."""
        now = datetime.now().isoformat()
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                updates = ["updated_at = ?"]
                params = [now]
                if name is not None:
                    updates.append("name = ?")
                    params.append(name.strip())
                if description is not None:
                    updates.append("description = ?")
                    params.append(description.strip())
                if allocation_mode is not None:
                    updates.append("allocation_mode = ?")
                    params.append(allocation_mode.lower())
                params.append(set_id)
                cursor.execute(f"UPDATE content_sets SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()
                return self.get_content_set(set_id)

    def delete_content_set(self, set_id: int) -> bool:
        """Deletes a content set and its associations (underlying library assets remain safe)."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM content_set_items WHERE set_id = ?", (set_id,))
                cursor.execute("DELETE FROM content_sets WHERE id = ?", (set_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
                self.log_event("WARNING", "ContentSets", f"Deleted content set ID {set_id}")
                return deleted

    def duplicate_content_set(self, set_id: int) -> Optional[Dict[str, Any]]:
        """Duplicates a content set with a new name and copies all items."""
        orig = self.get_content_set(set_id)
        if not orig:
            return None
        new_name = f"{orig['name']} (Copy)"
        new_set = self.create_content_set(
            name=new_name,
            set_type=orig["set_type"],
            description=orig.get("description", ""),
            allocation_mode=orig.get("allocation_mode", "balanced")
        )
        new_id = new_set["id"]

        now = datetime.now().isoformat()
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for it in orig.get("items", []):
                    cursor.execute("""
                        INSERT INTO content_set_items (set_id, item_type, template_id, media_asset_id, is_included, sort_order, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (new_id, it["item_type"], it.get("template_id"), it.get("media_asset_id"), it.get("is_included", 1), it.get("sort_order", 0), now))
                conn.commit()
        return self.get_content_set(new_id)

    def add_items_to_set(self, set_id: int, template_ids: Optional[List[int]] = None, media_asset_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """Adds existing templates or media assets to a content set."""
        now = datetime.now().isoformat()
        added_count = 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Find current max sort order
                cursor.execute("SELECT COALESCE(MAX(sort_order), 0) as max_sort FROM content_set_items WHERE set_id = ?", (set_id,))
                current_sort = cursor.fetchone()["max_sort"]

                if template_ids:
                    for tid in template_ids:
                        cursor.execute("SELECT id FROM content_set_items WHERE set_id = ? AND template_id = ?", (set_id, tid))
                        if not cursor.fetchone():
                            current_sort += 1
                            cursor.execute("""
                                INSERT INTO content_set_items (set_id, item_type, template_id, is_included, sort_order, created_at)
                                VALUES (?, 'text', ?, 1, ?, ?)
                            """, (set_id, tid, current_sort, now))
                            added_count += 1

                if media_asset_ids:
                    for mid in media_asset_ids:
                        cursor.execute("SELECT id FROM content_set_items WHERE set_id = ? AND media_asset_id = ?", (set_id, mid))
                        if not cursor.fetchone():
                            current_sort += 1
                            cursor.execute("""
                                INSERT INTO content_set_items (set_id, item_type, media_asset_id, is_included, sort_order, created_at)
                                VALUES (?, 'media', ?, 1, ?, ?)
                            """, (set_id, mid, current_sort, now))
                            added_count += 1

                conn.commit()
        return {"set": self.get_content_set(set_id), "added_count": added_count}

    def add_new_message_to_set(self, set_id: int, title: str, content: str) -> Dict[str, Any]:
        """Creates a new template directly and adds it to the specified Text Set."""
        unique_title = title
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, content FROM templates WHERE name = ?", (title,))
                row = cursor.fetchone()
                if row:
                    if row["content"] == content:
                        tpl_id = row["id"]
                    else:
                        unique_title = f"{title} ({datetime.now().strftime('%m%d_%H%M%S')})"
                        tpl_id = self.add_template(name=unique_title, content=content)
                else:
                    tpl_id = self.add_template(name=title, content=content)

        self.add_items_to_set(set_id=set_id, template_ids=[tpl_id])
        return self.get_content_set(set_id)

    def remove_items_from_set(self, set_id: int, item_ids: List[int]) -> int:
        """Removes items from a content set by item ID (underlying library assets are untouched)."""
        if not item_ids:
            return 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in item_ids)
                cursor.execute(f"DELETE FROM content_set_items WHERE set_id = ? AND id IN ({placeholders})", [set_id] + list(item_ids))
                removed = cursor.rowcount
                conn.commit()
                return removed

    def move_items_between_sets(self, source_set_id: int, target_set_id: int, item_ids: List[int]) -> int:
        """Moves selected items from one set to another."""
        if not item_ids or source_set_id == target_set_id:
            return 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in item_ids)
                cursor.execute(f"UPDATE content_set_items SET set_id = ? WHERE set_id = ? AND id IN ({placeholders})", [target_set_id, source_set_id] + list(item_ids))
                moved = cursor.rowcount
                conn.commit()
                return moved

    def copy_items_between_sets(self, source_set_id: int, target_set_id: int, item_ids: List[int]) -> int:
        """Copies selected items into another set."""
        if not item_ids:
            return 0
        now = datetime.now().isoformat()
        copied = 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in item_ids)
                cursor.execute(f"SELECT * FROM content_set_items WHERE set_id = ? AND id IN ({placeholders})", [source_set_id] + list(item_ids))
                items_to_copy = [dict(r) for r in cursor.fetchall()]

                for it in items_to_copy:
                    cursor.execute("""
                        INSERT INTO content_set_items (set_id, item_type, template_id, media_asset_id, is_included, sort_order, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (target_set_id, it["item_type"], it.get("template_id"), it.get("media_asset_id"), it.get("is_included", 1), it.get("sort_order", 0), now))
                    copied += 1
                conn.commit()
                return copied

    def toggle_set_item_included(self, item_id: int, is_included: Optional[int] = None) -> bool:
        """Toggles or sets the temporary campaign inclusion state (1 = included, 0 = excluded)."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if is_included is None:
                    cursor.execute("UPDATE content_set_items SET is_included = CASE WHEN is_included = 1 THEN 0 ELSE 1 END WHERE id = ?", (item_id,))
                else:
                    cursor.execute("UPDATE content_set_items SET is_included = ? WHERE id = ?", (1 if is_included else 0, item_id))
                conn.commit()
                return cursor.rowcount > 0

    def bulk_toggle_set_items(self, item_ids: List[int], is_included: int) -> int:
        """Bulk updates inclusion state across multiple set items."""
        if not item_ids:
            return 0
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in item_ids)
                cursor.execute(f"UPDATE content_set_items SET is_included = ? WHERE id IN ({placeholders})", [1 if is_included else 0] + list(item_ids))
                updated = cursor.rowcount
                conn.commit()
                return updated

    def auto_seed_default_sets_if_empty(self):
        """Ensures at least one working Text Set and Media Set exists, populated with approved items."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Check Text Sets
                cursor.execute("SELECT id FROM content_sets WHERE set_type = 'text'")
                if not cursor.fetchone():
                    now = datetime.now().isoformat()
                    cursor.execute("""
                        INSERT INTO content_sets (name, set_type, description, allocation_mode, created_at, updated_at)
                        VALUES ('Primary Campaign Messages', 'text', 'Default campaign messaging pool', 'balanced', ?, ?)
                    """, (now, now))
                    text_set_id = cursor.lastrowid
                    cursor.execute("SELECT id FROM templates ORDER BY id ASC LIMIT 5")
                    for t in cursor.fetchall():
                        cursor.execute("""
                            INSERT INTO content_set_items (set_id, item_type, template_id, is_included, sort_order, created_at)
                            VALUES (?, 'text', ?, 1, 0, ?)
                        """, (text_set_id, t["id"], now))

                # Check Media Sets
                cursor.execute("SELECT id FROM content_sets WHERE set_type = 'media'")
                if not cursor.fetchone():
                    now = datetime.now().isoformat()
                    cursor.execute("""
                        INSERT INTO content_sets (name, set_type, description, allocation_mode, created_at, updated_at)
                        VALUES ('Promotional Media & Banners', 'media', 'Standard creative media set', 'balanced', ?, ?)
                    """, (now, now))
                    media_set_id = cursor.lastrowid
                    cursor.execute("SELECT id FROM media_assets ORDER BY id ASC LIMIT 5")
                    for m in cursor.fetchall():
                        cursor.execute("""
                            INSERT INTO content_set_items (set_id, item_type, media_asset_id, is_included, sort_order, created_at)
                            VALUES (?, 'media', ?, 1, 0, ?)
                        """, (media_set_id, m["id"], now))
                conn.commit()

    def cleanup_synthetic_test_data(self) -> Dict[str, int]:
        """Cleans up auto-generated synthetic test records cluttering templates and media while protecting genuine user content."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Purge synthetic templates with timestamped suffixes
                cursor.execute("DELETE FROM templates WHERE name LIKE '%17938%' OR name LIKE 'Test Template %' OR name = 'MEOW' OR name LIKE 'Rotation Template%' OR name LIKE 'Seeded AB%'")
                cleaned_templates = cursor.rowcount

                # Purge 16-byte dummy Q4 Brochure copies from tests if more than 1 exist
                cursor.execute("SELECT id FROM media_assets WHERE title = 'Q4 Brochure' AND file_size = 16 ORDER BY id ASC")
                brochures = cursor.fetchall()
                cleaned_media = 0
                if len(brochures) > 1:
                    # Keep the first one, delete subsequent duplicates
                    dup_ids = [b["id"] for b in brochures[1:]]
                    placeholders = ",".join("?" for _ in dup_ids)
                    cursor.execute(f"DELETE FROM media_assets WHERE id IN ({placeholders})", dup_ids)
                    cleaned_media = cursor.rowcount

                conn.commit()
                return {"cleaned_templates": cleaned_templates, "cleaned_media": cleaned_media}

    def get_overview_kpis(self) -> Dict[str, Any]:
        """Calculates system KPIs for dashboard overview."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM contacts")
            total_contacts = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE consent_status = 'opted_in'")
            opted_in_contacts = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM suppression_list")
            suppressed_contacts = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM templates")
            total_templates = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM media_assets")
            total_media_assets = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM jobs")
            total_jobs = cursor.fetchone()["count"]

            cursor.execute("SELECT SUM(sent_count) as sent, SUM(failed_count) as failed FROM jobs")
            row = cursor.fetchone()
            total_sent = row["sent"] or 0
            total_failed = row["failed"] or 0
            total_attempted = total_sent + total_failed
            success_rate = round((total_sent / total_attempted * 100), 1) if total_attempted > 0 else 100.0

            return {
                "total_contacts": total_contacts,
                "opted_in_contacts": opted_in_contacts,
                "suppressed_contacts": suppressed_contacts,
                "total_templates": total_templates,
                "total_media_assets": total_media_assets,
                "total_jobs": total_jobs,
                "total_sent": total_sent,
                "total_failed": total_failed,
                "success_rate": success_rate
            }

    # --- Persistent Browser Profile Preferences Operations ---

    def get_browser_profile_preference(self) -> Dict[str, Any]:
        """
        Retrieves the persistent browser profile preference singleton.
        Cleanly separates preferred personal profile from the active Relay automation session
        so unsupported Chrome profiles never overwrite the working persistent session.
        """
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM browser_profile_preferences WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    res = dict(row)
                    res["remember_profile"] = bool(res.get("remember_profile", 1))
                    res["auto_connect"] = bool(res.get("auto_connect", 0))

                    # Provide clean structured separation while keeping legacy keys
                    pers_b = res.get("preferred_personal_browser") or res.get("browser_id") or "chrome"
                    pers_p = res.get("preferred_personal_profile_dir") or res.get("canonical_profile_dir") or "Profile 10"
                    pers_name = res.get("preferred_personal_profile_name") or res.get("profile_display_name") or "whatsapp auto"

                    # Check automation support for personal profile non-destructively
                    from browser_manager import BrowserManager
                    is_supp, unsupp_r, _ = BrowserManager.is_profile_automation_supported(
                        pers_b, profile_dir=pers_p, is_dedicated=False
                    )

                    res["preferred_personal_profile"] = {
                        "browser": pers_b,
                        "profile_dir": pers_p,
                        "profile_name": pers_name,
                        "is_supported": is_supp,
                        "unsupported_reason": unsupp_r if not is_supp else ""
                    }
                    res["selected_automation_mode"] = res.get("selected_automation_mode") or res.get("connection_mode") or "dedicated"
                    res["active_relay_session"] = {
                        "browser": "chrome",
                        "profile_dir": res.get("active_relay_session_dir") or "__dedicated__",
                        "profile_name": res.get("active_relay_session_name") or "Relay Automation Session",
                        "is_dedicated": True,
                        "is_supported": True
                    }
                    res["last_connected_session"] = {
                        "browser": res.get("last_connected_browser") or "chrome",
                        "profile_dir": res.get("last_connected_profile_dir") or "__dedicated__",
                        "profile_name": res.get("last_connected_profile_name") or "Relay Automation Session",
                        "mode": res.get("last_connected_mode") or "dedicated",
                        "connected_at": res.get("last_connected_at"),
                        "was_authenticated": bool(res.get("last_connected_was_authenticated", 1))
                    }
                    return res

                return self._seed_default_browser_preference(conn)

    def _seed_default_browser_preference(self, conn) -> Dict[str, Any]:
        """Discovers local Chrome profiles and seeds preferred personal profile and dedicated automation session."""
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        browser_id = "chrome"
        browser_family = "chrome"
        browser_exe_path = ""
        profile_display_name = "Dedicated WhatsApp Session"
        canonical_profile_dir = "__dedicated__"
        connection_mode = "dedicated"
        personal_profile_dir = "Profile 10"
        personal_display_name = "whatsapp auto"
        personal_is_supported = 0

        try:
            from browser_manager import BrowserManager
            installed = BrowserManager.get_installed_browsers()
            if "chrome" in installed:
                browser_exe_path = installed["chrome"].get("exe_path", "")
                profiles = BrowserManager.get_profiles("chrome")
                for p in profiles:
                    dname = (p.get("display_name") or p.get("name") or "").lower()
                    if "whatsapp auto" in dname:
                        personal_profile_dir = p.get("dir", "Profile 10")
                        personal_display_name = p.get("display_name") or "whatsapp auto"
                        is_supp, _, _ = BrowserManager.is_profile_automation_supported(
                            "chrome", profile_dir=personal_profile_dir, is_dedicated=False
                        )
                        personal_is_supported = 1 if is_supp else 0
                        break
        except Exception:
            pass

        cursor.execute("""
            INSERT OR REPLACE INTO browser_profile_preferences (
                id, browser_id, browser_family, browser_exe_path,
                profile_display_name, canonical_profile_dir, connection_mode,
                preferred_personal_browser, preferred_personal_profile_dir,
                preferred_personal_profile_name, preferred_personal_is_supported,
                selected_automation_mode, active_relay_session_dir, active_relay_session_name,
                last_connected_browser, last_connected_profile_dir, last_connected_profile_name,
                last_connected_mode, last_connected_was_authenticated,
                remember_profile, auto_connect, last_selected_at, last_connected_at,
                schema_version, created_at, updated_at
            ) VALUES (
                1, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                'dedicated', '__dedicated__', 'Relay Automation Session',
                'chrome', '__dedicated__', 'Relay Automation Session',
                'dedicated', 1,
                1, 0, ?, NULL, 1, ?, ?
            )
        """, (
            browser_id, browser_family, browser_exe_path,
            personal_display_name, personal_profile_dir, "existing_profile",
            browser_id, personal_profile_dir,
            personal_display_name, personal_is_supported,
            now, now, now
        ))
        conn.commit()

        cursor.execute("SELECT * FROM browser_profile_preferences WHERE id = 1")
        row = cursor.fetchone()
        res = dict(row)
        res["remember_profile"] = bool(res.get("remember_profile", 1))
        res["auto_connect"] = bool(res.get("auto_connect", 0))
        return self.get_browser_profile_preference()

    def save_browser_profile_preference(
        self,
        browser_id: str,
        canonical_profile_dir: str,
        profile_display_name: str,
        connection_mode: str = "existing_profile",
        remember_profile: bool = True,
        auto_connect: bool = False,
        browser_exe_path: Optional[str] = None,
        browser_family: Optional[str] = None,
        selected_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """Persists the user's browser profile preference while keeping personal vs automation tracking separated."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                family = browser_family or browser_id.lower()

                if not browser_exe_path:
                    try:
                        from browser_manager import BrowserManager
                        installed = BrowserManager.get_installed_browsers()
                        b_info = installed.get(browser_id.lower(), {})
                        browser_exe_path = b_info.get("exe_path", "")
                    except Exception:
                        browser_exe_path = ""

                is_dedicated = (canonical_profile_dir == "__dedicated__")
                mode = selected_mode or ("dedicated" if is_dedicated else connection_mode)

                from browser_manager import BrowserManager
                is_supp, _, _ = BrowserManager.is_profile_automation_supported(
                    browser_id, profile_dir=canonical_profile_dir, is_dedicated=is_dedicated
                )

                # If user selected an existing personal profile, remember it under preferred_personal_*
                pers_b = browser_id if not is_dedicated else "chrome"
                pers_p = canonical_profile_dir if not is_dedicated else "Profile 10"
                pers_name = profile_display_name if not is_dedicated else "whatsapp auto"

                cursor.execute("""
                    INSERT OR REPLACE INTO browser_profile_preferences (
                        id, browser_id, browser_family, browser_exe_path,
                        profile_display_name, canonical_profile_dir, connection_mode,
                        preferred_personal_browser, preferred_personal_profile_dir,
                        preferred_personal_profile_name, preferred_personal_is_supported,
                        selected_automation_mode, active_relay_session_dir, active_relay_session_name,
                        remember_profile, auto_connect, last_selected_at,
                        schema_version, created_at, updated_at
                    ) VALUES (
                        1, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, '__dedicated__', 'Relay Automation Session',
                        ?, ?, ?,
                        1,
                        COALESCE((SELECT created_at FROM browser_profile_preferences WHERE id = 1), ?),
                        ?
                    )
                """, (
                    browser_id, family, browser_exe_path,
                    profile_display_name, canonical_profile_dir, mode,
                    pers_b, pers_p,
                    pers_name, 1 if (is_supp and not is_dedicated) else 0,
                    mode,
                    1 if remember_profile else 0,
                    1 if auto_connect else 0,
                    now, now, now
                ))
                conn.commit()
                return self.get_browser_profile_preference()

    def update_browser_last_connected(
        self,
        browser: str = "chrome",
        profile_dir: str = "__dedicated__",
        profile_name: str = "Relay Automation Session",
        mode: str = "dedicated",
        was_authenticated: bool = True
    ):
        """Updates last_connected metadata upon successful WhatsApp Web authentication."""
        with _lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("""
                    UPDATE browser_profile_preferences SET
                        last_connected_at = ?,
                        last_connected_browser = ?,
                        last_connected_profile_dir = ?,
                        last_connected_profile_name = ?,
                        last_connected_mode = ?,
                        last_connected_was_authenticated = ?,
                        updated_at = ?
                    WHERE id = 1
                """, (now, browser, profile_dir, profile_name, mode, 1 if was_authenticated else 0, now))
                conn.commit()


# Global singleton database manager instance
db = DatabaseManager()
