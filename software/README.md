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

Open `http://127.0.0.1:5173`. The Vite server proxies `/api` and `/ws` to the local backend. On restricted Windows installations where Vite's development dependency optimizer cannot traverse its parent directories, use `npm run build` followed by `npm run preview` and open `http://127.0.0.1:4173`. The preview server uses the same local API and WebSocket proxy. Keep the backend on port 8000 when using these proxies.

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
```

The backend suite covers replay, actual OpenCV geometry checks, decision logic, mock I/O safe states, canonical schema validation, SQLite and review history, REST, WebSocket delivery, restart persistence, and all six scenarios. The HMI component suite covers status, simulated labels, history detail, and disconnection/reconnection. Browser automation and physical hardware validation are separate future work.

## Future integration

Replace `inspection/replay.py` with a camera adapter that supplies the same frame contract, replace `ScenarioDetector` in `inspection/service.py` with measured model inference, and replace `MockGPIOController` behind the existing edge I/O interface after electrical approval. Real-image datasets, ONNX/RKNN parity, Orange Pi timing, physical pin mapping, and shop-floor validation remain open Stage 2/3 work.
