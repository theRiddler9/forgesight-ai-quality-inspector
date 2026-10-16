# Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build the backend's independent SQLite audit store, read-only REST API, system status calculation, and bounded WebSocket client manager without deciding how edge events reach the backend.

**Architecture:** Keep SQLite access in a small repository that opens one connection per worker-thread operation. FastAPI read routes use that repository; system status combines the latest stored telemetry with `psutil` system RAM. A separate WebSocket manager isolates each client with a bounded queue and send timeout. No event-file reader or edge handoff is included.

**Tech Stack:** Python, FastAPI, `uvicorn[standard]`, SQLite, Pydantic v2 shared schemas, `psutil`, pytest, httpx, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-10-16-backend-audit-api-design.md`

## Global Constraints

- Use shared models from `software/common/schemas.py`; do not duplicate them.
- Bind the service to `127.0.0.1:8000` by default and keep it local-only.
- Use SQLite WAL mode, a busy timeout, and one connection per worker-thread operation.
- Keep audit records append-only with database triggers; do not describe the log as tamper-proof.
- History ordering is `timestamp DESC, rowid DESC`.
- `system/status` reports system RAM, converts `soc_temp_c == -1.0` to null with a null timestamp, and counts only inspection results in the five-second rate.
- Slow or disconnected WebSocket clients must not block ingestion or other clients.
- JSONL handoff selection, JSONL tailing, and handoff-dependent lifespan wiring are explicitly out of scope until Riya approves section 7 of `software/CONTRACT.md`.
- Do not alter existing CAD/KiCad user changes.

## Review Focus

- Empty database latest/history/status responses remain valid and do not fabricate inspections; test empty-store API responses.
- Equal timestamps and out-of-order event insertion produce deterministic history ordering; test `rowid DESC` tie breaking.
- The telemetry sentinel and old sample timestamp do not appear as a valid current temperature; test `-1.0` becomes null and sample time is preserved for valid readings.
- A full or stalled WebSocket client cannot block broadcasts; test queue overflow eviction and send timeout.
- Windows cannot import `resource`; test status through `psutil` system memory on supported platforms.

---

### Task 1: Backend package and dependencies

**Files:**
- Create: `software/backend/__init__.py`
- Modify: `software/requirements.txt`
- Modify: `software/requirements-dev.txt`

**Interfaces:**
- Runtime dependencies expose FastAPI, WebSocket-capable `uvicorn[standard]`, and `psutil`.
- Development dependencies expose `httpx` and `pytest-asyncio` alongside existing requirements.

- [x] Add the runtime and development dependencies with compatible minimum versions.
- [x] Confirm the dependency files still include the existing edge runtime and test requirements.

### Task 2: SQLite audit repository

**Files:**
- Create: `software/backend/database.py`
- Test: `software/backend/tests/test_database.py`

**Interfaces:**
- `AuditStore(db_path: str | Path)` initializes schema and opens/closes a new SQLite connection per operation.
- `AuditStore.append_event(event: str, data: InspectionResult | WatchdogAlert) -> bool` inserts a canonical envelope idempotently and returns whether it was new.
- `AuditStore.latest_inspection() -> InspectionResult | None`.
- `AuditStore.inspection_history(result: InspectionDecision | None, limit: int, offset: int) -> tuple[list[InspectionResult], int]`.
- `AuditStore.status_snapshot(now: datetime) -> dict[str, object]` supplies telemetry-only values; system RAM is added at the API layer.

- [x] Test schema initialization, WAL mode, append-only triggers, and duplicate event keys.
- [x] Test shared-model serialization/deserialization for inspection and watchdog envelopes.
- [x] Test latest empty/non-empty behavior and history filters, pagination, and timestamp ties.
- [x] Implement the repository using parameterized SQL, explicit event-type columns, canonical JSON SHA-256 keys, and a configurable SQLite busy timeout.
- [x] Keep this repository independent of any edge event transport.

### Task 3: Read-only REST API and system status

**Files:**
- Create: `software/backend/config.py`
- Create: `software/backend/app.py`
- Test: `software/backend/tests/test_api.py`
- Modify: `software/CONTRACT.md`

**Interfaces:**
- `create_app(db_path: str | Path | None = None) -> FastAPI` constructs the local API and initializes the store in lifespan.
- `GET /health -> {status: str, uptime_seconds: float}`.
- `GET /api/v1/inspections/latest -> InspectionResult | null`.
- `GET /api/v1/inspections/history -> {items, total, limit, offset}` with optional result filter, limit 1–500 (default 50), offset >= 0 (default 0).
- `GET /api/v1/system/status -> {soc_temp_c, soc_temp_timestamp, ram_used_mb, ram_total_mb, fps, avg_latency_ms}`.

- [x] Test exact response shapes, input bounds, local CORS for `http://localhost:5173`, and empty-store results.
- [x] Test `soc_temp_c == -1.0` maps both temperature and timestamp to null; valid readings preserve the inspection timestamp.
- [x] Test FPS counts only `inspection_result` events over the previous five seconds and average latency uses at most the newest 100.
- [x] Implement Pydantic response models, `psutil.virtual_memory()` metrics, monotonic uptime, parameter validation, and `asyncio.to_thread` calls for repository operations.
- [x] Add backend v1 response bodies to section 6 of `software/CONTRACT.md`; leave section 7 explicitly proposed pending Riya's approval.

### Task 4: Isolated live WebSocket manager

**Files:**
- Create: `software/backend/websocket.py`
- Modify: `software/backend/app.py`
- Test: `software/backend/tests/test_websocket.py`

**Interfaces:**
- `WebSocketHub(queue_size: int = 32, send_timeout_seconds: float = 2.0)` manages connected clients.
- `publish(envelope: dict[str, object]) -> None` enqueues without awaiting client sends; overflow evicts that client.
- `/ws/live` registers one client, sends queued envelopes independently, and unregisters on disconnect or timeout.

- [x] Test fanout to multiple clients and normal disconnect cleanup.
- [x] Test bounded queue overflow and per-send timeout remove only the slow client.
- [x] Implement per-client sender tasks and ensure no client send runs in the publisher's call path.

### Task 5: Verification boundary and handoff stop point

**Files:**
- No JSONL tailer or edge runtime changes in this plan.

**Interfaces:**
- The eventual ingestion task may call `AuditStore.append_event(...)` and `WebSocketHub.publish(...)` after it reads a contract-approved event.

- [x] Run `pytest software/backend/tests -q` and `git diff --check` after the independent implementation is complete.
- [x] Stop before adding the event-file tailer, its error recorder, or lifespan wiring that starts it; resume only after Riya approves the section 7 JSONL handoff decision.
- [x] Do not claim edge-to-backend integration until the handoff-dependent work is implemented and verified.

