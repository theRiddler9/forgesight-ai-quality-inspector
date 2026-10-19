# ForgeSight Stage 2 Work Plan

**Prepared:** 2026-10-02  
**Scope:** Vishwakarma Innovation Challenge, Stage 2 - Design and Feasibility Audit  
**Working assumption:** The user is Riya, based on the workspace account and the team roster. The personal lane below therefore prioritizes Riya's software and edge-AI responsibilities.  
**Schedule basis:** No submission deadline appears in the reviewed documents, so the plan uses four relative work weeks. Compress the weeks in order if the actual deadline is closer.

**Execution workflow:** Use [`workflows/riya-stage2-execution-workflow.md`](workflows/riya-stage2-execution-workflow.md) as the day-to-day checklist. This document remains the master scope and sequencing reference.

## 1. Authoritative Scope

Use the documents in this order when two sources disagree:

1. `Project_Goals.md`, `Tech_Stack.md`, `Roles.md`, and the repository `README.md`
2. `Vishwakarma Innovation  (2).pdf` for repository organization and evidence rules
3. `Vishwakarma Innovation  (1).pdf` for detailed ownership
4. `RUGGED AI-ENABLED VISION FOR MSMEs.pdf` for the original problem, user journey, and long-term concept
5. The KiCad and SOLIDWORKS manuals as tool references, not as requirements

The current Stage 2 design is:

- One component type and one primary defect: heavy burrs.
- COTS-first hardware: IP65 ABS junction box, 2020 extrusion, rubber isolators, standard cable glands, and an external heatsink.
- Orange Pi 5 with a local OpenCV plus INT8 RKNN inference pipeline.
- PASS / FAIL / RECHECK decisions, local SQLite audit logging, FastAPI/WebSocket services, and a React touchscreen HMI.
- Virtual validation in Stage 2. Physical build, shop-floor deployment, and shadow-mode testing remain Stage 3 work.
- Native CAD and KiCad files, benchmark logs, screenshots, and creation history are part of the submission evidence.

## 2. Conflicts to Resolve Before Design Work

| Conflict | Decision for Stage 2 | Required documentation change |
|---|---|---|
| ₹15,000 in the concept PDF vs under ₹10,000 in newer documents | Use **under ₹10,000** as the binding KPI | Record the concept-to-COTS cost change in `design_decisions.md` and the iteration log |
| 3D-printed PETG enclosure vs COTS IP65 ABS enclosure | Use the **COTS IP65 ABS enclosure** | Update presentation copy derived from the older concept PDF |
| Field/lab testing phases vs Stage 2 virtual validation | Stage 2 ends at CAD, FEA, schematics, software execution, and benchmark evidence | Put physical and shop-floor tests only in `validation/stage3_plan/` |
| Multi-defect detector vs burr-first plan | Heavy burr detection is the acceptance target; flash, cracks, and scratches are stretch/future classes | Make the dataset card and KPI wording explicit |
| 100 ms inference vs 100 ms total inspection time | Track both, but use **end-to-end trigger-to-decision ≤100 ms** as the final KPI | Log per-stage timings so the inference contribution is visible |
| Top-level `system/` folder in README vs cross-domain artifacts placed under `software/` and `electrical/` in the structure PDF | Prefer the subsystem structure; add `system/` only if it owns a single approved cross-domain specification | Align README and `slide_content_map.md` after the team decides |
| `Project_Goals.md` ends at the Stage 2/Stage 3 heading | Complete the roadmap section before execution | Add explicit in-scope/out-of-scope tables |

Two targets still need team decisions: an acceptable false-reject rate and the exact Stage 2 submission deadline.

## 3. Current Repository State

The repository currently contains only `README.md` and `LICENSE`. None of the proposed `docs/`, `mechanical/`, `electrical/`, `software/`, `validation/`, `evidence/`, or `submission/` deliverables has been committed yet.

This makes repository setup, scope freezing, and interface definition the first critical-path milestone. Do not begin independent subsystem work without those contracts, or the CAD, electronics, and software designs will diverge at the camera, mounting, power, and GPIO boundaries.

## 4. Critical Path

1. Freeze Stage 2 scope, KPI definitions, hardware assumptions, and repository structure.
2. Freeze cross-domain interfaces: camera geometry, trigger behavior, GPIO allocation, voltage levels, output behavior, and audit-event schema.
3. Produce a thin vertical software slice using recorded images and mocked GPIO: capture -> Poka-Yoke -> placeholder inference -> decision -> SQLite -> WebSocket -> HMI.
4. Build the burr dataset and establish a reproducible FP32 baseline.
5. Export ONNX, compile INT8 RKNN, and benchmark on Orange Pi 5.
6. Integrate the trained model into the vertical slice and lock PASS / FAIL / RECHECK thresholds.
7. Collect KPI evidence, complete FMEA, reconcile BOM/CAD/KiCad/software interfaces, and assemble the presentation.

## 5. Riya's Workstream

### Work Package R0 - Repository and Contracts

**Collaborator:** Akash  
**Dependencies:** Team scope decisions  
**Outputs:**

- Create the agreed folder skeleton from `Vishwakarma Innovation  (2).pdf`.
- Copy the goals, stack, and role documents into `docs/` and finish `roadmap.md`, `design_decisions.md`, `references.md`, and `CONTRIBUTING.md`.
- Define the canonical inspection event with: timestamp, part ID, result, defect type, confidence, Poka-Yoke results, per-stage latency, SoC temperature, image reference, and operator review fields.
- Define the software/electrical interface: trigger input, tower-light channels, buzzer, ring-light PWM, active levels, timeout behavior, and safe state.
- Define branch/commit naming and the evidence rule: native source + export/screenshot + validation log + commit.

**Done when:** Every team member can name where their native file, evidence, and presentation asset belongs, and both software and electrical leads approve the I/O table.

### Work Package R1 - Dataset Foundation

**Collaborator:** Akash; Kartikay supports image-rig consistency  
**Dependencies:** Final camera/lighting assumptions and one selected part type  
**Outputs:**

- `software/dataset/DATASET_CARD.md` with provenance, consent/licensing, part type, burr definition, real vs synthetic counts, class balance, and known limitations.
- Raw, annotated, augmented, and split manifests. Split by physical part, never by image.
- A real held-out test set that is never used for training or threshold tuning.
- A separate 200-image INT8 calibration set with representative lighting, pose, and surface variation.
- Annotation quality check on a sampled subset and a documented defect-labeling guide.

**Done when:** The dataset can be reproduced from manifests, no physical part leaks across splits, and the calibration set is frozen.

### Work Package R2 - Deterministic Vision Baseline

**Collaborator:** Akash  
**Dependencies:** Sample images and camera contract  
**Outputs:**

- Capture interface with exposure lock, crop/ROI, contrast normalization, and explicit camera-loss errors.
- Independent Poka-Yoke checks for part presence, position, required hole/feature, and size range.
- Per-stage timing instrumentation.
- A replay mode that processes a recorded folder without hardware.

**Done when:** A recorded dataset can run deterministically from input image to structured Poka-Yoke result, including negative cases for missing, rotated, and badly exposed parts.

### Work Package R3 - Model Training and Evaluation

**Collaborator:** Akash  
**Dependencies:** R1 dataset freeze  
**Outputs:**

- Reproducible YOLOv8n and/or YOLO11n training configuration with fixed seeds and versioned dependencies.
- FP32 baseline metrics: precision, recall, mAP, confusion matrix, false-reject rate, and false-accept/escape rate on the real held-out set.
- Precision-recall analysis that proposes PASS / FAIL / RECHECK thresholds.
- An experiment log explaining which model is selected and why.

**Done when:** Heavy-burr recall exceeds 95% on the held-out real set, or the gap is documented with a concrete data/model recovery action. Do not hide an unmet KPI behind synthetic-only results.

### Work Package R4 - ONNX, INT8, and RKNN Deployment

**Collaborator:** Akash  
**Dependencies:** Selected FP32 model and Orange Pi 5 access  
**Outputs:**

- PyTorch -> ONNX -> RKNN conversion scripts and exact commands.
- Frozen 200-image calibration manifest.
- FP32 vs INT8 accuracy comparison.
- Warm-up and repeated NPU benchmark logs, separating preprocessing, inference, postprocessing, decision, and total latency.
- Deployment notes for Armbian/Ubuntu 22.04 and RKNN-Toolkit2.

**Done when:** The `.rknn` model runs on the target NPU and the measured trigger-to-decision pipeline is at or below 100 ms, or a bottleneck report identifies the failing stage and recovery plan.

### Work Package R5 - Decision Engine, I/O Adapter, and Watchdog

**Collaborator:** Akash; interface review by Aratrik and Kartikay  
**Dependencies:** R0 contracts, R2 checks, and R4 model adapter  
**Outputs:**

- Deterministic rule combining Poka-Yoke status, AI confidence, and image-quality checks into PASS / FAIL / RECHECK.
- Mock GPIO adapter for development and Orange Pi GPIO adapter for target execution.
- Safe-state behavior for camera loss, invalid frames, pipeline stalls, and GPIO errors.
- Watchdog events visible in the audit log and HMI.

**Done when:** Every result path and failure path produces the agreed light/buzzer state and a complete audit event without directly coupling business logic to GPIO code.

### Work Package R6 - Backend and Audit Trail

**Primary owner:** Riya  
**Dependencies:** R0 event schema and R5 decision output  
**Outputs:**

- FastAPI routes for health, current inspection, history, failed-frame detail, settings, and operator review.
- WebSocket event stream for live inspection state and alerts.
- SQLite schema and migration for inspection events, operator corrections, settings, and device health.
- Bounded image retention and graceful handling of missing image files or database corruption.

**Done when:** A replayed inspection appears in SQLite and on the WebSocket, operator correction is preserved as retraining data without overwriting the original decision, and restart does not lose committed events.

### Work Package R7 - Touchscreen HMI

**Primary owner:** Riya  
**Dependencies:** Stable R6 API/WebSocket contract  
**Outputs:**

- Live camera panel and large PASS / FAIL / RECHECK banner.
- Connection/camera/watchdog status, failed-frame history, inspection detail, yield, and defect-trend charts.
- Guarded threshold and brightness settings with current values and validation.
- Touch-first layout with large targets, high contrast, and a useful disconnected/reconnecting state.

**Done when:** The HMI operates against both mock and live backend data, remains understandable when the camera/backend is unavailable, and the core workflow works at the intended touchscreen resolution.

### Work Package R8 - Validation, FMEA, Evidence, and Submission

**Accountable:** Akash  
**Riya's responsibility:** Consolidate software evidence and co-produce FMEA and the final deck  
**Outputs:**

- KPI evidence folders containing raw logs, summary tables, plots, and the exact commit/model/config used.
- FMEA entries for lighting drift, sensor drift, power drop, camera loss, overheating, pipeline stall, storage exhaustion, model uncertainty, and incorrect operator correction.
- Software architecture/data-flow diagram aligned with the electrical master interconnect at the GPIO boundary.
- Maker-journey screenshots showing source trees, training, benchmark output, backend tests, database records, and HMI states.
- `submission/slide_content_map.md`, final deck, references, and external links.

**Done when:** Every quantitative slide claim links to reproducible evidence, native files remain in the repository or an explicitly documented large-file store, and the deck consistently describes the COTS under-₹10k Stage 2 design.

## 6. Team Dependencies That Riya Must Drive Early

| Needed from | Dependency | Needed by | Latest useful point |
|---|---|---|---|
| Rudra/Akash | Camera height, field of view, cowl opening, lighting position, enclosure volume, and thermal path | Dataset rig, ROI, HMI camera assumptions, thermal telemetry | Before R1/R2 freeze |
| Aratrik | 5V/12V rails, GPIO isolation topology, input/output active levels, safe state | R0 and R5 | Before the I/O adapter is implemented |
| Kartikay | Trigger sensor behavior, debounce interval, tower-light/buzzer truth table, PWM range | R0 and R5 | Before decision-engine integration |
| Entire team | Costed BOM with supplier links | Scope and final validation | End of Week 1, not at presentation time |
| Akash | Orange Pi 5 and RKNN environment access | R4 | Before Week 3 |

## 7. Four-Week Relative Schedule

### Week 1 - Freeze and Prove the Skeleton

- Resolve the conflicts in Section 2 and complete the missing roadmap.
- Create the full repository structure and contribution/evidence rules.
- Freeze event, API, GPIO, and geometry interfaces.
- Start the dataset card, label guide, split manifests, and BOM supplier sheet.
- Demonstrate a mocked end-to-end slice from recorded image to HMI.

**Gate:** Scope, contracts, cost direction, and the thin vertical slice are approved.

### Week 2 - Build Independent Evidence-Producing Subsystems

- Complete the deterministic vision baseline and dataset quality audit.
- Train and compare the lightweight model candidates.
- Build the FastAPI/SQLite/WebSocket core and HMI workflow against mocks.
- Mechanical team produces native parts/master assembly draft; electrical team produces four schematic drafts and ERC results.

**Gate:** FP32 evaluation is reproducible, backend/HMI handles real event shapes, and CAD/electrical interfaces still match R0.

### Week 3 - Target Deployment and Cross-Domain Integration

- Export ONNX, compile RKNN INT8, benchmark on Orange Pi 5, and integrate inference.
- Lock decision thresholds from held-out evidence.
- Integrate the GPIO adapter with the reviewed pinout and safe states.
- Complete master CAD assembly, exploded view, FEA, thermal calculation, schematics, and master interconnect.
- Reconcile the BOM against the under-₹10k target.

**Gate:** All six KPI folders contain preliminary evidence. Any red KPI has an owner and recovery decision.

### Week 4 - Audit and Submission

- Run the final held-out model evaluation and end-to-end latency benchmark.
- Complete FMEA, standards checklist, and Stage 3 plan.
- Capture maker-journey evidence and verify timestamps/native files.
- Build the final slide deck from the slide-content map.
- Conduct three reviews: technical consistency, claim-to-evidence traceability, and presentation clarity.

**Gate:** Submission audit passes and the repository state can reproduce every software claim.

## 8. KPI Acceptance Checklist

- [ ] Itemized COTS BOM totals under ₹10,000 with current supplier evidence and excludes no required subsystem.
- [ ] Trigger-to-decision latency is ≤100 ms on Orange Pi 5; per-stage latency is logged.
- [ ] Heavy-burr recall is >95% on a real held-out, part-separated test set.
- [ ] False-reject and defect-escape rates are reported, even if the team has not set formal thresholds.
- [ ] SolidWorks FEA reports FoS >2.0 for documented 50 N and 100 N load cases, with mesh and fixture evidence.
- [ ] Thermal calculation supports SoC <65°C at 45°C ambient and identifies assumptions.
- [ ] Every external GPIO channel shown in software is opto-isolated in the KiCad design.
- [ ] Camera loss, invalid image, low confidence, and stalled pipeline result in RECHECK/safe-state behavior rather than PASS.
- [ ] Native `.SLDPRT`, `.SLDASM`, and `.kicad_sch` files and their audit history are preserved.
- [ ] Screenshots, benchmark logs, references, and slide assets are mapped to the final presentation.

## 9. Risks and Controls

| Risk | Early control |
|---|---|
| Required hardware cannot fit under ₹10,000 | Cost the mandatory BOM in Week 1; treat supplier pricing as a design input |
| Real burr data is unavailable or too small | Secure one part/defect source immediately; keep synthetic data out of the final held-out set |
| Orange Pi/RKNN access arrives late | Build ONNX and mocked-runtime paths first, but reserve target hardware time before Week 3 |
| Mechanical, electrical, and software interfaces drift | Version one shared interface table and require review for changes |
| Riya/Akash software scope is too broad | Preserve the vertical slice; defer extra charts, PostgreSQL, cloud, Modbus, multi-part models, and anomaly experiments |
| Audit trail is weak | Commit small increments with native files and evidence; do not bulk-upload at the end |
| Concept PDF claims leak into the new design | Run a terminology/cost/scope consistency check across the deck before submission |

## 10. Immediate Next 48 Hours

- [ ] Confirm the actual deadline and false-reject target.
- [ ] Approve the authoritative-scope hierarchy and the six conflict decisions.
- [ ] Create the repository skeleton and move/copy the three Markdown source documents into `docs/`.
- [ ] Complete `roadmap.md`, `design_decisions.md`, `references.md`, `CONTRIBUTING.md`, and `slide_content_map.md` stubs.
- [ ] Hold a 30-minute interface review with all five members and publish the camera/GPIO/event contracts.
- [ ] Select the exact part and heavy-burr acceptance definition; start the dataset card and labeling guide.
- [ ] Create a costed mandatory BOM with supplier links before locking component choices.
- [ ] Build the replay-driven thin vertical slice with mock inference and mock GPIO.

## 11. Explicitly Deferred to Stage 3

- Physical prototype fabrication and conveyor installation
- Shop-floor or MSME field validation
- Shadow-mode comparison against human inspectors
- Production-line rejection/control authority
- Custom PCB unless Stage 2 time remains after required schematics
- Cloud and multi-factory dashboards
- PostgreSQL migration, RS485/Modbus integration, and multi-part/multi-defect expansion
