# Local ONNX integration and handoff

This path executes an ONNX graph on the development CPU. It does **not** establish heavy-burr accuracy, ONNX/RKNN parity, Orange Pi latency, or physical acceptance criteria. The deterministic graph is an adapter test fixture, not a defect model.

## Optional installation and test fixture

Use Python 3.10+ from the repository root. Normal replay requires only `software/requirements-dev.txt`. For ONNX integration tests, install `python -m pip install -r software/requirements-onnx.txt` in an isolated environment. This optional file adds `onnxruntime` and `onnx`; dependency ranges are constrained but are not a complete environment lock.

```powershell
python -m software.ml.fixture_model data/onnx-adapter-test --bundle
python -m pytest software/ml/tests/test_onnx_adapter.py software/inspection/tests/test_local_onnx.py software/backend/tests/test_onnx_api.py -q
```

The command creates a new ignored directory with `catalog/`, `models/adapter-test.onnx`, and `model-manifest.json`. It refuses to overwrite an existing bundle. Its profile is `metal-plate-v1@9.0.0`, **provisional and test-only**; the usual `metal-plate-v1@1.0.0` replay profile remains the default. The fixture graph consumes `[1,3,64,64]` float32 RGB and emits one constant box and score through actual ONNX Runtime execution. These outputs have no defect meaning. The service forces RECHECK for this fixture when geometry passes.

## Inspect a local image

The CLI uses an explicitly supplied local file, profile catalog, and model manifest. It records the input hash and a safe source reference, not the file bytes or an arbitrary absolute path in SQLite.

```powershell
python -m software.inspection software/fixtures/images/clean.png --profile-catalog data/onnx-adapter-test/catalog --profile metal-plate-v1@9.0.0 --model-manifest data/onnx-adapter-test/model-manifest.json --model-root data/onnx-adapter-test/models --db data/onnx-adapter-test/audit.sqlite3
```

To enable the **loopback-only** upload API in a local backend, set `FORGESIGHT_PROFILE_CATALOG`, `FORGESIGHT_MODEL_MANIFEST`, and `FORGESIGHT_MODEL_ROOT` to those server-owned paths before `python -m software.backend`. Then send a PNG/JPEG/BMP body of at most 8 MiB to `POST /api/v1/inspections/image?profile_id=metal-plate-v1&version=9.0.0`. The request selects a registered profile; it cannot supply filesystem or model paths. The canonical event commits before WebSocket broadcast. The HMI displays the resulting test-only provenance, source hash, geometry, boxes, decision, and mock I/O state. No uploaded image preview is stored. Restarted clients recover events from SQLite history.

From `software/frontend`, run `npm run test:e2e` for the recorded replay suite. With the optional Python packages installed, set `FORGESIGHT_TEST_ONNX=1` before that command to generate an isolated fixture bundle and run the additional browser test for actual ONNX execution and HMI rendering. The browser harness stores its model, database, and generated files under ignored `.tools/playwright-runs/`.

## Supported ONNX contract

`ModelManifest.output_format` currently accepts only `yolo11_raw_v1`: one input named arbitrarily, with static shape `[1,3,H,W]` and float32 type; one float32 output with shape `[1,4+C,N]`, where `C` equals the manifest class count and `1 <= N <= 10000`. The output uses model-input pixel coordinates: `cx,cy,width,height` followed by per-class scores in `[0,1]`, **without an objectness channel or built-in NMS**. The adapter takes the best class per candidate, gates at the profile RECHECK threshold, applies class-aware IoU 0.5 NMS, and restores boxes to original image pixels. It rejects malformed, nonfinite, out-of-range, padding-crossing, or unsupported outputs. This is an explicit format contract, not a claim that every Ultralytics export follows it; inspect and validate each exported graph before registration. The fixture graph exercises this same decoder.

Profile preprocessing decodes BGR8, verifies dimensions, applies ROI and configured rotation, letterboxes to the model size, converts to RGB float32, and optionally scales to `[0,1]`. The detector uses the original BGR frame while the inherited edge Poka-Yoke runs on grayscale pixels. Coordinate transforms are tested independently. Profile, preprocessing fingerprint, model identity, artifact SHA-256, input dimensions, class map, and thresholds must match the manifest. ONNX Runtime is imported only when a local ONNX detector is requested. RKNN execution remains unavailable.

## Failure and audit behavior

Corrupt or wrong-size images, missing calibration, unsupported geometry, missing or incompatible models, runtime errors, and malformed outputs produce or preserve RECHECK through the local inspection service whenever an event can be persisted. They cannot fall back to scenario simulation. Definitive geometry failures continue through the shared decision engine. Database failure leaves mock I/O in the fault state and prevents WebSocket publication. The event contains profile ID/version/fingerprint, model ID/version/runtime/artifact hash/purpose, threshold and calibration references, normalized defect boxes, software timing, decision reasons, faults, source hash, and explicit simulation/mock-I/O flags. Operator reviews remain separate append-only actions.

`trained_unverified` and `adapter_test_fixture` are forced to RECHECK for geometrically valid images. Only a genuinely approved profile and independently validated model should ever be marked `real_approved` and `trained_validated`; those strings are declarations requiring external evidence, not automatic certification. The current fixture must never be promoted by editing its label.

## Training and hardware handoff

Before registering an exported ONNX artifact, run the static contract preflight
against the exact profile and manifest:

```powershell
python -m software.ml.export `
  --profile-catalog data/models/catalog `
  --profile <profile-id>@<version> `
  --model-manifest data/models/model-manifest.json `
  --model-root data/models `
  --output data/models/onnx-validation.json
```

The report verifies the artifact hash, profile and preprocessing fingerprints, and
the graph's single float32 input `[1,3,H,W]` and output `[1,4+C,N]` tensor shapes.
The manifest hashes one `.onnx` file, so the preflight rejects ONNX graphs with
external tensor data before invoking ONNX's full checker. The checker performs
static shape inference to catch inferable inconsistencies; it does not execute
model inference or establish numerical correctness.
It records `inference_executed: false` and `hardware_verified: false`; it is a
registration gate, not accuracy, RKNN, Orange Pi, thermal, or latency evidence.

1. Select and approve the physical component and reject tolerances; capture calibrated, rights-cleared images with part/session IDs and independent annotations.
2. Train against the frozen splits, select thresholds on validation only, and report held-out heavy-burr recall and false acceptance with uncertainty intervals.
3. Export a model and verify its actual ONNX input/output tensors against the contract above; otherwise implement a separately versioned decoder with fixture tests.
4. Create a new immutable component profile and model manifest. Verify artifact hashes, preprocessing parity, class mapping, geometry, calibration, and measured decisions before changing approval labels.
5. Measure ONNX-to-RKNN parity and Orange Pi latency with real hardware; validate camera, lighting, isolation, GPIO, thermal behavior, and fault recovery. Keep the mock software demo distinct from these physical claims.
