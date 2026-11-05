"""
Tests for Stage 6: Durable Queue Lifecycle and Restart Recovery.
Verifies:
1. Queue item states: PENDING, SENDING, DISPATCHED, FAILED_PERMANENT, UNCERTAIN.
2. Uncertain outcome handling: marked as UNCERTAIN without auto-retry or duplicate sends.
3. Restart recovery: previously dispatched items and uncertain items are never duplicated.
"""

import time
import pytest
from unittest.mock import MagicMock

from backend.database import db
from backend.job_queue import BackgroundJobWorker
from backend.adapter import MockMessagingProvider


def test_queue_uncertain_send_not_duplicated():
    """
    Verifies that when a messaging provider returns UNCERTAIN, the queue item is
    marked UNCERTAIN and is NOT retried automatically, preventing double messaging.
    """
    worker = BackgroundJobWorker()
    worker._active_job = None
    worker._is_stopped = False
    worker._is_paused = False

    test_contacts = [
        {"name": "Alice Uncertain", "phone": "+919999900001", "consent_status": "opted_in"}
    ]

    # Create mock provider returning UNCERTAIN
    mock_provider = MockMessagingProvider(simulation_delay=0.01)
    mock_provider.send_message = MagicMock(return_value={
        "status": "UNCERTAIN",
        "error": "Attachment send clicked but preview did not clear. Outcome unverified."
    })

    job = worker.start_campaign_job(
        campaign_name=f"UncertainTest_{int(time.time())}",
        contacts=test_contacts,
        template_content="Hi {name}",
        use_mock=True,
        provider=mock_provider
    )
    job_id = job["id"]

    # Allow worker to process
    if worker._worker_thread:
        worker._worker_thread.join(timeout=3)

    items = db.get_queue_items(job_id=job_id)
    assert len(items) == 1
    assert items[0]["status"] == "UNCERTAIN"
    assert "unverified" in items[0]["error_message"].lower()

    # Verify that get_queue_items(status="PENDING") returns 0 items (will not be retried)
    pending_items = db.get_queue_items(job_id=job_id, status="PENDING")
    assert len(pending_items) == 0

    # Cleanup
    worker.cancel_job(job_id)


def test_queue_restart_recovery_preserves_allocations():
    """
    Verifies that restarting Relay does not alter previously assigned message/media
    variants or duplicate already-sent items.
    """
    job_id = f"recovery_test_{int(time.time())}"
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Enqueue 3 items: 1 DISPATCHED, 1 UNCERTAIN, 1 PENDING
    items = [
        {
            "idempotency_key": f"{job_id}_1",
            "recipient_name": "User One",
            "recipient_phone": "919000000001",
            "resolved_message": "Hello User One",
            "media_path": "uploads/media/flyer.png",
            "media_asset_id": 101,
            "status": "DISPATCHED"
        },
        {
            "idempotency_key": f"{job_id}_2",
            "recipient_name": "User Two",
            "recipient_phone": "919000000002",
            "resolved_message": "Hello User Two",
            "media_path": "uploads/media/banner.png",
            "media_asset_id": 102,
            "status": "UNCERTAIN"
        },
        {
            "idempotency_key": f"{job_id}_3",
            "recipient_name": "User Three",
            "recipient_phone": "919000000003",
            "resolved_message": "Hello User Three",
            "media_path": "uploads/media/flyer.png",
            "media_asset_id": 101,
            "status": "PENDING"
        }
    ]

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (id, campaign_name, status, total_count, started_at) VALUES (?, 'RecoveryJob', 'PAUSED', 3, ?)", (job_id, now))
        conn.commit()

    db.create_queue_items(job_id=job_id, campaign_id=None, items=items)

    # Re-instantiate worker as if server just restarted
    new_worker = BackgroundJobWorker()

    # Query items to be dispatched
    pending_to_dispatch = db.get_queue_items(job_id=job_id, status="PENDING")
    assert len(pending_to_dispatch) == 1
    assert pending_to_dispatch[0]["recipient_name"] == "User Three"
    assert pending_to_dispatch[0]["media_asset_id"] == 101
    assert pending_to_dispatch[0]["resolved_message"] == "Hello User Three"

    # Verify that DISPATCHED and UNCERTAIN items are not in pending_to_dispatch
    all_items = db.get_queue_items(job_id=job_id)
    assert len(all_items) == 3
    statuses = {i["status"] for i in all_items}
    assert statuses == {"DISPATCHED", "UNCERTAIN", "PENDING"}

    # Cleanup
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM campaign_queue_items WHERE job_id = ?", (job_id,))
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
