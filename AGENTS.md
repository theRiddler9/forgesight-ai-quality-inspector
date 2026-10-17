# ForgeSight: AI-Enabled Industrial Quality Inspector

## Mission
Build an autonomous, real-time edge-AI quality inspection station that mounts over an MSME conveyor line to inspect metal parts for surface flaws (burrs, flash, cracks, scratches) and dimensional Poka-Yoke errors under ₹10,000 in hardware.

The system must deterministically capture parts on trigger, enforce rule-based geometric constraints, infer surface anomalies via a quantized INT8 neural network on the RK3588S NPU in under 100 ms, dispatch opto-isolated industrial I/O, maintain an immutable SQLite audit log, and stream live inspection telemetry to a touchscreen operator dashboard.

## Non-Goals
Do not reduce the project to:
- Cloud-dependent AI vision (must run 100% locally on the Orange Pi 5 edge device)
- Custom 3D-printed mechanical housings (must use commercial off-the-shelf IP65 ABS junction box)
- Generic camera web streaming without deterministic Poka-Yoke gating
- An LLM or VLM wrapper around raw camera frames (deterministic OpenCV + quantized INT8 YOLO only; LLMs may explain evidence, but must not judge whether a defect occurred)
- An unverified prototype (Stage 2 requires SolidWorks FEA FoS > 2.0, thermal headroom SoC < 65 °C, and RKNN NPU benchmark ≤ 100 ms)

## Core Pipeline
```
Conveyor Inductive/Optical Sensor
  -> PC817 Optocoupler Isolation
  -> Orange Pi 5 GPIO Interrupt
  -> OpenCV Global Shutter Capture (OV9281 + LED Ring Light)
  -> Deterministic Poka-Yoke Rules (Presence / Position / Hole / Size)
  -> RKNN INT8 YOLO Detection on RK3588S NPU (Burr / Flash / Crack / Scratch)
  -> Decision Engine (PASS / FAIL / RECHECK Confidence Thresholding)
  -> Opto-Isolated Indicator Driver (Tower Light G/R/A + Buzzer + LED Ring PWM)
  -> SQLite Local Audit Log (Result, Defect, Confidence, Latency, SoC Temp)
  -> FastAPI Async Streamer + WebSockets
  -> React + Tailwind Touchscreen Operator HMI
```
The capture -> Poka-Yoke -> NPU inference -> decision -> I/O & audit log pipeline is fixed for the Stage 2 architecture.

## Shared Source of Truth
Read these before implementation:
- `REMEMBER.md` — non-negotiable project notes, competition audit boundaries, and hardware constraints
- `starter_code.md` — software contracts, task division, stub engine, and REST/WebSocket routes
- `README.md` — system architecture, team roles, and repository map
- `docs/Project_Goals.md` — scope, objectives, and KPI targets (< ₹10,000 BOM, ≤ 100 ms latency, > 95% recall)
- `docs/Roles.md` — RACI matrix and subsystem responsibilities
- `docs/roadmap.md` — Stage 2 virtual validation vs Stage 3 shop-floor deployment boundary
- `docs/design_decisions.md` — why Orange Pi 5 over Jetson, COTS over 3D printing, passive heatsink sizing

## Package Boundaries
Any contributor may work anywhere in the repository. Keep changes coherent with these component boundaries, but do not treat them as exclusive ownership:
- **Akash (Edge & Hardware Runtime Lead)**:
  - Edge optimization, ONNX export, INT8 quantization, and RKNN NPU deployment (`software/ml/export/`, `software/ml/benchmarks/`).
  - Deterministic vision engine: OpenCV capture, exposure locking, contrast adjustment, and Poka-Yoke rule checks (`software/edge/acquisition/`, `software/edge/poka_yoke/`).
  - Decision engine, opto-isolated GPIO control, and watchdog monitor (`software/edge/decision/`, `software/edge/io_control/`, `software/edge/watchdog/`).
  - *(Also Mechanical Co-Lead: SolidWorks master assembly and structural/thermal FEA)*.
- **Riya (ML & Software Platform Lead)**:
  - Dataset engineering: raw collection, synthetic augmentation, YOLO annotation, part-based splits, and 200-image INT8 calibration set (`software/dataset/`) — supported by Kartikay and Rudra on rig/lighting.
  - Model training and benchmarking: PyTorch YOLOv8n / YOLO11n training, mAP/recall curves, and confidence threshold selection (`software/ml/training/`).
  - Backend & audit logging: asynchronous FastAPI service, SQLite audit database, WebSocket live streaming, and operator review API (`software/backend/`).
  - Operator touchscreen HMI: React + Vite + Tailwind dashboard, live camera feed, yield/defect charts, and settings UI (`software/frontend/`).

## Inspection & Review Boundary
```
Conveyor Sensor Trigger
  -> Edge Pipeline executes capture & Poka-Yoke
  -> NPU runs INT8 YOLO inference
  -> Decision engine produces InspectionResult
  -> Opto-isolated GPIO updates tower light & buzzer
  -> SQLite logs result & metrics
  -> FastAPI WebSockets broadcast event
  -> Operator HMI renders result
  -> [Optional] Operator corrects defect classification via POST /api/v1/operator/review
  -> Corrected frame & label saved to software/dataset/retraining/
```
No duplicate decision logic across packages: the decision engine in `software/edge/decision/` is the single source of truth for PASS / FAIL / RECHECK status.

## Shared Contracts
All packages must import shared types from `software/common/schemas.py` and conform to `software/CONTRACT.md`. Do not create local incompatible copies of `InspectionResult`, `PokaYokeStatus`, `LatencyBreakdown`, or `DetectionBox`.

Contract changes require checking every package consumer (edge runtime, FastAPI backend, SQLite database, React HMI) before merge.

## Definition of Done
An inspection feature or pipeline stage is only considered done when:
1. Normal parts pass through OpenCV Poka-Yoke and produce a PASS decision.
2. Defective parts (burrs, flash, cracks, scratches) trigger accurate FAIL or RECHECK decisions.
3. The per-stage latency breakdown verifies the ≤ 100 ms total target:
   - Capture: ≤ 10 ms
   - Poka-Yoke: ≤ 15 ms
   - NPU Inference: ≤ 30 ms
   - Decision & I/O: ≤ 5 ms
4. Opto-isolated GPIO signals correspond strictly to the decision state (Green = PASS, Red = FAIL, Amber = RECHECK/Fault).
5. SQLite audit log records the inspection with SoC temperature and latency breakdown.
6. The WebSocket broadcast renders live on the React touchscreen HMI.
7. If end-to-end integration fails to reproduce the decision or exceeds 100 ms latency, the feature is not done.

## Engineering Rules
- Prefer deterministic behavior over LLM judgment. Rule-based OpenCV checks must filter geometric faults before using NPU time.
- Write tests for deterministic components and contract schemas.
- Never claim something works without running the relevant test, benchmark, or simulation. Evidence before assertions always.
- Keep modules narrow, hardware interfaces abstracted, and schemas explicit.
- Prefer the smallest working primitive over complex frameworks.
- Do not add authentication, billing, cloud sync, accounts, or unrelated enterprise bloat before the core edge inspection pipeline works.

## Reliability and Evidence Rules
- **Hardware isolation:** 100% of GPIO signals must pass through PC817 optocouplers to prevent industrial line transients from damaging the Orange Pi 5.
- **Watchdog protection:** A pipeline stall (> 200 ms) or camera frame loss must trip the watchdog, set the amber tower light/buzzer, and log a critical fault.
- **Thermal headroom:** SoC temperature must remain below 65 °C at 45 °C ambient. If temperature exceeds 65 °C, flag a thermal warning.
- **Sensor noise:** Sensor chatter, dirty triggers, and buck converter ripple are hardware/setup errors, not AI defects. Address them via 10–20 ms software debounce and low-pass filtering.
- **Model validation:** Defect recall must exceed 95% on the held-out test set; false-reject rate must be documented with precision-recall curves.

## Shop-Floor & Hardware Rig Rules
- Treat all physical inputs (inductive proximity sensors, pushbuttons, ambient factory lighting) as noisy and untrusted.
- The optical cowl and LED ring light must eliminate ambient lighting variation; camera exposure and gain must be software-locked on initialization.
- All edge hardware drivers must support mock modes (`--mock-hardware`, `--mock-camera`, `--use-stub-engine`) so developers can test the full pipeline anywhere without physical rig access.

## Test Isolation
- Test suites (`pytest`, vitest, etc.) must exclude build outputs, caches, virtual environments, and temporary files.
- Local tests run with mock hardware; hardware tests run on the Orange Pi 5 target.

## Codex / Superpowers Workflow
Before implementation:
- Read this file (`AGENTS.md`)
- Read `REMEMBER.md`
- Read `starter_code.md`
- Read `docs/Project_Goals.md` and relevant component plans
- Use Superpowers planning before coding.
- For independent tasks, subagents may be used, but they must not redesign cross-team interfaces.
- Use `verification-before-completion` before declaring milestones complete.

## Git Rules
- Work on separate feature branches (`feat/`, `fix/`, `pair/`).
- Make small logical commits with clear prefixes (`sw:`, `mech:`, `elec:`, `docs:`).
- Merge shared contracts before dependent work.
- Pull/rebase shared changes before integration.
- Avoid destructive Git operations (`rebase -i` on shared branches, force pushes).
- Do not wait until Day 3 to integrate. Commit every feature and stage frequently for a dense audit trail.
- **Both software contributors need to review PRs of each other and then make changes accordingly which are related to each other.**
