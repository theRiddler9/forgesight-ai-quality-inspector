# ForgeSight Stage 2 Software Architecture

**Owner:** Riya with Akash as co-lead  
**First delivery:** Recorded-image vertical slice with mock model and mock I/O  
**Hardware rule:** No Orange Pi, camera, GPIO, or RKNN dependency is required for the first slice

## Objective

Prove the complete audit path before training or hardware integration:

```text
recorded image
  -> frame source
  -> deterministic checks
  -> detector result
  -> PASS / FAIL / RECHECK decision
  -> mock outputs
  -> canonical inspection event
  -> SQLite
  -> FastAPI + WebSocket
  -> operator HMI
```

Later camera, RKNN, and GPIO adapters replace mocks without changing the decision, event, backend, or HMI contracts.

## Component Boundaries

| Component | Responsibility | Must not own |
|---|---|---|
| Frame source | Produce validated frame packets | Poka-Yoke or decisions |
| Preprocessor | Normalize and prepare image data | Camera lifecycle or thresholds |
| Poka-Yoke engine | Deterministic part and geometry checks | Learned defect classification |
| Detector adapter | Return defect candidates and confidence | Final PASS/FAIL policy |
| Decision engine | Combine rules, detections, faults, and thresholds | GPIO library calls or persistence |
| I/O adapter | Translate logical states to mock/hardware outputs | Inspection policy |
| Event builder | Emit schema-compliant audit events | Database or WebSocket transport |
| Repository | Persist and query events in SQLite | Decision logic |
| API service | Expose health, history, review, and replay operations | Vision algorithms |
| Event stream | Publish committed inspection events | Creating or modifying events |
| HMI | Present state and collect review actions | Recomputing inspection decisions |

## Planned Source Layout

```text
software/
  pyproject.toml
  src/
    forgesight/
      contracts/
      vision/
      edge/
      backend/
  tests/
    contracts/
    vision/
    edge/
    backend/
    acceptance/
  frontend/
    src/
    tests/
  fixtures/
    images/
    scenarios/
  contracts/
```

Each Python area is independently testable inside one installable `forgesight` package. Shared data structures live in the `contracts` subpackage rather than being copied between services.

## Decision Precedence

Evaluate in this order; the first matching rule wins:

1. Pipeline, camera, stale-frame, timeout, or I/O fault -> `RECHECK`.
2. Missing/invalid part or insufficient image quality -> `RECHECK`.
3. Definitive Poka-Yoke defect, such as a required hole missing -> `FAIL`.
4. Detector confidence at or above the configured fail threshold -> `FAIL`.
5. Detector confidence inside the uncertainty band -> `RECHECK`.
6. All required checks pass and no defect reaches the uncertainty band -> `PASS`.

Threshold values remain configuration until model evaluation freezes them.

## Initial API Surface

| Method and path | Purpose |
|---|---|
| `GET /api/v1/health` | Service, database, model-adapter, frame-source, and I/O health |
| `POST /api/v1/inspections/replay` | Run one named recorded scenario |
| `GET /api/v1/inspections` | Paginated audit history |
| `GET /api/v1/inspections/{event_id}` | One canonical event |
| `POST /api/v1/inspections/{event_id}/review` | Confirm or correct an operator-reviewable result |
| `GET /api/v1/metrics/summary` | Counts, yield, result distribution, and latency summary |
| `WS /ws/inspections` | Publish committed inspection events and health changes |

An inspection event is published only after its SQLite transaction commits.

## Persistence Rules

- `event_id` is the idempotency key and primary identifier.
- Store the canonical event without discarding raw fields needed for audit.
- Operator review updates are append-auditable: reviewer, time, old value, new value, and note.
- Store image references and checksums, not unbounded image blobs in SQLite.
- Schema migrations are versioned and tested from an empty database.

## Error and Safety Behavior

- No exception or missing dependency may default to PASS.
- A failed database commit prevents event publication and returns a service fault.
- A WebSocket failure does not lose a committed audit event; the HMI can recover through history.
- The I/O adapter enters the logical safe state during startup, fault, shutdown, and unhandled exceptions.
- The HMI shows disconnected or stale state explicitly; it does not keep showing an old PASS as current.

## First Vertical-Slice Scenarios

| Scenario | Poka-Yoke | Detector | Expected result | Output state |
|---|---|---|---|---|
| `clean_part` | All checks pass | No heavy burr | PASS | Green |
| `heavy_burr` | All checks pass | Above fail threshold | FAIL | Red plus configured buzzer pulse |
| `uncertain_burr` | All checks pass | Inside uncertainty band | RECHECK | Amber |
| `missing_hole` | Required hole absent | Not evaluated | FAIL | Red plus configured buzzer pulse |
| `no_part` | Part absent | Not evaluated | RECHECK | Amber |
| `capture_fault` | Not evaluated | Not evaluated | RECHECK with fault | Amber/safe state |

## Vertical-Slice Acceptance Test

For each scenario above, an automated acceptance test must prove:

1. The scenario produces the expected decision and reason.
2. The mock I/O adapter records the expected complete output state.
3. Exactly one event validates against `inspection-event.schema.json`.
4. Exactly one matching row commits to a temporary SQLite database.
5. The event returned by the API is semantically identical to the stored event.
6. The WebSocket receives the committed event once, after persistence.
7. The HMI renders the matching result, reason, latency, and connectivity state.
8. Replaying the same `event_id` does not create a duplicate audit record.

The first slice is complete only when all six scenarios pass from a clean checkout without camera, NPU, or GPIO hardware.

## Evidence Produced by the Slice

- Automated test report.
- Example SQLite database generated from fixtures.
- API schema and example responses.
- WebSocket event capture.
- HMI screenshots for PASS, FAIL, RECHECK, and disconnected/fault states.
- Timing log clearly labeled as development-machine virtual evidence, not Orange Pi performance.
