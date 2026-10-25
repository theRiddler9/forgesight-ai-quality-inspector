# ForgeSight AI Quality Inspector

ForgeSight is a local, edge-AI inspection station for MSME metal-part production. It combines deterministic OpenCV Poka-Yoke checks, defect inference, PASS/FAIL/RECHECK decisions, isolated industrial outputs, a SQLite audit trail, and a React operator HMI.

## Current status

The repository contains a reproducible **Stage 2 virtual validation slice**. Six synthetic scenarios run through geometry checks, simulated inference, decision logic, mock I/O, SQLite, FastAPI/WebSockets, and the HMI.

The following remain hardware or real-data validation items:

- real component-matched burr dataset and trained model
- RKNN INT8 execution on Orange Pi 5
- measured trigger-to-decision latency and SoC temperature
- reviewed GPIO pinout and physical opto-isolation validation
- SolidWorks FEA, thermal, BOM, and shop-floor evidence

Synthetic replay, desktop ONNX/RKNN adapter tests, and mock GPIO are not claims of physical performance or model recall.

## Architecture

```text
Trigger sensor
  -> OpenCV capture and Poka-Yoke checks
  -> ONNX / RKNN defect inference
  -> PASS / FAIL / RECHECK decision
  -> isolated GPIO outputs and SQLite audit
  -> FastAPI / WebSocket telemetry
  -> React touchscreen HMI
```

Poka-Yoke checks run before inference. The shared decision engine is the only source of PASS, FAIL, and RECHECK results.

## Run the virtual demo

Use Python 3.10 or newer. From the repository root:

```powershell
python -m pip install -r software/requirements-dev.txt
```

Start the backend in one terminal:

```powershell
python -m software.backend
```

Install and start the HMI in a second terminal:

```powershell
cd software/frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. If Vite development mode is unavailable on Windows, use `npm run build` followed by `npm run preview` and open `http://127.0.0.1:4173`.

The backend uses `127.0.0.1:8000` and `data/audit.sqlite3` by default. Set `FORGESIGHT_DB_PATH` to use an isolated demo database.

## Run the edge replay CLI

```powershell
python -m software.edge.main `
  --mock-hardware `
  --mock-camera `
  --use-stub-engine `
  --count 20 `
  --interval-ms 200 `
  --jsonl data/events.jsonl
```

The optional profile-validated RKNN path is available when RKNN-Lite and a compatible artifact are present:

```powershell
python -m software.edge.main `
  --mock-hardware --mock-camera --use-rknn-engine `
  --profile-catalog software/profiles/catalog `
  --profile metal-plate-v1@1.0.0 `
  --model-manifest data/models/model-manifest.json `
  --model-root data/models
```

The adapter verifies the artifact hash, profile fingerprint, preprocessing, thresholds, and output contract before inference. GPIO stays mock-only until the electrical pinout is approved.

## Verify the repository

From the repository root:

```powershell
python -m pytest -q
cd software/frontend
npm run typecheck
npm run test -- --run
npm run build
npm run test:e2e
```

The browser suite starts its own backend and preview server. Keep ports 8000 and 4173 free when running it.

## Dataset and model workflow

Dataset tooling is under `software/dataset/`. Keep raw images, annotations, manifests, exports, and model weights in ignored `data/` directories. The workflow is:

1. Import rights-cleared captures with `python -m software.dataset import`.
2. Add reviewed `bbox_json_v1` annotations and physical-part/session IDs.
3. Validate and audit the manifest.
4. Create grouped train/validation/test splits by physical part.
5. Export reviewed data to YOLO format.
6. Run training preflight with `python -m software.ml.training preflight`.
7. Train only after the dataset, profile, licensing, and environment are approved.
8. Evaluate on a held-out real set, export ONNX, validate the graph, then compile and benchmark RKNN on the target board.

See [dataset and annotation rules](docs/ml-phase1/dataset-and-annotations.md), [pre-training readiness](docs/ml-phase1/pre-training-readiness.md), and [ONNX integration](docs/ml-phase1/onnx-integration.md).

## Evidence and validation

- [KPI evidence matrix](validation/kpi-matrix.json)
- [Evidence index](validation/evidence-index.json)
- [Software FMEA](validation/fmea/software-fmea.csv)
- [Stage 2 work plan](docs/forgesight-stage2-work-plan.md)
- [Software architecture](system/software-architecture.md)
- [Recorded-image demo evidence](evidence/recorded-image-slice/README.md)

Validate the evidence tools with:

```powershell
python -m validation validation/evidence-index.json
python -m validation.kpi validation/kpi-matrix.json
```

## Repository map

| Directory | Contents |
|---|---|
| `docs/` | Goals, roles, roadmap, contracts, and ML workflow |
| `mechanical/` | SolidWorks parts, assemblies, FEA, thermal, and BOM |
| `electrical/` | KiCad schematics, isolation, pinout, and BOM |
| `software/edge/` | Acquisition, Poka-Yoke, decision, watchdog, and I/O |
| `software/ml/` | Training preflight, evaluation, export, parity, and benchmarks |
| `software/backend/` | FastAPI, SQLite audit storage, and WebSockets |
| `software/frontend/` | React/Vite operator HMI |
| `software/dataset/` | Intake, manifests, grouped splits, and YOLO export |
| `validation/` | KPI evidence, FMEA, and validation tools |
| `evidence/` | Screenshots and reproducibility records |

## Team ownership

See [Roles.md](docs/Roles.md) for the RACI matrix. Akash leads edge runtime, deployment validation, and mechanical co-lead work. Riya leads dataset/model training, backend, and HMI work. Cross-domain interfaces require review by the affected owners.

## Engineering boundaries

- Run all production decisions through the shared decision engine.
- Keep physical tests and hardware claims separate from virtual evidence.
- Keep raw datasets and model artifacts outside Git unless explicitly approved.
- Preserve native CAD and KiCad sources alongside exports and screenshots.
- Use small, traceable commits and record the command behind each quantitative claim.

## License and references

Project references and external sources are listed in [docs/references.md](docs/references.md). Review dataset and model licenses before importing third-party material.
