# Recorded-Image Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hardware-independent vertical slice that replays six inspection scenarios through decision logic, mock I/O, SQLite, FastAPI/WebSocket, and the operator HMI.

**Architecture:** One installable Python package contains contracts, vision adapters, edge orchestration, and backend services behind narrow interfaces. A separate React/Vite frontend consumes only the versioned HTTP and WebSocket contracts. Camera, detector, and GPIO behavior remain injected mocks until their physical interfaces are approved.

**Tech Stack:** Python 3.10+, pytest, Pydantic 2, jsonschema, OpenCV headless, FastAPI, SQLite, React, TypeScript, Vite, Vitest, Testing Library.

**Spec:** `system/software-architecture.md`

## Global Constraints

- No Orange Pi, camera, GPIO, or RKNN dependency is required for this slice.
- No fault, exception, missing part, stale frame, or uncertainty may produce PASS.
- Every event must validate against `software/contracts/inspection-event.schema.json`.
- Persist each event before publishing it; publication failure must not erase the audit record.
- `event_id` is idempotent and may create at most one database record.
- Keep thresholds, paths, and timings in injected configuration.
- Implement and verify one behavior at a time using RED-GREEN-REFACTOR.
- Make one small verified commit per task.

## Review Focus

- A corrupt or unreadable scenario/image returns RECHECK or a typed request error and never creates PASS.
- A database write failure publishes no WebSocket event and requests the logical safe state.
- Reusing an `event_id` creates no duplicate row or duplicate live event.
- A disconnected HMI visibly reports stale/disconnected state and recovers history after reconnect.
- Invalid operator-review transitions are rejected without altering the original audit event.

---

### Task 1: Python Workspace and Contract Validation

**Files:**
- Create: `software/pyproject.toml`
- Create: `software/src/forgesight/__init__.py`
- Create: `software/src/forgesight/contracts/__init__.py`
- Create: `software/src/forgesight/contracts/events.py`
- Create: `software/tests/contracts/test_events.py`

**Interfaces:**
- Consumes: `software/contracts/inspection-event.schema.json`
- Produces: `load_event_schema() -> dict[str, object]`, `validate_inspection_event(event: Mapping[str, object]) -> None`, and `canonical_event_json(event: Mapping[str, object]) -> str`

- [ ] **Step 1: Write failing contract tests**

Add tests named `test_example_event_validates`, `test_missing_required_field_is_rejected`, `test_unknown_field_is_rejected`, and `test_canonical_json_is_stable` using the committed example event.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest software/tests/contracts/test_events.py -v`  
Expected: collection fails because `forgesight.contracts.events` does not exist.

- [ ] **Step 3: Add the Python project and minimal contract implementation**

Resolve the schema path relative to the repository, validate with Draft 2020-12, and serialize with sorted keys and compact separators.

- [ ] **Step 4: Install the editable Python workspace**

Run: `python -m pip install -e "software[dev]"`  
Expected: the `forgesight` package and pinned development dependencies install successfully.

- [ ] **Step 5: Run the focused and full Python suites**

Run: `python -m pytest software/tests/contracts/test_events.py -v`  
Expected: 4 passed.  
Run: `python -m pytest software/tests -q`  
Expected: all tests passed.

- [ ] **Step 6: Commit**

```text
R0: validate canonical inspection events
```

### Task 2: Recorded Frame and Scenario Replay

**Files:**
- Create: `software/src/forgesight/vision/__init__.py`
- Create: `software/src/forgesight/vision/frames.py`
- Create: `software/src/forgesight/vision/replay.py`
- Create: `software/fixtures/scenarios/*.json`
- Create: `software/fixtures/images/*.png`
- Create: `software/tests/vision/test_replay.py`

**Interfaces:**
- Consumes: scenario names and recorded image paths
- Produces: `FramePacket`, `ReplayScenario`, and `DirectoryReplaySource.capture(scenario_name: str) -> tuple[FramePacket, ReplayScenario]`

- [ ] **Step 1: Write failing replay tests**

Cover deterministic sequence numbers, BGR8 image loading, missing scenario, unreadable image, wrong image dimensions, and repeated capture producing a fresh frame ID.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest software/tests/vision/test_replay.py -v`  
Expected: collection fails because the vision modules do not exist.

- [ ] **Step 3: Implement the minimal replay source**

Use immutable dataclasses. Reject invalid files with typed `ReplaySourceError` fault codes from `camera-interface.md`.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m pytest software/tests/vision/test_replay.py -v`  
Expected: all replay tests passed.  
Run: `python -m pytest software/tests -q`  
Expected: all tests passed.

- [ ] **Step 5: Commit**

```text
R0: add deterministic recorded-image replay
```

### Task 3: Decision Engine

**Files:**
- Create: `software/src/forgesight/edge/__init__.py`
- Create: `software/src/forgesight/edge/decision.py`
- Create: `software/tests/edge/test_decision.py`

**Interfaces:**
- Consumes: `PokaYokeResult`, `Sequence[Detection]`, `Sequence[str]` faults, and `DecisionConfig`
- Produces: `decide(...) -> InspectionDecision` using the precedence in the spec

- [ ] **Step 1: Write one failing parameterized decision test**

Cover `clean_part`, `heavy_burr`, `uncertain_burr`, `missing_hole`, `no_part`, and `capture_fault`, plus the boundaries exactly equal to both configured thresholds.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest software/tests/edge/test_decision.py -v`  
Expected: collection fails because `forgesight.edge.decision` does not exist.

- [ ] **Step 3: Implement immutable result types and `decide`**

Return one result, ordered reason codes, and normalized defect records. Stop at the first precedence class but retain all reasons within that class.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m pytest software/tests/edge/test_decision.py -v`  
Expected: all decision cases passed.  
Run: `python -m pytest software/tests -q`  
Expected: all tests passed.

- [ ] **Step 5: Commit**

```text
R0: implement safe inspection decisions
```

### Task 4: Mock I/O and Safe State

**Files:**
- Create: `software/src/forgesight/edge/io.py`
- Create: `software/tests/edge/test_io.py`

**Interfaces:**
- Consumes: `InspectionDecision`
- Produces: `OutputState`, `output_for_decision(decision) -> OutputState`, and `MockIOAdapter` with `start`, `write_outputs`, `safe`, `health`, and `close`

- [ ] **Step 1: Write failing I/O tests**

Assert complete output states for PASS, FAIL, and RECHECK; startup/fault/close never assert green; repeated close is harmless; and every transition has a monotonic timestamp.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest software/tests/edge/test_io.py -v`  
Expected: collection fails because `forgesight.edge.io` does not exist.

- [ ] **Step 3: Implement the mock adapter and mapping**

Keep the adapter free of GPIO imports and record immutable transitions.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m pytest software/tests/edge/test_io.py -v`  
Expected: all I/O tests passed.  
Run: `python -m pytest software/tests -q`  
Expected: all tests passed.

- [ ] **Step 5: Commit**

```text
R0: add mock IO safe-state adapter
```

### Task 5: SQLite Audit Repository

**Files:**
- Create: `software/src/forgesight/backend/__init__.py`
- Create: `software/src/forgesight/backend/repository.py`
- Create: `software/tests/backend/test_repository.py`

**Interfaces:**
- Consumes: validated canonical event mappings
- Produces: `SQLiteInspectionRepository.initialize()`, `save(event) -> bool`, `get(event_id) -> dict | None`, `list(limit, offset) -> list[dict]`, and `review(event_id, review) -> dict`

- [ ] **Step 1: Write failing repository tests**

Cover empty-database initialization, exact event round-trip, duplicate-ID idempotency, newest-first pagination, valid review, invalid review transition, and persistence across repository restart.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest software/tests/backend/test_repository.py -v`  
Expected: collection fails because the repository module does not exist.

- [ ] **Step 3: Implement the repository with standard-library `sqlite3`**

Use explicit transactions, a unique primary key, canonical JSON storage, indexed timestamp/result columns, and an append-only review audit table.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m pytest software/tests/backend/test_repository.py -v`  
Expected: all repository tests passed.  
Run: `python -m pytest software/tests -q`  
Expected: all tests passed.

- [ ] **Step 5: Commit**

```text
R0: persist idempotent inspection events
```

### Task 6: Inspection Orchestrator and Event Bus

**Files:**
- Create: `software/src/forgesight/edge/pipeline.py`
- Create: `software/src/forgesight/backend/event_bus.py`
- Create: `software/tests/edge/test_pipeline.py`

**Interfaces:**
- Consumes: replay source, scenario-provided mock results, decision engine, I/O adapter, repository, event validator, and event bus
- Produces: `InspectionPipeline.run(scenario_name: str, event_id: UUID | None = None) -> dict[str, object]` and `InspectionEventBus.subscribe() -> AsyncIterator[dict]`

- [ ] **Step 1: Write failing orchestration tests**

For all six scenarios assert decision, output state, schema validity, one committed row, and one post-commit publication. Add database-failure and duplicate-ID tests proving safe state and no publication.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest software/tests/edge/test_pipeline.py -v`  
Expected: collection fails because pipeline and event bus do not exist.

- [ ] **Step 3: Implement the pipeline in explicit stages**

Measure each stage with a monotonic clock, calculate total independently, save before publish, and enter safe state on every exception path.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m pytest software/tests/edge/test_pipeline.py -v`  
Expected: all pipeline tests passed.  
Run: `python -m pytest software/tests -q`  
Expected: all tests passed.

- [ ] **Step 5: Commit**

```text
R0: connect replay pipeline to audit events
```

### Task 7: FastAPI and WebSocket Service

**Files:**
- Create: `software/src/forgesight/backend/app.py`
- Create: `software/tests/backend/test_api.py`

**Interfaces:**
- Consumes: `InspectionPipeline`, `SQLiteInspectionRepository`, and `InspectionEventBus`
- Produces: `create_app(pipeline, repository, event_bus) -> FastAPI` with every route in the spec

- [ ] **Step 1: Write failing API tests**

Cover health, successful replay, unknown scenario, history, event detail, valid/invalid review, metrics summary, committed-event WebSocket delivery, and duplicate-ID behavior.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest software/tests/backend/test_api.py -v`  
Expected: collection fails because `create_app` does not exist.

- [ ] **Step 3: Implement the minimal API**

Use explicit request/response models, stable error codes, dependency injection, and no global database connection.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m pytest software/tests/backend/test_api.py -v`  
Expected: all API/WebSocket tests passed.  
Run: `python -m pytest software/tests -q`  
Expected: all tests passed.

- [ ] **Step 5: Commit**

```text
R0: expose inspection audit API
```

### Task 8: Touchscreen HMI Slice

**Files:**
- Create: `software/frontend/package.json`
- Create: `software/frontend/src/App.tsx`
- Create: `software/frontend/src/api.ts`
- Create: `software/frontend/src/types.ts`
- Create: `software/frontend/src/components/InspectionStatus.tsx`
- Create: `software/frontend/src/components/ConnectionBanner.tsx`
- Create: `software/frontend/src/App.test.tsx`
- Create: remaining minimal Vite/TypeScript configuration files

**Interfaces:**
- Consumes: inspection event JSON, `/api/v1/inspections`, and `/ws/inspections`
- Produces: live current result, reason, latency, connectivity state, and recent history at the target touchscreen viewport

- [ ] **Step 1: Create package/test configuration and write failing HMI tests**

Test PASS, FAIL, RECHECK, fault, disconnected/stale, reconnect-with-history, and unknown event-field tolerance using accessible roles and text.

- [ ] **Step 2: Install the frontend workspace**

Run: `npm install` from `software/frontend`  
Expected: dependencies install and the lockfile is created.

- [ ] **Step 3: Run the tests and verify RED**

Run: `npm test -- --run` from `software/frontend`  
Expected: tests fail because the application components do not exist.

- [ ] **Step 4: Implement the minimal HMI**

Use high-contrast status regions and large touch targets. Fetch history on initial load and reconnect; never retain an old PASS as live while disconnected.

- [ ] **Step 5: Run frontend tests and build**

Run: `npm test -- --run`  
Expected: all frontend tests passed.  
Run: `npm run build`  
Expected: production build completed without TypeScript errors.

- [ ] **Step 6: Commit**

```text
R0: add touchscreen inspection status slice
```

### Task 9: End-to-End Acceptance and Operating Instructions

**Files:**
- Create: `software/tests/acceptance/test_vertical_slice.py`
- Modify: `software/README.md`
- Modify: `docs/workflows/riya-stage2-execution-workflow.md`

**Interfaces:**
- Consumes: all prior task interfaces and six named fixtures
- Produces: one reproducible command sequence and acceptance evidence for the complete slice

- [ ] **Step 1: Write the failing acceptance test**

Parameterize all six scenarios and assert expected result, reason class, mock output, schema validity, one SQLite event, API equality, and one WebSocket publication. Re-run one event ID and assert idempotency.

- [ ] **Step 2: Run it and verify RED if any integration is missing**

Run: `python -m pytest software/tests/acceptance/test_vertical_slice.py -v`  
Expected: FAIL on the first missing integration behavior, or PASS only if prior tasks already satisfy the complete contract.

- [ ] **Step 3: Add only the missing integration wiring and operating instructions**

Document environment setup, tests, API startup, HMI startup, fixture replay, and evidence locations. Do not add physical-hardware claims.

- [ ] **Step 4: Run all verification**

Run: `python -m pytest software/tests -q`  
Expected: all Python tests passed.  
Run: `npm test -- --run` from `software/frontend`  
Expected: all frontend tests passed.  
Run: `npm run build` from `software/frontend`  
Expected: production build completed.  
Run: `git diff --check`  
Expected: no whitespace errors.

- [ ] **Step 5: Commit**

```text
R0: verify the recorded-image vertical slice
```
