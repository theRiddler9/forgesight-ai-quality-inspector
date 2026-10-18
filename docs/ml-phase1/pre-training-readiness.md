# Pre-training readiness (2026-10-18)

## Gate and dependency order

**CONDITIONALLY READY — external data and approvals required.** The software can intake, audit, annotate, split, export, and preflight a future real dataset. No licensed, component-matched heavy-burr dataset or approved physical component/tolerance has been established. The provisional `metal-plate-v1@1.0.0` remains a simulated replay profile and deliberately fails real-training preflight. No ForgeSight model has been trained or evaluated.

| Prerequisite | State | Evidence or next dependency |
| --- | --- | --- |
| Versioned profile, fingerprint, geometry, ROI, image contract, thresholds | Implemented and tested | `software/profiles/`; plate profile is provisional and uncalibrated. Profile changes cannot silently omit required checks. |
| Local licensed-data intake, integrity, provenance, immutable raw copy, audit | Implemented and tested with synthetic files | `software/dataset/intake.py`; team must approve rights and provide real captures. |
| Reviewed annotations, duplicate checks, grouped frozen splits, YOLO export | Implemented and tested with synthetic files | `software/dataset/`; part/session IDs and independent annotation review require human capture practice. Near duplicates need human inspection. |
| Deterministic decode, ROI, orientation, letterbox, box transforms | Implemented and tested | `software/ml/preprocessing.py`; calibrate against the selected camera and component before deployment. |
| Training preflight and explicit optional runner | Implemented, preflight tested | `software/ml/training/`; optional Ultralytics runner and actual training remain unexecuted. Team must approve its AGPL terms and training configuration. |
| Evaluation arithmetic and validation-only threshold sweep | Implemented and tested on synthetic records | `software/ml/evaluation.py`; actual performance is unknown until reviewed real predictions exist. |
| Model manifest/hash/compatibility checks | Implemented and tested | `software/ml/model_manifest.py`; ONNX/RKNN inference is intentionally unavailable. |
| Real heavy-burr training/evaluation dataset | **External blocker** | No verified plate heavy-burr dataset; see [candidate review](dataset-candidates.md). |
| Approved component, physical reject criteria, licensing, held-out review | **Team decisions** | Obtain the physical part, edge examples, tolerances, usage rights, capture plan, and independent label review. |
| Real model training, ONNX parity, RKNN/Orange Pi latency and electrical integration | **Later phases** | Requires approved data/model or hardware. The simulator does not verify these. |

The existing replay contract and six scenarios remain the regression baseline. A future model can use the detector boundary without changing the shared decision or audit event structure, but it **cannot be activated** by a manifest alone: runtime adapter implementation and model validation are still required. Missing, incompatible, or unavailable models remain non-PASS.

## Windows setup and commands

Use Python 3.10+ (the supported backend minimum) from the repository root. `software/requirements-dev.txt` constrains the software-test dependencies; it is not a full environment lock. Install the optional training dependency only in a separate approved training environment: `python -m pip install -r software/requirements-ml.txt`. The Ultralytics package currently advertises AGPL-3.0; resolve licensing before any commercial use. Do not use the guarded `train --execute-training` action until data, profile, licensing, and preflight are approved.

Keep images, labels, generated manifests, exports, training runs, and model weights under ignored `data/` or another controlled untracked location. These examples use `data/datasets/v1` and are illustrative; obtain explicit rights before importing third-party images.

```powershell
python -m software.dataset import data/incoming/approved-capture --output data/datasets/v1 --dataset-version 1.0.0 --profile metal-plate-v1@1.0.0 --source-name team-capture --source-license team-owned --capture-session session-01 --dry-run
# After inspecting the dry-run report, repeat without --dry-run to create a new immutable destination.
python -m software.dataset validate data/datasets/v1/manifest.json
python -m software.dataset report data/datasets/v1/manifest.json --group-by physical_part_id
python -m software.dataset split data/datasets/v1/manifest.json --group-by physical_part_id --seed 42 --fractions 0.7 0.15 0.15 --output data/datasets/v1/split-manifest.json
python -m software.dataset export-yolo data/datasets/v1/split-manifest.json --class-map data/datasets/v1/class-map.json --output data/datasets/v1/yolo-export --dry-run
python -m software.ml.training preflight data/training/approved-config.json
python -m software.ml.evaluation data/evaluation/reviewed-predictions.json --split validation --positive-class heavy_burr --thresholds 0.5 0.7 0.9
```

Import creates a manifest with provisional review status. Add canonical JSON annotations, class mapping, part/batch/session identities and independent reviews before export. Clean images require an explicit empty `boxes` list. A split manifest cannot be silently regenerated; create a new dataset version to change assignments. The class map and training configuration must match a **new versioned, real-model** component profile. `metal-plate-v1@1.0.0` is intentionally unsuitable for real-training preflight. Validation selects thresholds; the held-out test set is for final evaluation only. Neither the dry run nor preflight starts training.

## Model adoption boundary

Create a new immutable profile version for the selected physical component, camera geometry, calibration, preprocessing, classes, thresholds, and model metadata. Record the model artifact and SHA-256 in a model manifest; `verify_model_artifact` checks profile and artifact identity. Change model versions by adding a new profile/model manifest pair and validating it, never by replacing a historical artifact in place. Implement and test the real runtime adapter, output mapping, decision behavior, ONNX/RKNN parity where applicable, and physical safety before enabling real inspections. Audit events retain the profile/configuration identity used at inspection time.

See [component profiles](component-profiles.md), [dataset and annotation rules](dataset-and-annotations.md), and the [evaluation protocol](evaluation-protocol.md). The UI and recorded-image demo continue to label synthetic images, simulated burr decisions, and mock I/O explicitly.
