# ForgeSight Software Contract

Shared interface between the edge runtime (`software/edge/`), backend (`software/backend/`),
SQLite audit log, and React HMI (`software/frontend/`).

- Python types: `software/common/schemas.py` (Pydantic v2) — import, never copy.
- Formal schema: `software/schema.json` (JSON Schema Draft 7).
- **Any change to this file, `schemas.py` or `schema.json` needs review from both software
  contributors and a check of every consumer (edge, backend, DB, HMI) before merge.**

## 1. InspectionResult

One record per conveyor trigger. Fields: `inspection_id` (UUID), `timestamp` (UTC ISO-8601,
`Z` suffix), `result`, `defect_type`, `confidence`, `class_names`, `poka_yoke_status`,
`per_stage_latency_ms`, `soc_temp_c`, `detections[]`, `image_path` (nullable).

| Enum | Values |
|---|---|
| `result` | `PASS`, `FAIL`, `RECHECK` |
| `defect_type` | `none`, `burr`, `flash`, `crack`, `scratch`, `dimensional_error`, `missing_hole`, `part_misaligned` |

`image_path` is `null` for PASS (only non-PASS frames are saved).
`bbox` format: `[x_min, y_min, x_max, y_max]` in pixels of the captured frame.

## 2. Decision semantics (source of truth: `software/edge/decision/engine.py`)

Evaluated in this order; first match wins.

| # | Condition | result | defect_type | confidence |
|---|---|---|---|---|
| 1 | No part present | `RECHECK` | `none` | `0.0` |
| 2 | Poka-Yoke geometry check failed | `FAIL` | `part_misaligned` > `dimensional_error` > `missing_hole` (priority order) | `1.0` (deterministic) |
| 3 | Top AI detection conf >= `fail_confidence` | `FAIL` | detected class | detection conf |
| 4 | Top AI detection conf >= `recheck_confidence` | `RECHECK` | detected class | detection conf |
| 5 | Otherwise | `PASS` | `none` | `1 - top_conf` (or `0.99` if no detections) |

Unknown AI class names are never trusted: they produce `RECHECK` / `none`.
Poka-Yoke failures (rows 1-2) skip the NPU entirely (`npu_inference_ms = 0`).

Default thresholds: `fail_confidence = 0.80`, `recheck_confidence = 0.50`.
These are placeholders until Riya selects them from the precision-recall curve.

## 3. Latency budget (total <= 100 ms)

| Stage | Budget |
|---|---|
| `capture_ms` (read + contrast adjust) | <= 10 ms |
| `poka_yoke_ms` | <= 15 ms |
| `npu_inference_ms` | <= 30 ms |
| `decision_ms` (decision + GPIO update) | <= 5 ms |

`total_ms` is the sum of the four stages (frame saving and logging are excluded).

## 4. Tower light / buzzer mapping (opto-isolated GPIO)

| State | Green | Red | Amber | Buzzer |
|---|---|---|---|---|
| PASS | on | | | |
| FAIL | | on | | on |
| RECHECK | | | on | |
| Fault (camera loss, stall) | | | on | |

> Fault behavior follows `software/contracts/io-interface.md`: ring illumination and buzzer are off. Kartikay must still approve physical signalling and pin mapping.

## 5. WebSocket (`/ws/live`)

Envelope: `{"event": "<type>", "data": { ... }}`

| Event | Payload |
|---|---|
| `inspection_result` | Full `InspectionResult` |
| `inspection_frame` | Low-latency base64 JPEG thumbnail for live preview |
| `watchdog_alert` | `WatchdogAlert` (below) |

### WatchdogAlert (additive extension)

`alert_type`: `camera_disconnected` \| `pipeline_stall` \| `overheating`;
`severity`: `warning` \| `critical`; `message`; `timestamp`; `value` (nullable number:
stall ms, SoC temp in C, or missed-frame count).

Triggers: pipeline stall > 200 ms (critical), 3 consecutive missed frames (critical),
SoC temperature > 65 C (warning).

## 6. REST routes

| Route | Purpose |
|---|---|
| `GET /health` | Health probe and uptime |
| `GET /api/v1/inspections/latest` | Most recent inspection |
| `GET /api/v1/inspections/history` | Paginated history (`result`, `limit`, `offset`) |
| `POST /api/v1/operator/review` | Operator correction -> `software/dataset/retraining/` |
| `GET /api/v1/system/status` | SoC temperature, RAM, FPS, average latency |
| `POST /api/v1/settings/thresholds` | PASS/FAIL/RECHECK thresholds + LED ring PWM brightness |

### Read response bodies (backend v1)

`GET /health`:

```json
{"status":"ok","uptime_seconds":12.5}
```

`GET /api/v1/inspections/latest`: a complete `InspectionResult` object, or JSON `null`
when there are no inspection events.

`GET /api/v1/inspections/history?result=FAIL&limit=50&offset=0`:

```json
{
  "items": [
    {
      "inspection_id": "f5bd274e-8f46-4bd9-b5fb-28c26015609d",
      "timestamp": "2026-10-16T12:00:00Z",
      "result": "FAIL",
      "defect_type": "burr",
      "confidence": 0.91,
      "class_names": ["burr", "flash", "crack", "scratch"],
      "poka_yoke_status": {
        "part_present": true,
        "position_valid": true,
        "hole_present": true,
        "size_in_range": true
      },
      "per_stage_latency_ms": {
        "capture_ms": 8.0,
        "poka_yoke_ms": 12.0,
        "npu_inference_ms": 25.0,
        "decision_ms": 2.0,
        "total_ms": 47.0
      },
      "soc_temp_c": 52.0,
      "detections": [],
      "image_path": "data/frames/f5bd274e-8f46-4bd9-b5fb-28c26015609d.jpg"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

`items` contains complete `InspectionResult` objects. Results are ordered by
`timestamp DESC, rowid DESC`; `total` is the number matching the optional result filter
before pagination. `limit` defaults to 50 and is capped at 500; `offset` defaults to 0.

`GET /api/v1/system/status`:

```json
{
  "soc_temp_c": 52.0,
  "soc_temp_timestamp": "2026-10-16T12:00:00Z",
  "ram_used_mb": 2048.0,
  "ram_total_mb": 8192.0,
  "fps": 2.0,
  "avg_latency_ms": 48.5
}
```

RAM means system RAM, not backend-process RAM. `fps` is the count of
`inspection_result` events in the preceding five seconds divided by five; watchdog alerts
are excluded. `soc_temp_timestamp` is the timestamp of the inspection that supplied the
reading, not the API response time. `soc_temp_c` and its timestamp are both `null` when
there is no sample or the edge sentinel is `-1.0`. `avg_latency_ms` is the mean total
latency from at most the latest 100 inspections, or `null` when there are none.

The local Vite development origin (`http://localhost:5173`) must be enabled by narrow
localhost CORS configuration (`GET` only) or a documented Vite proxy before the HMI
integration. The current backend allows only that origin and GET methods.

Operator review and settings request/response bodies remain undefined and must be added
before those routes are implemented or merged.

## 7. Edge -> backend handoff (PROPOSED — pending Riya approval)

Proposal: use the existing JSONL sink as the edge-to-backend handoff. The edge runtime
writes one JSON line per event to a JSONL file, already in the WebSocket envelope shape
(`{"event": "inspection_result", "data": {...}}` or `{"event": "watchdog_alert", "data": {...}}`),
so the backend can tail and rebroadcast without a schema change. Run the edge CLI with
`--jsonl data/events.jsonl`; it has no default JSONL path. Alternatives are an in-process
import or a new internal `POST` route. Riya must approve this section 7 decision before
backend implementation or merge.
