# ForgeSight

**AI-enabled, low-cost industrial quality inspection for MSMEs. Edge-AI vision, no cloud, under ₹10,000 in hardware.**


| | |
|---|---|
| **Theme** | AI in Hardware & Manufacturing |
| **Sub-Theme** | Computer Vision & Smart Quality Inspection |
| **Event** | Vishwakarma Awards 2026-27, Stage 2 (Design and Feasibility Audit) |

---

## Overview

Small and medium manufacturers often inspect metal parts by eye. It is slow, inconsistent and hard to audit. Industrial vision systems solve this, but they are priced far beyond what most MSMEs can spend.

**ForgeSight** is a compact inspection station that sits over a conveyor line and checks every part in real time. It combines:

- **Deterministic Poka-Yoke checks** (OpenCV): part present, correct position, hole present, size in range.
- **A quantized YOLO detector** running on the Orange Pi 5 NPU for surface defects such as burrs, flash, cracks and scratches.
- **A decision engine** that outputs PASS / FAIL / RECHECK and drives a tower light and buzzer through opto-isolated GPIO.
- **A touchscreen operator dashboard** with live view, yield and defect-trend charts, and an audit log.

Everything runs locally on the edge device. No cloud dependency.

## Design Strategy

ForgeSight is built **COTS-first** (Commercial Off-The-Shelf) to cut cost, lead time and manufacturing risk:

- Standard IP65 ABS junction box instead of a custom 3D-printed housing
- Modular 2020 V-slot aluminum extrusion for the adjustable camera stalk
- Off-the-shelf rubber vibration isolators, PG7/PG9 cable glands and heatsink
- Budget industrial electronics (buck converter, PC817 optocoupler bank)

## Stage 2 Scope

Stage 2 is a **virtual validation** stage. Physical shop-floor testing is planned for Stage 3 (post-selection).

| Stage 2 (now) | Stage 3 (post-selection) |
|---|---|
| Native SolidWorks CAD master assembly and exploded view | Physical prototype build |
| Static structural FEA in SolidWorks Simulation | Shop-floor and MSME line testing |
| KiCad schematics (power, isolation, sensing, indicators) | Field validation and tuning |
| INT8 quantization and NPU benchmarking | Shadow-mode deployment |
| FastAPI backend and React HMI dashboard | |

## Key Targets (KPIs)

| Parameter | Target | Verified by |
|---|---|---|
| Hardware cost | < ₹10,000 | Itemized COTS BOM |
| Inspection speed | ≤ 100 ms per part | RKNN NPU benchmark logs |
| Defect recall | > 95% on burrs, cracks, flaws | Held-out test set evaluation |
| Structural safety | Factor of Safety > 2.0 | SolidWorks static FEA (50-100 N) |
| Thermal headroom | SoC < 65 °C at 45 °C ambient | Passive heatsink calculation |
| Noise immunity | 100% opto-isolated GPIO | KiCad PC817 isolation schematic |

## System Architecture

```
Part sensor ─► Opto-isolation ─► Orange Pi 5 GPIO
                                      │
        Camera + LED ring ─► Acquisition (OpenCV)
                                      │
                      ┌───────────────┴───────────────┐
              Poka-Yoke rules                  YOLO (.rknn on NPU)
                      └───────────────┬───────────────┘
                                      ▼
                       Decision: PASS / FAIL / RECHECK
                                      │
              ┌───────────────────────┼────────────────────────┐
        Tower light + buzzer      SQLite audit log      FastAPI + WebSocket
        (opto-isolated GPIO)                                    │
                                                        React touchscreen HMI
```

## Tech Stack

**Hardware:** Orange Pi 5 (RK3588S, 6 TOPS NPU), global-shutter USB camera (OV9281 / IMX335), 12V LED ring light, IP65 ABS enclosure, 2020 aluminum extrusion, XL4015 / LM2596 buck converter, PC817 optocoupler module, inductive or photoelectric trigger sensor.

**Edge and AI:** Armbian / Ubuntu 22.04, Python, OpenCV, PyTorch, ONNX, RKNN-Toolkit2, YOLOv8n / YOLO11n, Anomalib PatchCore.

**Backend and HMI:** FastAPI, WebSockets, SQLite, React, Vite, Tailwind CSS, Chart.js / Recharts.

**Design tools:** SolidWorks 2024 (CAD and Simulation), KiCad 8.0.

## Repository Structure
```
forgesight/
├── docs/            Goals, tech stack, roles, roadmap, design decisions, problem context, references
├── mechanical/      SolidWorks parts and assembly, STEP exports, FEA, thermal, fabrication, renders
├── electrical/      KiCad schematics, pinout, calculations, BOM, datasheets
├── software/        Dataset, ML training and export, edge runtime, backend, frontend, deployment
├── system/          Top-level system block diagram and target specs
├── validation/      KPI evidence, model validation, FMEA, standards, risks, Stage 3 plan
├── evidence/        Maker-journey proof: lab photos, screenshots, iteration log, external links
└── submission/      Final presentation deck, slide assets, slide-to-folder map
```

See `submission/slide_content_map.md` for which folder feeds which slide of the Stage 2 template.

## Team

| Member | Area |
|---|---|
| **Akash** | Mechanical co-lead, SolidWorks master assembly and FEA, software and edge-AI co-lead |
| **Riya** | Software and edge-AI co-lead: dataset, training, backend, HMI |
| **Rudra** | Mechanical co-lead: enclosure, camera stalk, optical cowl, thermal interface |
| **Aratrik** | Power regulation and I/O isolation (KiCad) |
| **Kartikay** | Trigger sensor interface, indicator and lighting drivers (KiCad) |

Full responsibilities and the RACI matrix are in [`docs/Roles.md`](docs/Roles.md).

## Contributing

1. **Commit early and often.** Stage 2 audits file history and timestamps, so avoid bulk-uploading at the end.
2. **Keep native files.** Commit the originals (`.SLDPRT`, `.SLDASM`, `.kicad_sch`, `.STEP`), not just exports or screenshots.
3. **Work inside your area's folders**, and commit your own files.
4. **Large files** (`.rknn`, `.onnx`, `.pt`, raw images) go through Git LFS. If the dataset is too large, host it on Drive and link it from `software/dataset/DATASET_CARD.md`.
5. **Suggest design or functionality changes** by logging them in the team Changes tab before editing shared documents.
6. **Commit messages:** use a short prefix, for example `mech: add enclosure gasket groove`, `elec: draft buck converter schematic`, `sw: add INT8 calibration script`, `docs: update roadmap`.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for details.

## Reproducing Results

Setup and run instructions will be added as each subsystem lands:

- [ ] Mechanical: open `mechanical/solidworks/master_assembly/` in SolidWorks 2024
- [ ] Electrical: open `electrical/kicad/` in KiCad 8.0
- [ ] ML: training and export steps in `software/ml/`
- [ ] Edge, backend and HMI: setup in `software/deployment/`

## Project Status

- [ ] Problem context and before/after user journey
- [ ] SolidWorks CAD master assembly and exploded view
- [ ] Static structural FEA (FoS > 2.0)
- [ ] KiCad schematics and master interconnect
- [ ] COTS BOM under ₹10,000
- [ ] Dataset, training and INT8 quantization
- [ ] Edge pipeline, backend and HMI dashboard
- [ ] FMEA, standards checklist and risk mitigation
- [ ] Stage 2 presentation deck

## License

## Acknowledgements

Built for the Vishwakarma Awards 2026-27. Sources and image credits are listed in [`docs/references.md`](docs/references.md).