# RKNN Benchmark Harness Implementation Plan

> **For agentic workers:** This plan is scoped to an independent benchmark utility. The trained burr model, calibration set, RKNN conversion, and Orange Pi results remain gated on the model owner and target hardware.

**Goal:** Add a reusable local harness that measures warmup and repeated inference calls and writes a transparent JSON timing report.

**Architecture:** A framework-neutral Python function accepts a callable and in-memory frames, times each measured call with a monotonic high-resolution clock, and returns raw samples plus summary statistics and host metadata. The harness does not load models or claim target-board performance.

**Tech Stack:** Python standard library and existing NumPy frame type conventions.

**Spec:** `docs/forgesight-stage2-work-plan.md`, Work Package R4.

## Global Constraints

- Keep inspection decisions in the shared edge decision engine.
- Separate inference timing from trigger-to-decision timing.
- Record exact run parameters and environment metadata; do not present development-host results as Orange Pi evidence.
- Do not add a model artifact or calibration data before Riya's handoff.

## Review Focus

- Empty frame input must fail clearly instead of producing an empty report.
- Invalid warmup or repetition counts must fail before invoking the callable.
- Inference exceptions must propagate; partial timing reports must not appear successful.
- Percentile calculation must be deterministic for small sample counts.
- Report writing must preserve raw samples and identify the requested target label as metadata only.

---

### Task 1: Add a reusable inference timing harness

**Files:**
- Create: `software/ml/benchmarks/runner.py`
- Create: `software/ml/benchmarks/__init__.py`
- Create: `software/ml/benchmarks/environment.py`
- Create: `software/ml/benchmarks/report.schema.json`
- Create: `software/ml/benchmarks/README.md`
- Modify: `software/ml/benchmarks/runner.py` to record artifact identity and runtime telemetry.

**Interfaces:**
- `benchmark_inference(infer, frames, *, warmup_runs, repetitions, model_id, target_label) -> dict`
- `write_report(report, output_path) -> None`

- [x] Validate input and count parameters before execution.
- [x] Run warmups without including them in measured samples.
- [x] Time one callable invocation per measured sample using `perf_counter_ns`.
- [x] Include raw millisecond samples, mean, median, nearest-rank p95, min, max, UTC time, run parameters, and Python/platform metadata.
- [x] Optionally hash a model artifact before and after the run; fail if it changes.
- [x] Record runtime package versions and real SoC temperature samples when available.
- [x] Define the JSON report shape without changing shared inspection contracts.
- [x] Document that artifact loading, calibration, accuracy evaluation, and Orange Pi/RKNN execution are later handoff work.
- [x] Review the diff and run a syntax check; automated tests are not part of this task unless requested.

### Task 2: Add local CLI and run summary

**Files:**
- Create: `software/ml/benchmarks/cli.py`
- Create: `software/ml/benchmarks/__main__.py`
- Create: `software/ml/benchmarks/summarize.py`
- Modify: `software/ml/benchmarks/README.md`

**Interfaces:**
- `python -m software.ml.benchmarks` loads a local adapter factory and `.npy` frames.
- `python -m software.ml.benchmarks.summarize` recomputes summary statistics from one or more report files and writes CSV.

- [x] Keep adapter loading local and explicit through `module.path:factory`.
- [x] Keep target labels descriptive only and retain missing telemetry as null.
- [x] Recompute CSV statistics from raw samples; do not treat timing as an accuracy or KPI verdict.
- [x] Run Python syntax checks, JSON syntax check, CLI help check, and whitespace check.
