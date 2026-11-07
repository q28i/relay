# Relay Testing & Quality Verification Framework

This document details Relay's automated test suite, isolation architectures, regression fixtures, reproduction procedures for the historical sticker defect, and manual verification protocols.

---

## 1. Automated Test Suite Architecture

Relay maintains an automated test suite executed via `pytest`. The suite runs in approximately 2.5 minutes without requiring an active internet connection or live WhatsApp credentials.

**Last Verified Automated Test Suite Result**:
- **Total Tests Collected**: 236
- **Total Tests Passed**: **236** (100% Green)
- **Total Failures**: 0
- **Duration**: ~149.0s

### 1.1 Test Suite Breakdown
| Test Module | Test Count | Scope & Focus |
|---|---|---|
| `tests/test_api.py` | 40 | FastAPI REST endpoints, schema validation, error response codes. |
| `tests/test_browser_conflict_resolution.py` | 10 | Profile diagnosis, Relay-owned PID termination, personal browser prompts. |
| `tests/test_media_delivery_verification.py` | 25 | Sticker input rejection, modal-scoped captions, zero silent drops, dispatch locks. |
| `tests/test_visible_vs_background_and_preview_stuck.py` | 19 | Headed vs headless layouts, stuck preview timeouts, uncertain outcome pauses. |
| `tests/test_dispatch_reliability_and_partial_sends.py` | 14 | Partial send recovery (`retry_text_only`), Spintax, variable interpolation. |
| `tests/test_media_sending_and_session.py` | 14 | Dynamic file input classification, media format routing, session health. |
| `tests/test_contacts_and_campaigns_real.py` | 15 | CSV/XLSX contact imports, phone normalization, campaign allocations. |
| `tests/test_profile_persistence_and_states.py` | 8 | Persistent profile settings, config saving, dedicated session recovery. |
| `tests/test_profile_lock_and_launch.py` | 7 | Chromium 136+ detection, lockfile handling, stale lock cleanup. |
| `tests/test_stage1_contacts_clean.py` | 7 | International phone validation, cleaning, and suppression rules. |
| `tests/test_unified_templates_workflow.py` | 6 | Template variants, Spintax resolution, preview assignments. |
| `tests/test_spintax.py` | 6 | Deep nested Spintax randomness, deterministic parsing. |
| `tests/test_config_manager.py` | 5 | Configuration backup, restoration, and preset management. |
| `tests/test_updater.py` | 5 | Remote release checks, version comparisons. |
| `tests/test_validator.py` | 5 | Contact list validation, deduplication. |
| `tests/test_device_manager.py` | 4 | Windows hardware fingerprinting and licensing roles. |
| `tests/test_stage6_queue_and_recovery.py` | 2 | Durable queue recovery, idempotency key uniqueness. |
| `tests/test_stage5_campaign_allocation.py` | 2 | Media-to-contact assignment algorithms. |
| `tests/test_stage3_library_and_collections.py` | 2 | Content set and collection persistence. |
| `tests/test_connection_monitoring.py` | 9 | Connection state transitions, timeline updates. |
| `tests/test_data_loader.py` | 8 | Excel/CSV spreadsheet parsing routines. |
| `tests/test_logger.py` | 3 | Log event formatting, database logging. |
| `tests/test_engine_sleep.py` | 2 | Interruptible sleep routines. |
| `tests/test_gui_integration.py` | 2 | Desktop GUI launcher routines. |

---

## 2. Test Isolation & Fixtures

1. **Database Isolation**:
   Tests execute against in-memory SQLite instances or isolated temporary databases created in `pytest` fixtures, ensuring tests never overwrite production user databases.
2. **Mock WebDrivers**:
   Low-level Selenium interactions are tested using `MockWebDriver` and `MagicMock` instances that simulate the WhatsApp Web DOM tree without opening real browser windows.
3. **Dispatch Mutex Verification**:
   Tests like `test_22_connection_monitor_yields_when_dispatch_lock_is_held` explicitly acquire `_session_dispatch_lock` and confirm that the background monitor yields without invoking WebDriver methods.

---

## 3. How to Reproduce and Verify the Sticker Defect Safely

### 3.1 Simulated Defect (Unit Test Level)
To verify that the engine rejects sticker inputs, inspect `test_17_sticker_maker_input_rejected_for_photos` in `tests/test_media_delivery_verification.py`:
1. Provide a mock input having `accept="image/*"` (without video).
2. Invoke `engine._send_attachment_flow()`.
3. Verify that Relay logs a warning and refuses to deliver files to the sticker input.

### 3.2 Live DOM Non-Sending Verification
Relay exposes a safe verification endpoint (`POST /api/browser/test-preview-non-sending`) that tests the entire browser pipeline without transmitting any message:
```bash
curl -X POST http://127.0.0.1:8000/api/browser/test-preview-non-sending \
  -H "Content-Type: application/json" \
  -d '{"phone": "917622029755", "caption": "123 automation check", "media_path": "uploads/media/asset_8fc9cb1019.jpg"}'
```
**Verification Evidence Returned**:
- `input_accept`: Confirms `accept` includes `video/mp4`, etc.
- `is_sticker_input`: `false`
- `caption_rendered`: Confirms `123 automation check` is physically present.
- `closest_footer_is_null`: `true`
- `preview_dismissed`: `true`
- `transmitted`: `false` (Zero chat bubbles dispatched).

---

## 4. Evidence Analysis: User's Latest Live Screenshot

The latest user screenshot provides empirical evidence of the working baseline:
- **Campaign Counter**: Reports 3 of 3 recipient tasks completed successfully.
- **Visual Presentation**: The chat history shows a standard photographic image bubble (not a circular or transparent sticker thumbnail).
- **Caption Binding**: The caption `123 automation check` is attached directly to the photo inside the media bubble.
- **Multi-Recipient Continuity**: The campaign processed all 3 selected contacts without pausing or halting on recipient 1.

> [!NOTE]
> Campaign counters confirm queue worker progress. Conclusive delivery verification requires inspecting chat bubbles or delivery checkmarks. In the user's latest test, both the counter and the chat bubble display confirm delivery.

---

## 5. Future Regression Testing Checklist

Before deploying any future modifications to Relay, verify the following checklist:

- [ ] Run full test suite: `pytest` must report **236 passed, 0 failed**.
- [ ] Confirm `browser_manager.py` resolves cached chromedriver in < 3 seconds.
- [ ] Execute `POST /api/browser/test-preview-non-sending`:
  - [ ] Verify `is_sticker_input == False`.
  - [ ] Verify `closest_footer_is_null == True`.
  - [ ] Verify `caption_rendered` matches input text.
  - [ ] Verify preview is dismissed cleanly without sending.
- [ ] Verify `RECONCILIATION_REQUIRED` state transitions when uncertain sends occur.
- [ ] Verify that `_session_dispatch_lock` yields observation worker during send operations.
- [ ] Verify that permanent failures (invalid numbers) advance the queue without retrying.
