# ForgeSight Technical Stack

## Edge Platform

| Layer | Selected technology | Purpose |
|---|---|---|
| Compute | Orange Pi 5, RK3588S | Local CPU/NPU execution |
| OS | Armbian or Ubuntu 22.04 LTS | Edge runtime |
| Language | Python 3.10+ | Vision, inference, decision, and backend services |
| Vision | OpenCV | Capture, preprocessing, overlays, and Poka-Yoke |
| Training | PyTorch with YOLOv8n or YOLO11n | Heavy-burr detector |
| Portable model | ONNX | Export and parity verification |
| Edge model | RKNN INT8 | NPU inference |
| Edge acceleration | RKNN-Toolkit2 | Compilation and runtime |

## Application Platform

| Layer | Selected technology | Purpose |
|---|---|---|
| API | FastAPI | Inspection, history, health, settings, and review endpoints |
| Live events | WebSocket | HMI status and inspection updates |
| Storage | SQLite | Local audit trail |
| HMI | React and Vite | Touchscreen operator interface |
| Styling | Tailwind CSS | High-contrast responsive layout |
| Charts | Recharts or Chart.js | Yield and defect trends |

## Hardware Interfaces

| Subsystem | Preferred component |
|---|---|
| Camera | Global-shutter USB/UVC camera such as OV9281; final selection pending |
| Lighting | Diffused 12 V white LED ring with PWM control |
| Trigger | NPN/PNP proximity or through-beam sensor through isolation |
| Isolation | PC817 optocoupler channels |
| Indicators | Red, amber, and green tower light plus buzzer |
| Power | XL4015 or LM2596 conversion with protection and filtering |

## Engineering Tools

- SolidWorks 2024 for native mechanical CAD and static FEA.
- KiCad 8 for power, isolation, sensor, driver, and interconnect schematics.
- Git and Git LFS for source history and large model/native artifacts.
- Pytest for Python behavior and contract tests.
- Frontend test tooling will be selected with the HMI scaffold.

## Technical Rules

- Hardware-specific access is behind adapters; development and CI use deterministic mocks.
- Thresholds, dimensions, GPIO mappings, and model paths are configuration, not source constants.
- Every inspection event conforms to the canonical JSON Schema.
- Store native sources together with export, validation output, and evidence reference.
- Benchmark each pipeline stage separately and report total trigger-to-decision latency.
