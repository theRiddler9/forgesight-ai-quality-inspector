# Riya's ForgeSight Stage 2 Execution Workflow

**Owner:** Riya  
**Scope:** Dataset, computer vision, model deployment, decision logic, backend, HMI, integration evidence, and submission support  
**Master plan:** [`../forgesight-stage2-work-plan.md`](../forgesight-stage2-work-plan.md)  
**Current phase:** Gate 0 - scope, contracts, and repository foundation

## Outcome

**Recorded-image slice update (2026-10-17):** A repeatable synthetic virtual slice now exercises the edge pipeline, canonical SQLite event, API/WebSocket, and HMI. Automated tests cover all six decisions and mock I/O; Chrome Playwright tests verify the rendered operator journey, reconnection, reviews, metrics, and restart persistence. Setup is in `software/README.md`, with screenshots in `evidence/recorded-image-slice/`. The gate dashboard below remains open because its real-image, model, hardware, timing, and submission acceptance conditions have not all been met. Teammate modules live in `software/edge/`, `software/backend/`, and `software/common/`; `software/inspection/` adapts them to the canonical event contract without replacing their history.

Deliver a reproducible Stage 2 virtual prototype that takes a recorded inspection image through Poka-Yoke and burr detection, returns PASS / FAIL / RECHECK, records the event in SQLite, publishes it through FastAPI/WebSocket, displays it in the HMI, and produces traceable evidence for the final submission.

The binding target is a COTS-first system under Rs 10,000, focused first on heavy burrs, with end-to-end trigger-to-decision latency at or below 100 ms. Physical fabrication and shop-floor testing belong to Stage 3.

## Status Dashboard

Use: `Not started`, `Active`, `Blocked`, `Review`, or `Done`.

| Gate | Work package | Status | Depends on | Exit evidence |
|---|---|---|---|---|
| 0 | R0 - Repository and contracts | Active | Deadline and KPI decisions | Approved interfaces, event schema, folder skeleton, thin-slice plan |
| 1 | R1 - Dataset foundation | Not started | Camera, lighting, part, and burr definition | Dataset card, manifests, labels, part-separated splits |
| 2 | R2 - Deterministic vision | Not started | Gate 1 sample set | Replayable Poka-Yoke tests and timing report |
| 3 | R3 - Model training/evaluation | Not started | Gate 1 complete | Reproducible baseline, metrics, errors, frozen checkpoint |
| 4 | R4 - ONNX/INT8/RKNN deployment | Not started | Gate 3 checkpoint | Accuracy delta and Orange Pi benchmark logs |
| 5 | R5 - Decision engine and I/O | Not started | Gates 2 and 4; electrical pinout | Tested decisions, mock GPIO, watchdog, safe state |
| 6 | R6 - Backend and audit trail | Not started | Event schema from Gate 0 | API tests, SQLite records, WebSocket replay |
| 7 | R7 - Touchscreen HMI | Not started | Stable API from Gate 6 | Operator-flow recording and error-state evidence |
| 8 | R8 - Validation and submission | Not started | Gates 0-7 plus team artifacts | KPI matrix, FMEA, evidence index, slide assets |

## Gate 0 - Freeze the Foundation

Complete this gate before parallel implementation starts.

**Progress:** 6 of 11 items complete. The remaining five require team decisions or cross-discipline approval.

- [ ] Confirm the exact Stage 2 submission deadline with the team.
- [ ] Agree on the maximum acceptable false-reject rate.
- [ ] Freeze the selected part type and define what counts as a heavy burr.
- [x] Create the repository folders defined in the master plan.
- [x] Add `roadmap.md`, `design_decisions.md`, `references.md`, and `CONTRIBUTING.md`.
- [x] Record why the current plan uses an under-Rs-10,000 COTS enclosure instead of the older Rs-15,000 custom concept.
- [x] Define the canonical inspection event: timestamp, part ID, result, defect, confidence, Poka-Yoke results, stage timings, temperature, image reference, and review fields.
- [ ] Freeze the GPIO/I/O table with Aratrik and Kartikay: trigger, stack light, buzzer, ring-light PWM, active levels, timeouts, and safe state.
- [ ] Freeze camera height, field of view, mounting envelope, and lighting assumptions with Akash, Rudra, and Kartikay.
- [x] Define where every native artifact, export, log, screenshot, and slide asset belongs.
- [x] Write the thin vertical-slice acceptance test using recorded images and mocked GPIO.

**Gate 0 acceptance:** The team can implement independently without guessing an interface, and Riya can trace one mocked inspection from input through an event record to the HMI contract.

## Gate 1 - Build the Dataset Foundation

- [ ] Create `software/dataset/DATASET_CARD.md`.
- [ ] Record image provenance, permission/licensing, selected part, burr definition, capture conditions, class balance, and limitations.
- [ ] Create raw, annotation, augmentation, and split manifests.
- [ ] Write a labeling guide with positive, negative, ambiguous, occluded, and edge-case examples.
- [ ] Separate training, validation, and test data by physical part, not by image.
- [ ] Keep a real-image holdout set that synthetic or augmented images never enter.
- [ ] Reserve at least 200 representative images for INT8 calibration.
- [ ] Run label-quality checks and review disagreements with Akash.
- [ ] Save dataset version, manifest hash, and class counts with each training run.

**Gate 1 acceptance:** Another team member can reconstruct the exact dataset split and understand every inclusion, exclusion, and known bias.

## Gate 2 - Establish the Deterministic Baseline

- [ ] Build a folder-based image replay runner before connecting a live camera.
- [ ] Implement part-present, position, orientation, hole-presence, and size/range checks.
- [ ] Put thresholds and regions of interest in versioned configuration.
- [ ] Add synthetic or fixture-based unit tests for each rule.
- [ ] Evaluate the real holdout and record false PASS, false FAIL, and RECHECK cases.
- [ ] Log per-stage latency and save annotated output images.
- [ ] Define when a failed image-quality or geometry check must produce RECHECK instead of FAIL.

**Gate 2 acceptance:** The same input set produces repeatable rule outputs, annotated evidence, and a timing report from a clean checkout.

## Gate 3 - Train and Evaluate the Burr Detector

- [ ] Pin the Python environment and record package versions.
- [ ] Add a reproducible training configuration and command.
- [ ] Train a small YOLO baseline focused on heavy burrs.
- [ ] Record dataset version, seed, input size, augmentation, epochs, checkpoint, and hardware.
- [ ] Report precision, recall, F1, mAP, confusion matrix, and per-image latency.
- [ ] Inspect false positives and false negatives; group them by cause.
- [ ] Compare performance on real holdout images against augmented/synthetic images.
- [ ] Select and freeze the checkpoint using the agreed acceptance rule, not the training-set score.

**Gate 3 acceptance:** The chosen model is reproducible, heavy-burr recall is reported honestly on the held-out set, and failure cases are documented.

## Gate 4 - Export and Benchmark on Orange Pi 5

- [ ] Export the frozen checkpoint to ONNX.
- [ ] Verify ONNX outputs against the PyTorch model on a fixed comparison set.
- [ ] Compile an INT8 RKNN model using the reserved calibration images.
- [ ] Measure FP32-to-ONNX-to-INT8 accuracy changes.
- [ ] Benchmark preprocessing, NPU inference, postprocessing, decision, and total time separately.
- [ ] Run a sustained benchmark and log temperature, throttling, failures, and memory use.
- [ ] Store the exact export/compile commands, toolkit version, board image, and benchmark logs.

**Gate 4 acceptance:** The RKNN artifact is reproducible and the report shows whether accuracy and total latency meet the agreed KPI.

## Gate 5 - Integrate Decisions, I/O, and Safety

- [ ] Define PASS, FAIL, and RECHECK thresholds in configuration.
- [ ] Combine Poka-Yoke and model outputs in one deterministic decision table.
- [ ] Implement an I/O adapter with a mock backend first and hardware GPIO second.
- [ ] Add trigger debounce, duplicate-trigger prevention, inspection timeout, and camera/model error handling.
- [ ] Add a watchdog and verify the agreed safe output state.
- [ ] Test every decision-table branch and every output transition.
- [ ] Save decision traces that reference the source image and model/config versions.

**Gate 5 acceptance:** Automated tests prove every result and fault path, including timeout and safe-state behavior, without requiring physical hardware.

## Gate 6 - Build the Backend and Audit Trail

- [ ] Implement the canonical event schema as the shared software contract.
- [ ] Create SQLite migrations and indexes.
- [ ] Build endpoints for inspection, history, summary metrics, health, configuration, and review.
- [ ] Publish live inspection events over WebSocket.
- [ ] Preserve image/model/config traceability in every stored event.
- [ ] Add API, database, and WebSocket tests using fixed replay data.
- [ ] Verify recovery after process restart and malformed input.

**Gate 6 acceptance:** A replayed inspection creates exactly one auditable database event, one API-visible record, and one live WebSocket update.

## Gate 7 - Complete the Operator HMI

- [ ] Implement live status and PASS / FAIL / RECHECK display.
- [ ] Show the inspection image with defect and Poka-Yoke overlays.
- [ ] Add yield, defect trend, recent history, and health/temperature views.
- [ ] Add operator review for RECHECK events with an audit note.
- [ ] Design clear disconnected, camera-error, model-error, no-part, and safe-state screens.
- [ ] Test the primary flow at the target touchscreen resolution.
- [ ] Record a complete replay-driven operator journey.

**Gate 7 acceptance:** A reviewer can understand system state, inspect a result, review a RECHECK, and recognize every major fault without opening developer tools.

## Gate 8 - Validate, Reconcile, and Package the Submission

- [ ] Create one KPI matrix linking each claim to a file, command, log, screenshot, or calculation.
- [ ] Complete software, integration, electrical, mechanical, and operator FMEA entries with the relevant owners.
- [ ] Reconcile camera geometry, mounts, cable routes, power, pinout, BOM, software configuration, and diagrams.
- [ ] Confirm the itemized COTS BOM stays under Rs 10,000.
- [ ] Separate Stage 2 virtual evidence from the Stage 3 physical-test plan.
- [ ] Build an evidence index with native source, export, validation result, screenshot, and commit reference.
- [ ] Map every presentation claim to its evidence source.
- [ ] Run a clean-checkout reproduction and final demo rehearsal.

**Gate 8 acceptance:** Every headline claim is backed by traceable evidence, no subsystem interface conflicts remain, and the final demo can be reproduced from documented steps.

## Daily Operating Loop

Use this loop on every workday:

1. Select one gate deliverable that unblocks the critical path.
2. State its acceptance check before implementation.
3. Identify the evidence to save: source, test, log, screenshot, export, or benchmark.
4. Implement the smallest demonstrable slice.
5. Run the relevant test or replay immediately.
6. Save evidence in its permanent repository location.
7. Commit with the work-package ID, for example `R2: add position-check replay test`.
8. Update this dashboard and record blockers before stopping.

### End-of-Day Entry

```text
Date:
Active gate:
Completed:
Evidence saved:
Test/benchmark result:
Blocker and owner:
First task tomorrow:
```

## Weekly Review

At the end of each week:

- [ ] Demo one end-to-end improvement from recorded input to visible result.
- [ ] Compare actual KPI results with targets; do not report estimates as measurements.
- [ ] Review interface changes with affected owners before merging them.
- [ ] Check that native files, logs, and screenshots exist for each completed item.
- [ ] Move unfinished work forward explicitly; do not mark partial work done.
- [ ] Update risks, decisions, and the next week's critical path.

## Blocker Rules

When another subsystem is late or undecided:

1. Record the blocker, owner, date raised, decision needed, and impact.
2. Use the last approved interface or a versioned mock; label the assumption clearly.
3. Continue work that does not depend on the unresolved decision.
4. Re-run the affected acceptance tests when the real interface arrives.

Do not silently invent camera dimensions, GPIO levels, power behavior, defect definitions, or acceptance thresholds.

## Immediate Next 48 Hours

- [ ] Finish Gate 0 team decisions: deadline, false-reject target, selected part, and heavy-burr definition.
- [ ] Create the repository skeleton and ownership files.
- [ ] Draft the inspection-event schema and electrical I/O table for review.
- [ ] Define the recorded-image-to-HMI vertical-slice test.
- [ ] Start the dataset card and labeling guide using the approved part and defect definition.

## Final Definition of Done

Riya's Stage 2 lane is done only when:

- A clean checkout can replay an inspection end to end.
- The dataset, training, export, and benchmark chain is reproducible.
- PASS / FAIL / RECHECK and all fault paths are tested.
- Each event is auditable through SQLite, API, WebSocket, and HMI.
- KPI claims point to real Stage 2 evidence.
- Physical tests are described as Stage 3 plans, not claimed as completed Stage 2 results.
