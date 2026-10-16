# ForgeSight Local Backend Audit and API Design

## Goal

Add a local FastAPI service that consumes the edge runtime's JSONL event stream, stores validated inspection and watchdog events in an append-only SQLite audit log, serves read APIs, and broadcasts new events over `/ws/live`.

## Project context

Stage 2 is virtual validation. The backend must run locally, use the shared types in `software/common/schemas.py`, and leave inspection decisions in the edge decision engine. The team roles and goals assign backend/HMI jointly to Akash and Riya and require local SQLite audit logging, WebSocket telemetry, and the documented inspection history APIs.

## Selected handoff

Use the existing JSONL sink as the edge-to-backend handoff. Each complete JSONL line is already a WebSocket envelope: `{"event":"inspection_result","data":{...}}` or `{"event":"watchdog_alert","data":{...}}`. The backend tails this file; it does not call the edge pipeline in-process and does not add a new edge HTTP client or route.

The implementation will record this choice in section 7 of `software/CONTRACT.md`. It will not change `InspectionResult`, `WatchdogAlert`, or `software/schema.json`.

## Architecture and data flow

1. FastAPI lifespan initializes the SQLite database, then starts one asynchronous JSONL tailer task.
2. The tailer reads newline-terminated records incrementally, buffers a partial final line, validates known event payloads using shared Pydantic models, and appends valid events to SQLite.
3. After a new event commits, the service broadcasts the original envelope to connected `/ws/live` clients. Replayed or duplicate events are not rebroadcast.
4. REST handlers read the same SQLite store. No API handler computes or changes PASS/FAIL/RECHECK.
5. On shutdown, FastAPI stops and awaits the tailer before closing database resources.

The event file and database paths are configurable with `FORGESIGHT_EDGE_EVENTS_PATH` and `FORGESIGHT_DB_PATH`. Defaults are `data/events.jsonl` and `data/audit.sqlite3` relative to the project root. The service binds to `127.0.0.1:8000` by default and has no cloud dependency.

## SQLite audit store

Create an `audit_events` table with a stable event key, event type, event timestamp, nullable indexed inspection fields, and the complete validated JSON envelope. Inspection rows include inspection ID, result, defect type, confidence, SoC temperature, and total latency. Watchdog rows retain the complete `WatchdogAlert` payload.

Use SHA-256 over canonical JSON for the event key so replaying the same line after restart is idempotent. Add indexes for timestamp, result, and event type. Add SQLite triggers that reject UPDATE and DELETE on `audit_events`; the application exposes no mutation or deletion route for audit events.

Malformed JSON, unsupported event types, and schema-invalid payloads must not stop tailing. Record each invalid line's file offset, raw text, and reason in an `ingestion_errors` table and continue with the next complete line. If the event file is truncated or replaced, detect the size/identity change and restart reading at byte zero; unique event keys prevent replay duplicates.

## REST API

- `GET /health`: return `status` and service uptime.
- `GET /api/v1/inspections/latest`: return the most recent `InspectionResult`, or JSON `null` when empty.
- `GET /api/v1/inspections/history`: accept optional `result`, `limit` (default 50, range 1–500), and `offset` (default 0, minimum 0). Return items in newest-first order with total count, limit, and offset.
- `GET /api/v1/system/status`: return latest SoC temperature (nullable), process RAM in MiB, recent inspection rate (events in the preceding 5 seconds divided by 5), and mean total latency over the latest 100 inspections (nullable when empty).

Perform SQLite work without blocking the asyncio event loop. Return validation errors as HTTP 422 and unavailable database/service errors as HTTP 503; never fabricate inspection records to fill an empty result.

## WebSocket

`/ws/live` sends the exact envelope received from the edge after its database commit. V1 supports `inspection_result` and `watchdog_alert`. Client disconnects must not terminate ingestion or affect other connected clients. `inspection_frame` remains unsupported until the edge runtime publishes that event; no raw camera stream is added in this work.

## Scope boundaries

Included: local FastAPI app, JSONL tailing, schema validation, SQLite append-only audit and ingestion-error tables, the read routes above, `/ws/live`, configuration, and tests.

Deferred: React HMI; operator review and retraining-data writes; threshold/brightness POST settings; bidirectional edge control; live JPEG frame streaming; RKNN inference and physical hardware. The settings route needs a defined backend-to-edge control path; the operator review route needs a request body and label/image storage contract. These are not silently stubbed as successful operations.

## Dependencies and verification

Add FastAPI and Uvicorn as backend runtime dependencies; use the standard-library SQLite driver and async thread offloading for short database operations. Keep the existing OpenCV and NumPy edge dependencies unchanged.

Tests use temporary SQLite databases and JSONL files. Cover payload validation, partial lines, replay/idempotency, truncation, invalid-line recovery, append-only enforcement, history filters and pagination, empty-store responses, WebSocket fanout/disconnects, and lifespan cleanup. No RKNN latency, hardware GPIO, thermal, or defect-recall claims follow from these tests.
