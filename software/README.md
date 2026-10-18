# ForgeSight software

The Stage 2 recorded-image slice runs locally without a camera, Orange Pi, GPIO, or trained burr model. It reuses the team edge pipeline (`edge/`), common Pydantic models (`common/`), and audit API (`backend/`). The `inspection/` adapter adds synthetic image replay, canonical event construction, atomic SQLite storage, and six repeatable scenarios. `frontend/` is the React operator console.

## Setup

Use Python 3.10 or newer and Node 20.19+ or 22.12+. From the repository root:

```sh
python -m venv .venv
# Activate .venv using your shell's activation command.
python -m pip install -r software/requirements-dev.txt
cd software/frontend
npm ci
cd ../..
```

The runtime dependencies are in `software/requirements.txt`; the development file adds pytest, schema validation, and API testing tools. `npm ci` uses the committed lockfile. No paid service, model download, or hardware driver is required.

## Run

In a terminal at the repository root:

```sh
python -m software.backend
```

In another terminal:

```sh
cd software/frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite server proxies `/api` and `/ws` to the local backend. On restricted Windows installations where Vite's development dependency optimizer cannot traverse its parent directories, use `npm run build` followed by `npm run preview` and open `http://127.0.0.1:4173`. The preview server uses the same local API and WebSocket proxy. Keep the backend on port 8000 when using these proxies. In the current restricted Windows environment, `npm run dev` exits after esbuild reports `Cannot read directory "../../../../../..": Access is denied`; the build and preview path is verified and needs no security bypass.

The backend defaults to `127.0.0.1:8000` and `data/audit.sqlite3`. Optional variables are `FORGESIGHT_DB_PATH`, `FORGESIGHT_FIXTURE_DIR`, `FORGESIGHT_API_HOST`, and `FORGESIGHT_API_PORT`. Use a new database path for an isolated demonstration. Bind to loopback: replay and review writes accept loopback clients only, and WebSocket connections accept local browser origins. There is no login system or network access policy for a factory LAN deployment.

## Six-scenario demonstration

Select each button in the console and check the live result, image/geometry explanation, history row, detail view, and metrics. The API is also available at `POST /api/v1/inspections/replay` with JSON such as `{"scenario":"clean_part"}`. Results are:

| Scenario | Expected decision | Source |
|---|---|---|
| `clean_part` | PASS | Synthetic pixels and no simulated burr |
| `heavy_burr` | FAIL | Scenario-driven high-confidence burr |
| `uncertain_burr` | RECHECK | Scenario-driven uncertain burr |
| `missing_hole` | FAIL | OpenCV geometry from synthetic pixels |
| `no_part` | RECHECK | OpenCV absence from synthetic pixels |
| `capture_fault` | RECHECK | Simulated capture failure |

The images and their generator are in `fixtures/`; see [fixture limitations](fixtures/README.md). The burr confidence is scenario metadata, **not image-derived AI inference**. The light, buzzer, and ring output are mock state only. Software timing is measured on the development machine and is not the Orange Pi trigger-to-decision latency. No recall, precision, model parity, GPIO isolation, or physical safety claim follows from this demo.

The canonical event conforms to `contracts/inspection-event.schema.json`. The earlier team `InspectionResult` remains the edge/backend projection. `backend/database.py` commits both records in one SQLite transaction; WebSocket publication follows that commit. Reviews are appended separately and never alter the original decision. REST clients can recover missed live events from `GET /api/v1/inspections`.

## Verify

From the repository root:

```sh
python -m pytest -q
cd software/frontend
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

The backend suite covers replay, actual OpenCV geometry checks, decision logic, mock I/O safe states, canonical schema validation, SQLite and review history, REST, WebSocket delivery, restart persistence, and all six scenarios. The HMI component suite covers status, simulation labels, history detail, and disconnection/reconnection.

`npm run test:e2e` builds the HMI, then Playwright starts and stops its own backend and preview server. It uses a unique ignored database under `.tools/playwright-runs/` on each run. No running demo server is required; ports 8000 and 4173 must be free. Playwright uses installed Chrome or Edge on Windows, or a configured `FORGESIGHT_BROWSER` executable. If neither is available, install Playwright Chromium through the normal browser-install command where permitted. Set `FORGESIGHT_PYTHON` if `python` is not on `PATH`; the test runner also recognizes the local ignored `.tools/python/python.exe`. Browser tests click all six controls, inspect history and detail after refresh, submit a review, check metrics and pagination, interrupt/recover WebSocket delivery, restart the backend, and check desktop/mobile layout and keyboard activation. Optional `FORGESIGHT_CAPTURE_EVIDENCE=1` writes review screenshots to `evidence/recorded-image-slice/`.

For a clean manual demo, set `FORGESIGHT_DB_PATH` to a new path such as `data/demo-2026-10-17.sqlite3` before starting the backend. This starts an empty audit trail without deleting an existing database. If the browser reports a disconnected backend, verify the backend health endpoint at `http://127.0.0.1:8000/api/v1/health`, keep the HMI preview on `127.0.0.1:4173`, and confirm both ports are free before restarting. A missing fixture should be checked against `fixtures/scenarios.json` and `FORGESIGHT_FIXTURE_DIR`. Do not present local timing, synthetic fixtures, or mock I/O as physical validation.

## Future integration

The provisional `metal-plate-v1` profile now supplies replay geometry and decision thresholds. See [component profiles](../docs/ml-phase1/component-profiles.md), [dataset/annotation tools](../docs/ml-phase1/dataset-and-annotations.md), [verified dataset candidates](../docs/ml-phase1/dataset-candidates.md), the [evaluation protocol](../docs/ml-phase1/evaluation-protocol.md), the [pre-training readiness gate](../docs/ml-phase1/pre-training-readiness.md), and the [optional ONNX integration guide](../docs/ml-phase1/onnx-integration.md). Read-only `GET /api/v1/component-profiles` reports active and available profiles. New canonical events retain the selected profile fingerprint and model metadata; historical events remain unchanged. The backend defaults to the plate profile and the six demo controls require no new selection step.

Add a physical camera adapter behind the current frame contract, validate a trained model against the supported local ONNX decoder, implement RKNN on target hardware, and replace `MockGPIOController` behind the existing edge I/O interface after electrical approval. Real-image datasets, model training, ONNX/RKNN parity, Orange Pi timing, physical pin mapping, and shop-floor validation remain open Stage 2/3 work. The scenario detector remains explicit simulation.
