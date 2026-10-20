# Inference benchmark harness

`runner.py` provides `benchmark_inference` for timing a callable inference adapter
over a sequence of in-memory frames. It runs configurable warmups, records every
measured call in milliseconds, and reports mean, median, nearest-rank p95, minimum,
and maximum latency alongside the Python and host platform metadata. `write_report`
stores the result as formatted JSON.

This is a timing primitive, not a model evaluation or a claim that the current host
uses an RK3588 NPU. The `target_label` field is caller-supplied metadata. Reports
from a development computer must not be represented as Orange Pi measurements.

The profile-aware CPU ONNX detector is available through the dedicated command
below. A trained burr model, frozen calibration manifest, ONNX export, accuracy
parity evaluation, RKNN conversion, and Orange Pi 5 benchmark still require the
approved model/calibration handoff and target hardware.

## Command line

Save a NumPy `.npy` input frame or batch and provide a local zero-argument factory
whose return value accepts one frame, for example `my_runtime:create_infer`. Select
the layout explicitly: `gray` is one `H×W` image, `gray-batch` is `N×H×W`, `bgr`
is one `H×W×3` image, and `bgr-batch` is `N×H×W×3`. Run from the repository root:

```powershell
python -m software.ml.benchmarks --adapter my_runtime:create_infer --frames data/benchmark/frames.npy --input-layout gray-batch --model-id local-model-v1 --target-label orange-pi-5-rk3588s --warmup 10 --repetitions 100 --output data/benchmark/report.json
```

The target label is descriptive metadata supplied by the caller. The command does
not confirm that the named device or accelerator was used. The adapter and model
runtime must be installed in the active Python environment. When `--artifact` is
provided, the report stores its filename, size, and SHA-256; the run is rejected if
the artifact changes during measurement. Reports also capture installed ONNX/RKNN
runtime versions, detected host model, and SoC temperature before and after the run
when Linux thermal telemetry is available. Missing values are recorded as `null`.
Frame arrays must use `uint8` pixel values; the declared layout determines whether
the adapter receives gray or BGR frames and whether the file contains one frame or
a batch.

## Profile-aware CPU ONNX detector

Install the optional runtime and graph-generation dependencies with
`python -m pip install -r software/requirements-onnx.txt`. Save one BGR8 frame as
`H×W×3` or a batch as `N×H×W×3`; the dimensions must match the selected profile.
After registering an ONNX profile and matching model manifest, run from the
repository root (replace the profile and data paths with that handoff):

```powershell
python -m software.ml.benchmarks.onnx_cli `
  --profile-catalog data/models/catalog `
  --profile <onnx-profile-id>@<version> `
  --model-manifest data/models/model-manifest.json `
  --model-root data/models `
  --frames data/benchmark/bgr-frames.npy `
  --input-layout bgr-batch `
  --target-label local-cpu `
  --warmup 10 --repetitions 100 `
  --output data/benchmark/onnx-report.json
```

The command verifies the selected profile and manifest through the existing
`OnnxDetector`, then measures each complete `detect` call (preprocessing, ONNX
execution, and postprocessing) with the shared benchmark runner. The report hashes
the model artifact before and after measurement and contains the raw latency
samples and host/runtime/temperature provenance. `--target-label` remains metadata;
this CPU command does not claim RKNN use, Orange Pi performance, trigger-to-decision
latency, or defect accuracy. The generated adapter-test ONNX graph is only for
integration tests and must never be presented as a trained burr detector. ONNX
reports also retain the profile ID/version/fingerprint, model version/purpose, and
preprocessing fingerprint; the CSV summary carries these fields for run comparisons.

The report format is described by `report.schema.json`. To produce a CSV overview
from multiple reports without modifying the source JSON:

```powershell
python -m software.ml.benchmarks.summarize data/benchmark/run-*.json --output data/benchmark/summary.csv
```

The summarizer recomputes latency statistics from the raw samples. It reports
timing only; it does not calculate accuracy or determine whether a KPI passed.
It expands wildcard report paths itself, including the `run-*.json` pattern shown
above, so the command works in PowerShell as written.
