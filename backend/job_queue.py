"""
Background Job Queue and Execution Worker for WhatsApp Automation.
Provides thread-safe job scheduling, lifecycle state management (QUEUED, RUNNING,
PAUSED, COMPLETED, FAILED, CANCELLED), progress callbacks, and WebSocket telemetry.
Integrates durable SQLite queue items with deterministic idempotency keys and retry policies.
"""

import os
import uuid
import threading
import time
from datetime import datetime
import hashlib
import random
from typing import List, Dict, Any, Optional, Callable

from backend.database import db
from backend.adapter import MessagingProvider, WhatsAppWebAdapter, MockMessagingProvider
from backend.routers.templates import resolve_variant_and_render
from logger import get_logger, mask_phone

logger = get_logger("JobQueue")


class BackgroundJobWorker:
    """Manages active job execution in a dedicated background worker thread with durable queueing."""

    def __init__(self):
        self._active_job: Optional[Dict[str, Any]] = None
        self._active_provider: Optional[MessagingProvider] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.RLock()
        self._is_paused = False
        self._is_stopped = False
        self._schedule_timer: Optional[threading.Timer] = None
        self._worker_args: Optional[tuple] = None

        # Register intelligent connection monitor observer
        try:
            from backend.connection_monitor import connection_monitor
            connection_monitor.register_listener(self._on_connection_change)
        except Exception as e:
            logger.debug(f"Could not attach connection monitor listener: {e}")

    def _on_connection_change(self, state: str, snapshot: Dict[str, Any]):
        """Auto-resumes campaigns waiting for connection once WhatsApp Web becomes authenticated."""
        with self._lock:
            if not self._active_job or self._is_stopped:
                return
            cur_status = self._active_job.get("status")

        if state == "connected" and cur_status == "WAITING_FOR_CONNECTION":
            with self._lock:
                job_id = self._active_job.get("id")
                worker_args = self._worker_args
                self._active_job["status"] = "RUNNING"

            db.update_job_status(job_id, "RUNNING")
            db.log_event("INFO", "JobQueue", f"WhatsApp connection established! Auto-resuming campaign {job_id}.")
            self._broadcast({
                "type": "job_started",
                "job": self._active_job
            })

            if worker_args and (not self._worker_thread or not self._worker_thread.is_alive()):
                self._worker_thread = threading.Thread(
                    target=self._run_job_worker,
                    args=worker_args,
                    daemon=True,
                    name=f"JobWorker-{job_id}"
                )
                self._worker_thread.start()

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """Registers a listener for real-time telemetry (used by WebSocket manager)."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """Unregisters a telemetry listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _broadcast(self, event: Dict[str, Any]):
        """Broadcasts an event dictionary to all registered listeners."""
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.debug(f"Error dispatching to listener: {e}")

    def get_active_job(self) -> Optional[Dict[str, Any]]:
        """Returns the currently active job snapshot or None."""
        with self._lock:
            return dict(self._active_job) if self._active_job else None

    def start_campaign_job(
        self,
        campaign_name: str,
        contacts: List[Dict[str, Any]],
        template_content: str,
        min_delay: float = 8.0,
        max_delay: float = 15.0,
        batch_size: int = 20,
        batch_pause: float = 60.0,
        daily_cap: int = 100,
        attachment_path: Optional[str] = None,
        media_asset_id: Optional[int] = None,
        allocation_method: str = "explicit_default",
        allocation_seed: int = 42,
        use_mock: bool = False,
        max_retries: int = 3,
        template_id: Optional[int] = None,
        collection_id: Optional[int] = None,
        text_set_id: Optional[int] = None,
        media_set_id: Optional[int] = None,
        job_id: Optional[str] = None,
        scheduled_at: Optional[str] = None,
        provider: Optional[MessagingProvider] = None,
        message_format: str = "image_with_caption"
    ) -> Dict[str, Any]:
        """
        Stages recipients into durable queue items with SHA-256 idempotency keys,
        enforces suppression lists, and initiates asynchronous execution or schedules dispatch.
        """
        with self._lock:
            if self._active_job and self._active_job.get("status") in ("QUEUED", "RUNNING", "PAUSED", "SCHEDULED"):
                raise RuntimeError("Another campaign job is already in progress or scheduled. Please pause or cancel it first.")

            actual_job_id = job_id or str(uuid.uuid4())[:8]
            self._is_paused = False
            self._is_stopped = False
            if self._schedule_timer:
                try:
                    self._schedule_timer.cancel()
                    self._schedule_timer = None
                except Exception:
                    pass

            # Calculate scheduling delay if scheduled_at provided
            delay_seconds = 0.0
            if scheduled_at:
                try:
                    dt_str = scheduled_at.replace("Z", "")
                    target_dt = datetime.fromisoformat(dt_str)
                    now_dt = datetime.now()
                    diff = (target_dt - now_dt).total_seconds()
                    if diff > 2.0:
                        delay_seconds = diff
                except Exception as ex:
                    logger.warning(f"Could not parse scheduled_at '{scheduled_at}': {ex}")

            # Determine initial status based on scheduling and live connection availability
            if delay_seconds > 0:
                initial_status = "SCHEDULED"
            elif not use_mock:
                try:
                    from backend.connection_monitor import connection_monitor
                    initial_status = "RUNNING" if connection_monitor.is_connected() else "WAITING_FOR_CONNECTION"
                except Exception:
                    initial_status = "RUNNING"
            else:
                initial_status = "RUNNING"

            # Retrieve template and purpose-driven variants if specified
            template = db.get_template(template_id) if template_id else None
            variants = db.get_message_variants(template_id) if template_id else []
            approved_variants = [v for v in variants if v.get("approval_status") == "approved"]

            # Retrieve content collection if specified
            collection = db.get_collection(collection_id) if collection_id else None
            col_mode = collection.get("pairing_mode", "fixed_pair") if collection else None
            col_messages = collection.get("messages", []) if collection else []
            col_media = collection.get("media", []) if collection else []
            col_pairs = collection.get("pairs", []) if collection else []

            # Retrieve Text Set & Media Set if specified
            eligible_set_texts = []
            if text_set_id:
                t_set = db.get_content_set(text_set_id)
                if t_set:
                    eligible_set_texts = [it for it in t_set.get("items", []) if it.get("is_included", 1) == 1]

            eligible_set_media = []
            if media_set_id:
                m_set = db.get_content_set(media_set_id)
                if m_set:
                    eligible_set_media = [it for it in m_set.get("items", []) if it.get("is_included", 1) == 1]

            # Unified Template Active Assets and Variations
            tpl_active_texts = [tv for tv in template.get("text_variations", []) if tv.get("is_active", 1)] if template else []
            tpl_active_media = [ma for ma in template.get("media_assets", []) if ma.get("is_active", 1)] if template else []
            tpl_mode = template.get("content_selection_mode", "mix_variations") if template else "mix_variations"
            chosen_msg_format = message_format or (template.get("message_format") if template else "image_with_caption") or "image_with_caption"

            # If explicit alternatives exist beyond the auto-created Primary Variant, use those for rotation / AB testing
            rotation_variants = [v for v in approved_variants if v.get("variant_name") != "Primary Variant"]
            if not rotation_variants:
                rotation_variants = approved_variants

            # Stage queue items with suppression checks and idempotency keys
            queue_records = []
            suppressed_count = 0
            eligible_count = 0

            # Restrict total eligible recipients to daily_cap
            capped_contacts = contacts[:daily_cap]

            for idx, c in enumerate(capped_contacts):
                phone = str(c.get("phone", "")).strip()
                name = c.get("name", "Customer")

                content_template = template_content or (template.get("content") if template else "")
                item_media_asset_id = media_asset_id
                chosen_variant = None
                allocation_rule = ""

                if (tpl_active_texts or tpl_active_media) and allocation_method not in ("rule_based", "balanced_rotation", "reproducible_ab_test"):
                    if tpl_mode == "same_for_everyone":
                        content_template = tpl_active_texts[0]["content"] if tpl_active_texts else template_content
                        item_media_asset_id = tpl_active_media[0]["id"] if tpl_active_media else media_asset_id
                        allocation_rule = "Template Fixed (Same for Everyone)"
                    else:
                        text_idx = int(hashlib.md5(f"{allocation_seed}:text:{phone}".encode("utf-8")).hexdigest(), 16) if tpl_active_texts else 0
                        media_idx = int(hashlib.md5(f"{allocation_seed}:media:{phone}".encode("utf-8")).hexdigest(), 16) if tpl_active_media else 0
                        content_template = tpl_active_texts[text_idx % len(tpl_active_texts)]["content"] if tpl_active_texts else template_content
                        item_media_asset_id = tpl_active_media[media_idx % len(tpl_active_media)]["id"] if tpl_active_media else media_asset_id
                        allocation_rule = f"Template Mix Variations (Seed {allocation_seed})"
                    variant_id = None
                    variant_purpose = ""
                elif eligible_set_texts or eligible_set_media:
                    if eligible_set_texts:
                        chosen_text = eligible_set_texts[idx % len(eligible_set_texts)]
                        content_template = chosen_text.get("content", "")
                        allocation_rule = f"Text Set ({chosen_text.get('title')})"
                    else:
                        content_template = template_content
                    
                    if eligible_set_media:
                        chosen_med = eligible_set_media[idx % len(eligible_set_media)]
                        item_media_asset_id = chosen_med.get("media_asset_id") or chosen_med.get("id")
                    else:
                        item_media_asset_id = media_asset_id
                    variant_id = None
                    variant_purpose = ""
                elif collection:
                    if col_mode == "fixed_pair":
                        t_obj = col_messages[0] if col_messages else template
                        content_template = t_obj.get("content", "") if t_obj else template_content
                        m_obj = col_media[0] if col_media else None
                        item_media_asset_id = m_obj.get("id") if m_obj else media_asset_id
                        allocation_rule = f"Collection Fixed Pair: {collection.get('name')}"
                    elif col_mode == "approved_combinations" and col_pairs:
                        pair = col_pairs[idx % len(col_pairs)]
                        t_obj = db.get_template(pair["template_id"])
                        content_template = t_obj.get("content", "") if t_obj else template_content
                        item_media_asset_id = pair.get("media_asset_id") or media_asset_id
                        allocation_rule = f"Collection Combination #{idx % len(col_pairs) + 1}: {collection.get('name')}"
                    else:
                        t_obj = col_messages[idx % len(col_messages)] if col_messages else template
                        content_template = t_obj.get("content", "") if t_obj else template_content
                        m_obj = col_media[idx % len(col_media)] if col_media else None
                        item_media_asset_id = m_obj.get("id") if m_obj else media_asset_id
                        allocation_rule = f"Collection Balanced: {collection.get('name')}"
                    variant_id = None
                    variant_purpose = ""
                elif allocation_method == "rule_based" and approved_variants:
                    for v in approved_variants:
                        field = v.get("audience_filter_field", "")
                        req_val = str(v.get("audience_filter_value", "")).strip().lower()
                        if not field or not req_val or field == "all":
                            continue
                        # Check direct contact field
                        c_val = str(c.get(field, "")).strip().lower()
                        # Also check in custom_fields
                        if not c_val and isinstance(c.get("custom_fields"), dict):
                            c_val = str(c["custom_fields"].get(field, "")).strip().lower()
                        if c_val and c_val == req_val:
                            chosen_variant = v
                            allocation_rule = f"Rule-based: {field}='{v.get('audience_filter_value')}'"
                            break

                elif allocation_method == "balanced_rotation" and rotation_variants:
                    chosen_variant = rotation_variants[idx % len(rotation_variants)]
                    allocation_rule = f"Balanced rotation: variant #{chosen_variant['id']} ({chosen_variant['variant_name']})"

                elif allocation_method == "reproducible_ab_test" and rotation_variants:
                    h = int(hashlib.md5(f"{allocation_seed}:{phone}".encode("utf-8")).hexdigest(), 16)
                    chosen_variant = rotation_variants[h % len(rotation_variants)]
                    allocation_rule = f"Reproducible A/B test (seed={allocation_seed}): variant #{chosen_variant['id']} ({chosen_variant['variant_name']})"

                if not collection and allocation_method in ("rule_based", "balanced_rotation", "reproducible_ab_test", "explicit_default"):
                    if not chosen_variant:
                        if approved_variants and allocation_method == "explicit_default":
                            chosen_variant = approved_variants[0]
                            allocation_rule = f"Explicit default: variant #{chosen_variant['id']} ({chosen_variant['variant_name']})"
                        else:
                            allocation_rule = allocation_rule or "Default fallback"

                    if chosen_variant:
                        variant_id = chosen_variant["id"]
                        variant_purpose = chosen_variant.get("purpose", "")
                        content_template = chosen_variant.get("content", "")
                        item_media_asset_id = chosen_variant.get("media_asset_id") or media_asset_id
                    elif not (tpl_active_texts or tpl_active_media) and not (eligible_set_texts or eligible_set_media):
                        variant_id = None
                        variant_purpose = ""
                        content_template = c.get("message") or template_content or (template.get("content") if template else "")
                        item_media_asset_id = media_asset_id

                # Render content with variable interpolation
                rendered = content_template
                all_fields = dict(c)
                if isinstance(c.get("custom_fields"), dict):
                    all_fields.update(c["custom_fields"])
                all_fields["name"] = name
                all_fields["first_name"] = name.split()[0] if name else "Friend"
                all_fields["phone"] = phone
                all_fields["group"] = c.get("group_name", "")
                for k, v in all_fields.items():
                    if isinstance(v, (str, int, float)):
                        rendered = rendered.replace(f"{{{k}}}", str(v))

                from whatsapp_engine import process_spintax
                resolved_msg = process_spintax(rendered)

                # Associated media: variant media takes precedence over campaign-level attachment
                item_media_path = attachment_path or ""
                if item_media_asset_id:
                    asset = db.get_media_asset(item_media_asset_id)
                    if asset and asset.get("file_path"):
                        item_media_path = asset["file_path"]

                # Check global suppression list and contact opt-out status
                is_suppressed = db.is_phone_suppressed(phone) or (c.get("consent_status") == "opted_out")

                # Deterministic SHA-256 idempotency key: hash of job + campaign + phone + variant
                idempotency_raw = f"{actual_job_id}:{campaign_name}:{phone}:{variant_id or 0}"
                idempotency_key = hashlib.sha256(idempotency_raw.encode("utf-8")).hexdigest()

                if is_suppressed:
                    status = "SUPPRESSED"
                    error_msg = "Recipient suppressed: phone on global opt-out list"
                    suppressed_count += 1
                else:
                    status = "PENDING"
                    error_msg = ""
                    eligible_count += 1

                queue_records.append({
                    "idempotency_key": idempotency_key,
                    "recipient_name": name,
                    "recipient_phone": phone,
                    "variant_id": variant_id,
                    "variant_purpose": variant_purpose,
                    "resolved_message": resolved_msg,
                    "media_path": item_media_path,
                    "media_asset_id": item_media_asset_id,
                    "allocation_rule": allocation_rule,
                    "message_format": chosen_msg_format,
                    "status": status,
                    "max_retries": max_retries,
                    "error_message": error_msg
                })

            job_record = db.create_job(
                job_id=actual_job_id,
                campaign_name=campaign_name,
                total_count=eligible_count,
                suppressed_count=suppressed_count,
                scheduled_at=scheduled_at if delay_seconds > 0 else None
            )

            # Bulk insert into durable campaign_queue_items table
            db.bulk_enqueue_items(
                campaign_id=campaign_name,
                job_id=actual_job_id,
                items=queue_records
            )

            self._active_job = {
                "id": actual_job_id,
                "campaign_name": campaign_name,
                "status": initial_status,
                "total_count": eligible_count,
                "suppressed_count": suppressed_count,
                "sent_count": 0,
                "failed_count": 0,
                "current_recipient": "",
                "started_at": job_record["started_at"],
                "scheduled_at": scheduled_at if delay_seconds > 0 else None
            }

            provider = provider or (MockMessagingProvider() if use_mock else WhatsAppWebAdapter())
            self._active_provider = provider
            worker_args = (actual_job_id, min_delay, max_delay, batch_size, batch_pause, max_retries, provider, use_mock)
            self._worker_args = worker_args

            def _start_worker():
                with self._lock:
                    if self._is_stopped or not self._active_job or self._active_job.get("id") != actual_job_id:
                        return
                    self._active_job["status"] = "RUNNING"
                db.update_job_status(actual_job_id, "RUNNING")
                db.log_event("INFO", "JobQueue", f"Scheduled job {actual_job_id} for '{campaign_name}' is now RUNNING.")
                self._broadcast({
                    "type": "job_started",
                    "job": self._active_job
                })
                self._worker_thread = threading.Thread(
                    target=self._run_job_worker,
                    args=worker_args,
                    daemon=True,
                    name=f"JobWorker-{actual_job_id}"
                )
                self._worker_thread.start()

            if delay_seconds > 0:
                db.log_event("INFO", "JobQueue", f"Scheduled job {actual_job_id} for '{campaign_name}' to start in {int(delay_seconds)}s ({scheduled_at})")
                self._schedule_timer = threading.Timer(delay_seconds, _start_worker)
                self._schedule_timer.daemon = True
                self._schedule_timer.start()
                self._broadcast({
                    "type": "job_scheduled",
                    "job": self._active_job
                })
            elif initial_status == "WAITING_FOR_CONNECTION":
                db.update_job_status(actual_job_id, "WAITING_FOR_CONNECTION")
                db.log_event("WARNING", "JobQueue", f"Campaign {actual_job_id} for '{campaign_name}' is WAITING_FOR_CONNECTION. Sending will start automatically once connected.")
                self._broadcast({
                    "type": "job_waiting_for_connection",
                    "job": self._active_job
                })
            else:
                db.update_job_status(actual_job_id, "RUNNING")
                db.log_event("INFO", "JobQueue", f"Launched job {actual_job_id} for '{campaign_name}' ({eligible_count} eligible, {suppressed_count} suppressed)")
                self._worker_thread = threading.Thread(
                    target=self._run_job_worker,
                    args=worker_args,
                    daemon=True,
                    name=f"JobWorker-{actual_job_id}"
                )
                self._worker_thread.start()
                self._broadcast({
                    "type": "job_started",
                    "job": self._active_job
                })

            return dict(self._active_job)

    def _run_job_worker(
        self,
        job_id: str,
        min_delay: float,
        max_delay: float,
        batch_size: int,
        batch_pause: float,
        max_retries: int,
        provider: MessagingProvider,
        use_mock: bool
    ):
        """Worker thread entry point executing durable queue message dispatches."""
        sent_count = 0
        failed_count = 0

        # Retrieve pending items from database
        pending_items = db.get_queue_items(job_id=job_id, status="PENDING", limit=10000)
        total_items = len(pending_items)

        def log_event(message: str, level: str = "INFO"):
            db.log_event(level, "Automation", message)
            self._broadcast({
                "type": "log_event",
                "timestamp": time.strftime("%H:%M:%S"),
                "level": level,
                "message": message
            })

        log_event(f"Starting queue dispatch for job {job_id}: {total_items} pending recipients.")

        try:
            for idx, item in enumerate(pending_items, 1):
                # Check for cancellation
                if self._is_stopped:
                    log_event(f"Job {job_id} cancelled by operator.", "WARNING")
                    break

                # Handle pause
                while self._is_paused:
                    time.sleep(0.2)
                    if self._is_stopped:
                        break
                if self._is_stopped:
                    break

                # Pre-send connection readiness check
                if not use_mock:
                    try:
                        from backend.connection_monitor import connection_monitor
                        if not connection_monitor.is_connected():
                            log_event(f"Connection lost mid-campaign at recipient {idx}/{total_items}. Pausing campaign safely without marking unsent as sent.", "WARNING")
                            with self._lock:
                                if self._active_job and self._active_job.get("id") == job_id:
                                    self._active_job["status"] = "WAITING_FOR_CONNECTION"
                            db.update_job_status(job_id, "WAITING_FOR_CONNECTION")
                            self._broadcast({
                                "type": "job_waiting_for_connection",
                                "job_id": job_id,
                                "status": "WAITING_FOR_CONNECTION"
                            })
                            while not self._is_stopped and not self._is_paused:
                                time.sleep(1.0)
                                if connection_monitor.is_connected():
                                    log_event(f"Connection restored! Continuing campaign {job_id} at recipient {idx}/{total_items}.", "INFO")
                                    with self._lock:
                                        if self._active_job and self._active_job.get("id") == job_id:
                                            self._active_job["status"] = "RUNNING"
                                    db.update_job_status(job_id, "RUNNING")
                                    self._broadcast({
                                        "type": "job_resumed",
                                        "job_id": job_id,
                                        "status": "RUNNING"
                                    })
                                    break
                            if self._is_stopped or self._is_paused:
                                break
                    except Exception as ex:
                        logger.debug(f"Connection check error: {ex}")

                recipient_name = item.get("recipient_name", "Customer")
                recipient_phone = item.get("recipient_phone", "")
                masked = mask_phone(recipient_phone)
                resolved_msg = item.get("resolved_message", "")
                media_path = item.get("media_path", "")

                # Honest media check: If media is specified, ensure it exists on disk!
                if media_path and not os.path.isfile(media_path):
                    err_msg = f"Media failed — file missing on disk: {media_path}. No text was sent."
                    db.update_queue_item_status(item["id"], "FAILED_PERMANENT", error_message=err_msg)
                    db.record_job_result(
                        job_id=job_id,
                        name=recipient_name,
                        phone=recipient_phone,
                        status="FAILED",
                        error=f"[FAILED_PERMANENT] {err_msg}",
                        attachment=media_path
                    )
                    failed_count += 1
                    log_event(f"  -> Dispatch aborted for +{masked}: {err_msg}", "ERROR")
                    continue
                if media_path and os.path.isfile(media_path) and os.path.getsize(media_path) == 0:
                    err_msg = f"Media failed — file is 0 bytes: {media_path}. No text was sent."
                    db.update_queue_item_status(item["id"], "FAILED_PERMANENT", error_message=err_msg)
                    db.record_job_result(
                        job_id=job_id,
                        name=recipient_name,
                        phone=recipient_phone,
                        status="FAILED",
                        error=f"[FAILED_PERMANENT] {err_msg}",
                        attachment=media_path
                    )
                    failed_count += 1
                    log_event(f"  -> Dispatch aborted for +{masked}: {err_msg}", "ERROR")
                    continue

                with self._lock:
                    if self._active_job and self._active_job.get("id") == job_id:
                        self._active_job["current_recipient"] = f"{recipient_name} (+{masked})"

                log_event(f"[{idx}/{total_items}] Dispatching to {recipient_name} (+{masked})...")

                # Dispatch attempt with bounded exponential backoff on transient errors
                attempt = 0
                dispatched_successfully = False
                last_error = ""

                while attempt <= max_retries:
                    if self._is_stopped:
                        break

                    try:
                        item_format = item.get("message_format") or "image_with_caption"
                        try:
                            res = provider.send_message(
                                phone=recipient_phone,
                                message=resolved_msg,
                                attachment_path=media_path if media_path else None,
                                message_format=item_format
                            )
                        except TypeError:
                            res = provider.send_message(
                                phone=recipient_phone,
                                message=resolved_msg,
                                attachment_path=media_path if media_path else None
                            )
                    except Exception as e:
                        res = {"status": "FAILED", "error": str(e)}

                    status = res.get("status")
                    if status == "SENT":
                        dispatched_successfully = True
                        db.update_queue_item_status(item["id"], "DISPATCHED")
                        db.record_job_result(
                            job_id=job_id,
                            name=recipient_name,
                            phone=recipient_phone,
                            status="SENT",
                            attachment=media_path
                        )
                        sent_count += 1
                        log_event(f"  -> Dispatched successfully to +{masked}")
                        break
                    elif status == "UNCERTAIN":
                        last_error = res.get("error") or "Transmission initiated but outcome unconfirmed"
                        db.update_queue_item_status(item["id"], "UNCERTAIN", error_message=last_error)
                        db.record_job_result(
                            job_id=job_id,
                            name=recipient_name,
                            phone=recipient_phone,
                            status="UNCERTAIN",
                            error=f"[UNCERTAIN] {last_error}",
                            attachment=media_path
                        )
                        failed_count += 1
                        log_event(f"  -> Transmission unconfirmed for +{masked}: marked UNCERTAIN to prevent duplicate send.", "WARNING")
                        break
                    else:
                        last_error = res.get("error") or "Transmission failed"
                        # Classify permanent vs transient failures
                        err_upper = last_error.upper()
                        is_permanent = any(kw in err_upper for kw in [
                            "INVALID", "NOT A VALID", "UNREGISTERED", "NOT ON WHATSAPP", "OPTED_OUT", "SUPPRESSED"
                        ])

                        if is_permanent or attempt >= max_retries:
                            final_st = "FAILED_PERMANENT" if is_permanent else "FAILED_MAX_RETRIES"
                            db.update_queue_item_status(item["id"], final_st, error_message=last_error, retry_count=attempt)
                            db.record_job_result(
                                job_id=job_id,
                                name=recipient_name,
                                phone=recipient_phone,
                                status="FAILED",
                                error=f"[{final_st}] {last_error}",
                                attachment=media_path
                            )
                            failed_count += 1
                            log_event(f"  -> Dispatch failed permanently: {last_error}", "WARNING")
                            break
                        else:
                            attempt += 1
                            # Exponential backoff with jitter: 2s, 4s, 8s... + jitter
                            backoff_secs = min(30.0, 2.0 * (2 ** (attempt - 1))) + random.uniform(0.5, 1.5)
                            db.update_queue_item_status(
                                item["id"],
                                "RETRYING",
                                error_message=f"{last_error} (Retry {attempt}/{max_retries} in {backoff_secs:.1f}s)",
                                retry_count=attempt
                            )
                            log_event(f"  -> Transient error ({last_error}). Retrying in {backoff_secs:.1f}s ({attempt}/{max_retries})...", "WARNING")
                            time.sleep(backoff_secs)

                # Update job progress in database and active state
                db.update_job_progress(job_id, sent_count, failed_count, f"{recipient_name} (+{masked})")
                with self._lock:
                    if self._active_job and self._active_job.get("id") == job_id:
                        self._active_job["sent_count"] = sent_count
                        self._active_job["failed_count"] = failed_count

                # Broadcast real-time progress update
                progress_pct = round((idx / total_items) * 100, 1) if total_items > 0 else 0
                self._broadcast({
                    "type": "job_progress",
                    "job_id": job_id,
                    "current": idx,
                    "total": total_items,
                    "percentage": progress_pct,
                    "sent": sent_count,
                    "failed": failed_count,
                    "contact": {
                        "name": recipient_name,
                        "phone": recipient_phone,
                        "status": "SENT" if dispatched_successfully else "FAILED",
                        "error": last_error
                    }
                })

                # Anti-ban pacing delay between recipients
                if idx < total_items and not self._is_stopped:
                    if not use_mock:
                        delay = random.uniform(min_delay, max_delay)
                        time.sleep(delay)
                    else:
                        # Fast mock pacing for testing responsiveness
                        time.sleep(0.05)

                    # Batch cooldown pause
                    if idx % batch_size == 0 and not use_mock:
                        log_event(f"Batch threshold ({batch_size}) reached. Cooling down for {batch_pause}s...", "INFO")
                        time.sleep(batch_pause)

            # Determine final state
            with self._lock:
                current_status = self._active_job.get("status") if self._active_job else "COMPLETED"

            final_status = "CANCELLED" if (self._is_stopped or current_status == "CANCELLED") else "COMPLETED"
            db.update_job_status(job_id, final_status)
            log_event(f"Job {job_id} concluded with status {final_status} (Sent: {sent_count}, Failed: {failed_count})", "INFO")

            with self._lock:
                if self._active_job and self._active_job.get("id") == job_id:
                    self._active_job["status"] = final_status

            self._broadcast({
                "type": "job_finished",
                "job_id": job_id,
                "status": final_status,
                "sent": sent_count,
                "failed": failed_count
            })

        except Exception as e:
            logger.error(f"Job {job_id} encountered fatal worker error: {e}")
            db.update_job_status(job_id, "FAILED", error_message=str(e))
            log_event(f"Job {job_id} failed fatally: {e}", "ERROR")
            with self._lock:
                if self._active_job and self._active_job.get("id") == job_id:
                    self._active_job["status"] = "FAILED"
                    self._active_job["error"] = str(e)
            self._broadcast({
                "type": "job_finished",
                "job_id": job_id,
                "status": "FAILED",
                "error": str(e)
            })

    def pause_job(self, job_id: str) -> bool:
        """Pauses the active job."""
        with self._lock:
            if not self._active_job or self._active_job.get("id") != job_id:
                return False
            if self._active_job.get("status") not in ("RUNNING", "WAITING_FOR_CONNECTION"):
                return False
            self._active_job["status"] = "PAUSED"
            self._is_paused = True
            if self._active_provider:
                self._active_provider.pause()
            db.update_job_status(job_id, "PAUSED")
            db.log_event("WARNING", "JobQueue", f"Job {job_id} paused by user")
            self._broadcast({"type": "job_paused", "job_id": job_id})
            return True

    def resume_job(self, job_id: str) -> bool:
        """Resumes a paused or connection-waiting job."""
        with self._lock:
            if not self._active_job or self._active_job.get("id") != job_id:
                return False
            cur_st = self._active_job.get("status")
            if cur_st not in ("PAUSED", "WAITING_FOR_CONNECTION"):
                return False

            self._active_job["status"] = "RUNNING"
            self._is_paused = False
            if self._active_provider:
                self._active_provider.resume()
            db.update_job_status(job_id, "RUNNING")
            db.log_event("INFO", "JobQueue", f"Job {job_id} resumed by user")
            self._broadcast({"type": "job_resumed", "job_id": job_id})

            if self._worker_args and (not self._worker_thread or not self._worker_thread.is_alive()):
                self._worker_thread = threading.Thread(
                    target=self._run_job_worker,
                    args=self._worker_args,
                    daemon=True,
                    name=f"JobWorker-{job_id}"
                )
                self._worker_thread.start()

            return True

    def cancel_job(self, job_id: str) -> bool:
        """Cancels an active or scheduled job immediately."""
        with self._lock:
            if not self._active_job or self._active_job.get("id") != job_id:
                return False
            self._is_stopped = True
            self._is_paused = False
            if self._schedule_timer:
                try:
                    self._schedule_timer.cancel()
                    self._schedule_timer = None
                except Exception:
                    pass
            self._active_job["status"] = "CANCELLED"
            if self._active_provider:
                self._active_provider.stop()
            db.update_job_status(job_id, "CANCELLED")
            db.log_event("WARNING", "JobQueue", f"Job {job_id} cancelled by user")
            self._broadcast({"type": "job_cancelled", "job_id": job_id})
            return True


# Global singleton background worker
job_worker = BackgroundJobWorker()
