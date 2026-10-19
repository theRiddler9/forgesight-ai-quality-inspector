# Inference benchmark harness

`runner.py` provides `benchmark_inference` for timing a callable inference adapter
over a sequence of in-memory frames. It runs configurable warmups, records every
measured call in milliseconds, and reports mean, median, nearest-rank p95, minimum,
and maximum latency alongside the Python and host platform metadata. `write_report`
stores the result as formatted JSON.

This is a timing primitive, not a model evaluation or a claim that the current host
uses an RK3588 NPU. The `target_label` field is caller-supplied metadata. Reports
from a development computer must not be represented as Orange Pi measurements.

The trained burr model, frozen calibration manifest, ONNX/RKNN conversion, accuracy
parity evaluation, and Orange Pi 5 benchmark remain separate work. Integrate those
after the model artifact and calibration handoff are available.

## Command line

Save a NumPy `.npy` input frame or batch and provide a local zero-argument factory
whose return value accepts one frame, for example `my_runtime:create_infer`. Run
from the repository root:

```powershell
python -m software.ml.benchmarks --adapter my_runtime:create_infer --frames data/benchmark/frames.npy --model-id local-model-v1 --target-label orange-pi-5-rk3588s --warmup 10 --repetitions 100 --output data/benchmark/report.json
```

The target label is descriptive metadata supplied by the caller. The command does
not confirm that the named device or accelerator was used. The adapter and model
runtime must be installed in the active Python environment.
