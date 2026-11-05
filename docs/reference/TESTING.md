# Testing and Quality Assurance Strategy

This document outlines the testing architecture, test suites, coverage breakdown, regression prevention gates, and instructions for verifying the WhatsApp Bulk Messenger Pro platform.

---

## 1. Test Strategy Overview

The testing strategy follows a pyramid approach balancing fast in-memory unit tests with realistic HTTP integration tests:
1. **Domain Unit Tests:** Validate phone cleaning regex, Spintax recursion, config bounds checking, and device identification without external I/O.
2. **Pre-Flight & Simulation Tests:** Verify duplicate detection, campaign duration estimation, and in-memory dry-run execution.
3. **API Integration Tests:** Exercise all FastAPI REST endpoints, JSON error envelopes, file uploads, and background worker state transitions using `TestClient`.
4. **Mock Provider Simulation:** Test end-to-end background campaign execution and WebSocket telemetry without requiring Google Chrome or network calls.

---

## 2. Test Suites Summary

The automated test suite contains **61 tests** across 11 test modules with a **100% pass rate**.

| Test Module | Test Focus | Test Count | Pass Rate | Execution Time |
| :--- | :--- | :--- | :--- | :--- |
| `tests/test_api.py` | FastAPI REST routes, Static files, Contacts, Templates, Campaigns, Jobs, Presets | 21 | 100% | ~0.98s |
| `tests/test_config_manager.py` | AppConfig typed schema, preset application, validation bounds, serialization | 5 | 100% | ~0.08s |
| `tests/test_data_loader.py` | E.164 phone cleaning, column synonyms, CSV/Excel loading, variable substitution | 8 | 100% | ~0.12s |
| `tests/test_device_manager.py` | Hardware fingerprinting, short ID generation, developer flags, telemetry caching | 4 | 100% | ~0.06s |
| `tests/test_engine_sleep.py` | Interruptible sleep mechanism, responsive pause/cancel behavior | 2 | 100% | ~0.15s |
| `tests/test_gui_integration.py` | Backward compatibility binding with legacy desktop Tkinter components | 2 | 100% | ~0.09s |
| `tests/test_logger.py` | Phone number privacy masking (`mask_phone()`), rotating file logger singleton | 3 | 100% | ~0.04s |
| `tests/test_spintax.py` | Recursive `{A\|B\|C}` Spintax evaluation, nested variations, token preservation | 6 | 100% | ~0.05s |
| `tests/test_updater.py` | Semantic version parsing, update manifest resolution, version comparisons | 5 | 100% | ~0.06s |
| `tests/test_validator.py` | Pre-flight contact list audit, duplicate tracking, dry-run simulation engine | 5 | 100% | ~0.16s |
| **Total** | **Full Automated Test Suite** | **61** | **100%** | **~1.79s** |

---

## 3. How to Run Tests

### 3.1 Execute Full Test Suite
From the project root:
```bash
pytest -v
```

### 3.2 Run Specific Test Suites
```bash
# Run Web API endpoints tests
pytest tests/test_api.py -v

# Run Pre-flight validator and simulation tests
pytest tests/test_validator.py -v

# Run Anti-ban configuration and preset tests
pytest tests/test_config_manager.py -v

# Run Spintax evaluation tests
pytest tests/test_spintax.py -v
```

### 3.3 Test with Coverage
```bash
pytest --cov=backend --cov=. tests/
```

---

## 4. Key Verification Scenarios

### 4.1 Phone Number Normalization
- Normalizes international numbers: `+1 (415) 555-2671` -> `14155552671`.
- Appends default country code: `09876543210` with default code `91` -> `919876543210`.
- Rejects invalid phone numbers: `not-a-number`, empty strings, numbers with <10 digits.

### 4.2 Configuration Bounds Validation
- Enforces `min_delay >= 1.0` seconds.
- Rejects `max_delay < min_delay` with HTTP 422.
- Enforces `batch_size >= 1`, `batch_pause >= 5.0` seconds.

### 4.3 Background Job Worker State Transitions
- Verifies transition: `QUEUED` -> `RUNNING` -> `PAUSED` -> `RESUMED` -> `COMPLETED`.
- Proves thread-safe cancellation stops active dispatch loops immediately via `_interruptible_sleep`.
- Confirms results are recorded in SQLite and exportable to CSV.

### 4.4 Spintax Evaluation Safety
- Evaluates `{Hi|Hello|Hey}` into randomized greeting variations.
- Does not corrupt template tags like `{name}` or `{phone}` which lack pipe (`|`) delimiters.

---

## 5. Continuous Quality & Regression Checklist

Before committing or releasing new changes:
- [x] Run `pytest -v` and confirm 100% pass rate across all 61 tests.
- [x] Verify API docs load at `http://127.0.0.1:8000/api/docs`.
- [x] Verify frontend loads at `http://127.0.0.1:8000/`.
- [x] Verify WebSocket connects and displays "WS Live" in sidebar footer.
- [x] Verify CLI operations (`python run.py --dry-run`) execute without errors.

