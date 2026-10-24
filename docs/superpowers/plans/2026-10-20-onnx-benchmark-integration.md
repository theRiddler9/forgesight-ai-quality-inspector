# ONNX Benchmark Integration Plan

> **For agentic workers:** Execute this plan task by task with the inline implementation workflow. The trained model, calibration set, RKNN compilation, and Orange Pi measurements remain gated on approved handoffs and hardware.

**Goal:** Connect the merged profile-aware ONNX detector to the benchmark report workflow and add automated regression coverage for the existing benchmark tools.

**Architecture:** Keep the generic callable timing primitive intact. Add a dedicated ONNX command that loads an existing component profile and model manifest, validates BGR8 NumPy frames against the profile, runs the existing `OnnxDetector`, and writes the same provenance-rich benchmark report. Add focused tests for runner, telemetry, generic CLI, summarizer, and ONNX command behavior.

**Tech Stack:** Python, NumPy, pytest, JSON Schema, existing Pydantic profiles and ONNX detector.

**Spec:** `docs/ml-phase1/onnx-integration.md`, `docs/ml-phase1/pre-training-readiness.md`, `docs/superpowers/plans/2026-10-19-rknn-benchmark-harness.md`.

## Global Constraints

- Keep inspection decisions in the shared edge decision engine.
- Separate inference timing from trigger-to-decision timing.
- Record exact run parameters and environment metadata; do not present development-host results as Orange Pi evidence.
- Do not add a model artifact or calibration data before Riya's handoff.
- The test ONNX fixture is adapter test evidence only, never defect performance evidence.

## Review Focus

- Invalid repetitions, warmup counts, empty batches, or malformed frames must fail before reporting success.
- Inference errors and artifact changes must not produce a completed report.
- Host telemetry unavailable on Windows must serialize as null.
- Summary input patterns must work in PowerShell and reject malformed or schema-invalid reports.
- ONNX command must enforce profile dimensions and BGR8 dtype before creating the detector.
- Neither a target label nor ONNX execution alone establishes RKNN or Orange Pi performance.

---

### Task 1: Cover the timing primitive and environment collection

**Files:** Create `software/ml/tests/test_benchmark_runner.py`; create `software/ml/tests/test_benchmark_environment.py`.

**Interfaces:** Test the existing `benchmark_inference`, `write_report`, `collect_static_environment`, and `read_soc_temperature_c` interfaces without changing their public signatures.

- [x] Test warmup exclusion, cyclic frame selection, deterministic sample statistics, argument validation, exception propagation, artifact identity changes, strict JSON output, and unavailable telemetry.
- [x] Run the focused tests and commit each test module separately.

### Task 2: Cover the generic CLI and report summarizer

**Files:** Create `software/ml/tests/test_benchmark_cli.py`; create `software/ml/tests/test_benchmark_summarize.py`.

**Interfaces:** Exercise existing `main(argv)`, parser, adapter loader, `summarize_report`, and summarizer `main(argv)` through temporary files.

- [x] Cover explicit gray/BGR image and batch layouts, invalid dimensions/channels/dtypes, adapter loading, no report on failed inference, schema validation, raw-sample recomputation, wildcard expansion, and unmatched patterns.
- [x] Run the focused tests and commit each test module separately.

### Task 3: Add a profile-aware ONNX benchmark command

**Files:** Create `software/ml/benchmarks/onnx_cli.py`; create `software/ml/tests/test_onnx_benchmark_cli.py`; modify `software/ml/benchmarks/README.md`.

**Interfaces:** `python -m software.ml.benchmarks.onnx_cli --profile-catalog PATH --profile ID@VERSION --model-manifest PATH --model-root PATH --frames PATH --input-layout bgr|bgr-batch --target-label LABEL --warmup N --repetitions N --output PATH`.

- [x] Validate the manifest and selected profile, load `.npy` BGR8 frames with `allow_pickle=False`, check profile dimensions and layout, and benchmark `OnnxDetector.detect` through the shared runner.
- [x] Include the exact ONNX artifact in the existing report artifact identity field; never mark the report as target-verified based on `target-label`.
- [x] Test CLI validation and runner wiring with an isolated temporary profile/model bundle and a mocked detector; retain the existing optional runtime tests as the real ONNX execution check.
- [x] Document commands, input layout, report scope, and limits; run focused plus full Python test suites and commit code, tests, and docs as separate logical changes.
