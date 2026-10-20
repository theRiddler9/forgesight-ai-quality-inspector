# RKNN Export Validation Plan

> **For agentic workers:** Execute this plan in small verified commits. Real model approval, INT8 calibration, RKNN compilation, and Orange Pi measurements remain handoff and hardware gates.

**Goal:** Add a deterministic preflight validator for exported ONNX graphs before they are registered for the profile-aware detector or converted to RKNN.

**Architecture:** Inspect the ONNX graph statically, compare its tensor contract against the existing immutable model manifest and component profile, verify the artifact hash, and emit a machine-readable report. The validator does not run inference, train a model, or claim accuracy or NPU performance.

**Tech Stack:** Python, ONNX graph metadata, existing Pydantic manifests/profiles, JSON reports, pytest.

**Spec:** `docs/ml-phase1/onnx-integration.md`, `docs/ml-phase1/pre-training-readiness.md`, Work Package R4 in `docs/forgesight-stage2-work-plan.md`.

## Global Constraints

- Keep inspection decisions in the shared edge decision engine.
- Do not activate an artifact solely because its JSON manifest parses.
- Preserve exact artifact hash, profile identity, preprocessing identity, and graph tensor metadata.
- Do not claim RKNN, Orange Pi, latency, thermal, or defect-accuracy evidence from static validation.

## Review Focus

- Missing or malformed ONNX graphs must fail with a controlled validation error.
- Dynamic, wrong-rank, wrong-dtype, wrong-channel, and mismatched-size tensors must be rejected.
- Output channel count must equal `4 + len(class_map)` and candidate count must be bounded.
- Manifest/profile/artifact identity mismatches must be reported before registration.
- Validation reports must be stable JSON and distinguish static validation from runtime/hardware evidence.

### Tasks

- [ ] Add graph inspection and validation library with focused unit tests.
- [ ] Add a CLI that loads profile/manifest/model root and writes a validation report.
- [ ] Add report schema and documentation with exact handoff commands and evidence limits.
- [ ] Run the full Python suite, optional ONNX fixture tests, and dependency checks.
