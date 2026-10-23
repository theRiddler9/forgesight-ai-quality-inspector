# Real burr acquisition and edge handoff

## Evidence gate before training

No component-matched, licensed, independently reviewed heavy-burr image set is
available in this checkout. The provisional `metal-plate-v1@1.0.0` profile and
deterministic ONNX graph are software fixtures. They cannot establish detection
accuracy or a physical acceptance threshold. Do not train or promote a detector
using generic scratches relabeled as burrs.

The team and manufacturing partner must first approve the physical component,
which edge regions matter, the physical reject criterion, and how an ambiguous
observation should be handled. Capture representative *real* parts in a fixed
camera/fixture geometry. Record camera and lens identity, focus, distance,
resolution, exposure, illumination positions and settings, ambient light,
orientation, calibration reference, capture session, part and batch identity,
and image SHA-256. Keep the raw images immutable in ignored storage. Include
known acceptable edges, confirmed rejectable heavy burrs, borderline and
occluded edges, geometry failures, and realistic lighting and surface-finish
variation. Obtain physical measurements or adjudication where the reject
criterion needs them; RGB appearance alone does not provide burr height.

Use the [canonical annotation guide](dataset-and-annotations.md) for visible
boxes. Save empty annotations for reviewed clean images, and record uncertain
examples explicitly rather than forcing PASS or FAIL. Have independent reviewers
adjudicate disputed labels and keep their decisions. Verify image rights and
redistribution terms before import. Split by physical part, capture session,
and exact duplicate groups; inspect near duplicates and unknown identities
manually. Freeze a held-out test set before threshold selection. The required
sample size and acceptable confidence interval need team approval based on the
desired heavy-burr recall claim; no count is asserted here. Use validation data
to select thresholds and report test-set recall with the independent heavy-burr
count and interval. The dataset CLI commands are in
[dataset and annotations](dataset-and-annotations.md), and training preflight
commands are in [pre-training readiness](pre-training-readiness.md).

## Captured ONNX/RKNN output comparison

```powershell
python -m software.ml.parity `
  --onnx data/comparison/onnx-capture.json `
  --rknn data/comparison/rknn-capture.json `
  --tolerances data/comparison/approved-tolerances.json `
  --output data/comparison/parity-report.json
```

This command compares **saved records only**. It does not load an ONNX
or RKNN runtime, attest to the producer of either record, or approve the chosen
tolerances. Keep captures and reports outside Git, for example under `data/`.
The CLI returns 0 for matching records and 1 for a recorded mismatch. Invalid
records or missing files produce a command error. Its report includes hashes of
the three input JSON files and `hardware_verified: false` and
`approval_assessed: false` even when its numeric comparison passes.

Each capture JSON has this versioned shape (hashes below are placeholders that
must be replaced with real SHA-256 values):

```json
{
  "schema_version": "1.0.0",
  "backend": "onnx",
  "model_artifact_sha256": "<64 lowercase hex characters>",
  "profile_fingerprint": "<64 lowercase hex characters>",
  "preprocessing_fingerprint": "<64 lowercase hex characters>",
  "comparison_set_id": "frozen-real-comparison-v1",
  "class_map": {"heavy_burr": 0},
  "decoder_contract": "yolo11_raw_v1",
  "output_shape": [1, 5, 100],
  "frames": [{
    "image_id": "part-001-view-1",
    "image_sha256": "<64 lowercase hex characters>",
    "image_width": 1280,
    "image_height": 800,
    "decision": "RECHECK",
    "detections": [{
      "class_name": "heavy_burr",
      "confidence": 0.7,
      "bbox": [20.0, 30.0, 35.0, 45.0]
    }]
  }]
}
```

The RKNN record uses `"backend": "rknn"` and its own artifact hash. Both
records must declare the same comparison-set ID, profile/preprocessing
fingerprints, class map, decoder contract, frame IDs, image hashes, and image
dimensions. `output_shape` is the *raw* YOLO output tensor `[1,4+C,N]`, while
boxes are decoded original-image `x1,y1,x2,y2` pixels. Capture the same real
frames through the same preprocessing and decoder, with a frozen model export
lineage. The tool rejects unsupported shapes and coordinates outside the frame.
It finds one-to-one detection matches by class, absolute confidence difference,
absolute box-coordinate difference, and IoU, then checks the final inspection
decision. The tolerances JSON must explicitly supply `confidence_abs_max`,
`bbox_abs_px_max`, and `min_iou`; there are no silent defaults. The manufacturing
and model owners must approve these numerical limits for the actual precision,
quantization, and reject risk. Matching records alone cannot establish runtime
parity, because the records and hashes are self-reported. Preserve raw runtime
logs, immutable frame and model artifacts, capture code/version, and review
evidence for the eventual board trial.

## Conversion and board validation boundary

After an approved model and real calibration/comparison images exist, validate
the ONNX graph against the exact profile and manifest using
`python -m software.ml.export` as documented in
[ONNX integration](onnx-integration.md). Select a RKNN Toolkit2 release that
supports the actual Linux conversion host and RK3588S target; record the toolkit
version and conversion flags. Confirm model input layout, color/scale contract,
output tensor layout, quantization method, calibration image provenance, and
artifact hash. Review converter logs and reject unsupported output contracts.
Do not use the adapter-test ONNX graph as the production model.

On the Orange Pi 5, record board identity, OS/kernel, RKNN runtime and NPU
identity, model and profile hashes, ambient conditions, and actual output
captures. Only then run paired ONNX/RKNN comparisons on the frozen real set.
The host-side comparison command above is one analysis aid, not an execution
receipt. Use the benchmark harness for measured latency with explicit timing
scope and warmup exclusion. Measure sustained temperature and throttling on the
board; the 65°C target at 45°C ambient is unverified unless that ambient is
actually measured. Do not promote a model to production approval based solely
on a static contract check, captured parity report, or desktop benchmark.
