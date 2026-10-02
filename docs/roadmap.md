# ForgeSight Stage 2 Roadmap

The schedule is relative until the official submission deadline is recorded.

## Week 1 - Foundation and Replay Baseline

- Close the component, burr-definition, false-reject, and deadline decisions.
- Freeze the inspection-event, camera, and electrical I/O contracts.
- Establish the repository structure and evidence rules.
- Create dataset documentation, labeling rules, and split manifests.
- Demonstrate recorded-image replay through mocked decision and event storage.

**Exit:** Contracts are reviewable and one recorded inspection can traverse the planned software boundaries with mocks.

## Week 2 - Vision Baselines

- Implement and evaluate deterministic Poka-Yoke checks.
- Train the first heavy-burr YOLO baseline.
- Record metrics, error categories, timing, environment, and checkpoint provenance.
- Stabilize the inspection event database and API.

**Exit:** Reproducible OpenCV and FP32 model baselines exist on a part-separated held-out set.

## Week 3 - Edge Integration

- Verify ONNX parity and compile the INT8 RKNN model.
- Benchmark the complete pipeline on Orange Pi 5.
- Integrate PASS / FAIL / RECHECK, mocked/hardware I/O, and watchdog behavior.
- Connect the WebSocket event stream to the touchscreen HMI.

**Exit:** A recorded or camera-triggered inspection reaches outputs, SQLite, API, and HMI with measured per-stage timing.

## Week 4 - Validation and Submission

- Run sustained, fault-path, API, HMI, and acceptance tests.
- Reconcile mechanical, electrical, software, BOM, and presentation interfaces.
- Complete FMEA, KPI evidence matrix, maker-journey evidence, and slide assets.
- Run clean-checkout reproduction and final demo rehearsal.

**Exit:** Every Stage 2 claim points to reproducible evidence and Stage 3 work is clearly labeled as planned.

## Milestone Order

`R0 contracts -> R1 dataset -> R2/R3 baselines -> R4 deployment -> R5/R6 integration -> R7 HMI -> R8 validation`
