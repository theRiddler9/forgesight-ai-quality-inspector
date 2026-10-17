# ForgeSight: Non-Negotiable Project Notes & Competition Boundaries (REMEMBER.md)

**Theme:** AI in Hardware & Manufacturing  
**Event:** Vishwakarma Awards 2026-27, Stage 2 (Design and Feasibility Audit)  

---

## 1. Native Files & Audit Trail
- **Keep native CAD and KiCad files:** Raw SolidWorks files (`.SLDPRT`, `.SLDASM`) and KiCad files (`.kicad_sch`) must be committed directly to version control.
- **Creation timestamps matter:** Slide 11 of the Stage 2 evaluation audits native file creation timestamps and commit history. Never bulk-upload exports or screenshots at the last minute; commit originals incrementally as they are created.

---

## 2. Large File Policy & Git LFS
- **Track large binaries via Git LFS:** Compiled models (`.rknn`, `.onnx`, `.pt`, `.pth`), high-resolution video recordings, and large STEP models must be tracked through Git LFS via `.gitattributes`.
- **Large datasets on Google Drive:** If raw image dataset archives exceed reasonable Git storage limits, host the raw archive on Google Drive and link the verified hash and download URL from `software/dataset/DATASET_CARD.md`. The 200-image INT8 calibration set must remain version-controlled.

---

## 3. Stage 2 vs Stage 3 Boundary
- **Stage 2 is Virtual Validation:** Focus on native CAD modeling, static structural FEA (SolidWorks Simulation), thermal conduction calculations, KiCad schematics and master interconnect, INT8 quantization benchmarks, and the FastAPI/React HMI.
- **Isolate physical shop-floor plans:** Anything involving physical line trials, MSME factory floor testing, conveyor retrofitting, or field deployment belongs in `validation/stage3_plan/` until post-selection.

---

## 4. Hardware Architecture & Fabrication Realities
- **No firmware or 3D-printing folders:** The Orange Pi 5 runs standard Linux (Armbian / Ubuntu 22.04) and Python. GPIO control is handled directly via Python in `software/edge/io_control/`.
- **COTS-first enclosure:** The mechanical design utilizes an off-the-shelf IP65 ABS junction box rather than custom 3D printing to minimize cost and lead time. Fabrication is strictly limited to enclosure drilling cutouts and the laser-cut acrylic optical window (`mechanical/fabrication/`).
- **Custom PCB is optional:** The Stage 2 electrical architecture uses COTS modules (XL4015/LM2596 buck converter, PC817 optocoupler module, terminal blocks). KiCad schematics document the power regulation, isolation, and master interconnect; a custom consolidated PCB layout is optional and can be introduced in Stage 3.

---

## 5. Non-Negotiable Key Performance Indicators (KPIs)

| Parameter | Target | Verification Method |
| :--- | :--- | :--- |
| **Hardware Cost** | **< ₹10,000** | Itemized COTS BOM with active supplier links (`electrical/bom/`) |
| **Inspection Speed** | **≤ 100 ms per part** | RKNN NPU benchmark execution logs (`software/ml/benchmarks/`) |
| **Defect Recall** | **> 95%** | Evaluation against real held-out test set (`validation/defect_recall/`) |
| **Structural Safety** | **Factor of Safety > 2.0** | SolidWorks static structural FEA under 50–100 N loads (`mechanical/fea/`) |
| **Thermal Headroom** | **SoC < 65 °C at 45 °C ambient** | Heatsink passive thermal conduction calculation (`mechanical/thermal/`) |
| **Noise Immunity** | **100% opto-isolated GPIO** | PC817 isolation schematics between 24V line and 3.3V GPIO (`electrical/kicad/`) |

---

## 6. Software Decoupling & Collaboration
- **Task split:** 4 items for Riya (Dataset, ML Training, Backend, HMI) and 3 items for Akash (Edge RKNN Optimization, Deterministic OpenCV Vision, Decision/GPIO Logic + Watchdog). Akash also co-leads Mechanical CAD and FEA.
- **Mutual PR Review:** Both software contributors need to review PRs of each other and then make changes accordingly which are related to each other.
- **Contract-first development:** All modules adhere strictly to `software/CONTRACT.md` and `software/common/schemas.py`.
- **Zero-hardware local debugging:** All edge modules must support `--mock-hardware` and `--mock-camera`; backend must support `--use-stub-engine` so either contributor can develop and debug on any laptop without hardware blockers.
