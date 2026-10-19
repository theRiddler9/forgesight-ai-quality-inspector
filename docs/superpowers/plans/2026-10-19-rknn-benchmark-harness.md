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
- Create: `software/ml/benchmarks/README.md`

**Interfaces:**
- `benchmark_inference(infer, frames, *, warmup_runs, repetitions, model_id, target_label) -> dict`
- `write_report(report, output_path) -> None`

- [ ] Validate input and count parameters before execution.
- [ ] Run warmups without including them in measured samples.
- [ ] Time one callable invocation per measured sample using `perf_counter_ns`.
- [ ] Include raw millisecond samples, mean, median, nearest-rank p95, min, max, UTC time, run parameters, and Python/platform metadata.
- [ ] Document that artifact loading, calibration, accuracy evaluation, and Orange Pi/RKNN execution are later handoff work.
- [ ] Review the diff and run a syntax check; automated tests are not part of this task unless requested.
