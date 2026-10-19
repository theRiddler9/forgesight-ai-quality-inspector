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
