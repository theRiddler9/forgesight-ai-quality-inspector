# ForgeSight: Software Architecture, Task Division & Starter Code Blueprint

**Theme:** AI in Hardware & Manufacturing  
**Sub-Theme:** Computer Vision & Smart Quality Inspection  
**Event:** Vishwakarma Awards 2026-27, Stage 2 (Design and Feasibility Audit)  

---

## 1. Executive Summary & Purpose

This document defines the software engineering blueprint, shared contracts, task allocation, and collaboration protocols for **ForgeSight** before feature branches are created.

### Starter Code Strategy: "Contract-First, Zero Feature Code on Main"
To prevent merge conflicts and coordination bottlenecks:
1. **No feature code is pushed directly to `main` initially.** Only shared contracts, data schemas, folder skeletons, stubs, and governance documents reside on `main`.
2. Both software contributors (Akash and Riya) develop asynchronously against locked interfaces defined in this document.
3. Feature development takes place on dedicated feature branches (`feat/`, `fix/`, `pair/`), with pull requests reviewed mutually before merging.

---

## 2. Fair Task Allocation: Riya (4) & Akash (3)

The 7 core software engineering deliverables are split **4 for Riya** and **3 for Akash**, balancing total project workload across Vishwakarma Stage 2 deliverables:

| Owner | Count | Assigned Items | Target Folders | Rationale & Balance |
| :--- | :---: | :--- | :--- | :--- |
| **Riya** | **4** | **1. Dataset engineering**<br>**2. Model training & benchmarking**<br>**6. Backend & audit logging**<br>**7. Operator touchscreen HMI** | `software/dataset/`<br>`software/ml/training/`<br>`software/backend/`<br>`software/frontend/` | Riya owns the ML data/training loop and the backend/HMI presentation tier. While dataset engineering is heavy upfront, Kartikay (lighting/rig lead) and Rudra (mechanical co-lead) assist with part capture and labeling as defined in the RACI matrix. |
| **Akash** | **3** | **3. Edge optimization & compilation**<br>**4. Deterministic vision engine**<br>**5. Decision & I/O logic (+ watchdog)** | `software/ml/export/`<br>`software/ml/benchmarks/`<br>`software/edge/` | Akash is already carrying **Mechanical Co-Lead**, the **SolidWorks master assembly**, and **FEA simulation**. Keeping software to 3 edge-hardware items balances total Stage 2 workload and consolidates the entire Orange Pi 5 runtime pipeline under one owner. |

### Subsystem Breakdown

1. **Dataset engineering (Riya)**: Collects, augments, and annotates the metal defect dataset (burrs first, then flash, cracks, scratches) on the camera and lighting rig. Splits data by part (train/val/held-out test) and curates the 200-image INT8 calibration set.
2. **Model training and benchmarking (Riya)**: Trains lightweight YOLOv8n / YOLO11n detectors in PyTorch, evaluates mAP, recall, and false-reject rate against the >95% recall target, and establishes confidence thresholds for PASS, FAIL, and RECHECK.
3. **Edge optimization and compilation (Akash)**: Exports PyTorch models to ONNX, performs INT8 post-training quantization using RKNN-Toolkit2, and deploys `.rknn` binaries on the Orange Pi 5 NPU (RK3588S, 6 TOPS). Logs FP32 vs INT8 accuracy drop and verifies the ≤100 ms latency target.
4. **Deterministic vision engine (Akash)**: Python + OpenCV module for camera capture, exposure locking, contrast adjustment, and rule-based Poka-Yoke checks (part present, correct position, hole present, size in range). Ensures simple defects never consume NPU cycles.
5. **Decision and I/O logic (+ watchdog) (Akash)**: Combines Poka-Yoke and AI results into PASS / FAIL / RECHECK decisions. Drives the tower light, buzzer, and LED ring via opto-isolated GPIO. Includes a hardware/software watchdog flagging pipeline stalls (>200 ms) or camera disconnects.
6. **Backend and audit logging (Riya)**: Asynchronous FastAPI service with WebSocket live streaming, local SQLite audit logging (result, defect type, confidence, per-stage latency, SoC temperature), and an operator review endpoint where human corrections feed back into retraining data.
7. **Operator touchscreen HMI (Riya)**: React + Vite + Tailwind dashboard with live camera view, large PASS/FAIL/RECHECK banner, yield and defect-trend charts, failed-frame inspection history with thumbnails, and threshold/brightness controls.

---

## 3. Mutual Support & Peer Review Protocol

### Peer Review & Interdependent Changes Rule
> **Both software contributors need to review PRs of each other and then make changes accordingly which are related to each other.**
> 
> When a PR touches an edge output, WebSocket event, REST route, or data schema, both contributors coordinate the review to ensure upstream and downstream dependencies (e.g., edge decision engine ↔ backend audit log ↔ frontend HMI) are updated in lockstep before merging.

### Cross-Support & Backup Matrix
If either contributor encounters blockers, the other steps in to pair-debug or assist:

| Item | Primary Lead | Secondary / Backup | Cross-Support Touchpoints |
| :---: | :---: | :---: | :--- |
| **1 & 2 (Dataset / ML)** | **Riya** | **Akash** | Akash provides defect criteria from CAD/FMEA; assists in loss debugging and INT8-friendly architecture design. |
| **3 (Edge Optimization)** | **Akash** | **Riya** | Riya assists with PyTorch-to-ONNX opset compatibility, calibration sizing, and quantization error analysis. |
| **4 (OpenCV Vision)** | **Akash** | **Riya** | Riya assists with OpenCV adaptive thresholding, lighting normalization, and synthetic image test vectors. |
| **5 (Decision & GPIO)** | **Akash** | **Riya** | Riya assists with state machine transitions, watchdog exception formatting, and GPIO event dispatching. |
| **6 (Backend & DB)** | **Riya** | **Akash** | Akash assists with SQLite schema tuning, IPC ingestion from the edge decision engine, and low-latency WebSockets. |
| **7 (Operator HMI)** | **Riya** | **Akash** | Akash assists with UI responsiveness, WebSocket reconnect resilience, and touch controls styling. |

### Zero-Hardware Local Debugging (Hardware Abstraction Layer)
To enable Riya to debug Akash's edge pipeline without physical Orange Pi 5 hardware, and to enable Akash to test the backend/HMI locally:
- **Mock GPIO Controller (`--mock-hardware`)**: Logs pin states (Tower Green/Red/Amber, Buzzer, Ring PWM) to console/memory for local development on Windows or macOS.
- **Mock Camera Source (`--mock-camera`)**: Supports standard USB webcams, video loops, or directories of static defect images when the OV9281 global shutter camera is not attached.
- **Stub Inference Engine (`--use-stub-engine`)**: Allows Riya to run the full FastAPI backend and React HMI without requiring the RK3588S NPU.

---

## 4. Repository Structure Blueprint

```
forgesight/
├── docs/                              Planning and reference documents
│   ├── Project_Goals.md               Scope, objectives, KPI targets
│   ├── Tech_Stack.md                  Component and software specifications
│   ├── Roles.md                       Roles and RACI matrix
│   ├── roadmap.md                     Stage 2 vs Stage 3 scope boundary
│   ├── design_decisions.md            Why Orange Pi 5 over Jetson, COTS over 3D printing, etc.
│   ├── meeting_notes/                 Dated notes per team sync
│   └── references.md                  Sources and image credits
│
├── mechanical/                        Native SolidWorks 2024 design, FEA and thermal
│   ├── cots_parts/                    Vendor models and datasheets (IP65 junction box, 2020 extrusion, isolators)
│   ├── solidworks/
│   │   ├── enclosure/                 Body + lid (.SLDPRT)
│   │   ├── camera_stalk/              Adjustable arm, base plate (.SLDPRT)
│   │   ├── optical_cowl/              Camera/ring-light hood (.SLDPRT)
│   │   ├── thermal_interface/         Heatsink mounting boss and fin array (.SLDPRT)
│   │   ├── master_assembly/           Unified .SLDASM with Toolbox fasteners
│   │   └── exploded_view/             Explode-line sketches and BOM-callout render
│   ├── fea/                           Setup, results, reports (FoS > 2.0)
│   ├── thermal/                       Passive heatsink conduction calculation (SoC < 65 °C at 45 °C ambient)
│   ├── fabrication/                   Cutout drawings and acrylic window DXF/SVG
│   └── renders/                       Isometric and exploded images
│
├── electrical/                        KiCad 8.0 schematics, calculations and BOM
│   ├── kicad/
│   │   ├── 1_power_regulation/        24V/12V to 5V 4A buck, fusing, reverse-polarity protection
│   │   ├── 2_io_isolation/            PC817 optocoupler bank between Orange Pi GPIO and external I/O
│   │   ├── 3_trigger_sensor/          Sensor interface, signal conditioning, debounce
│   │   ├── 4_indicator_driver/        Tower light (G/R/A), buzzer, PWM LED ring driver
│   │   ├── 5_master_interconnect/     Top-level block diagram merging sub-circuits at GPIO boundary
│   │   └── drc_logs/                  DRC / ERC reports
│   ├── pinout/                        Orange Pi 5 GPIO allocation
│   ├── calculations/                  Component values, current budget, power dissipation
│   ├── bom/                           COTS itemized BOM (target under Rs 10,000)
│   └── datasheets/                    Orange Pi 5, camera, PC817, XL4015/LM2596, sensors
│
├── software/                          AI, edge runtime, backend and operator HMI
│   ├── architecture/                  Pipeline diagrams (edge_pipeline, backend_hmi_flow, merged_data_flow)
│   ├── CONTRACT.md                    Shared inspection result schema, REST routes, WebSocket events
│   ├── schema.json                    Formal JSON Schema Draft 7 specification
│   ├── common/
│   │   └── schemas.py                 Pydantic v2 data models used across edge and backend
│   ├── dataset/                       Dataset curation, YOLO annotations, splits, and INT8 calibration set
│   │   ├── raw/
│   │   ├── synthetic/
│   │   ├── annotated/
│   │   ├── augmentation/
│   │   ├── splits/
│   │   ├── calibration_int8/
│   │   └── DATASET_CARD.md
│   ├── ml/                            Training, export, and benchmarking
│   │   ├── training/
│   │   ├── anomaly/
│   │   ├── export/
│   │   ├── models/                    Compiled .rknn and ONNX files (Git LFS)
│   │   └── benchmarks/                mAP, recall, latency vs 100 ms target
│   ├── edge/                          Orange Pi 5 runtime
│   │   ├── acquisition/               OpenCV capture, exposure locking, contrast adjustment
│   │   ├── poka_yoke/                 Rule-based checks: part present, position, hole, size
│   │   ├── inference/                 RKNN runtime & stub_inference.py
│   │   ├── decision/                  Combines Poka-Yoke + AI into PASS / FAIL / RECHECK
│   │   ├── io_control/                Opto-isolated GPIO: trigger in, tower light, buzzer, ring PWM
│   │   └── watchdog/                  Flags pipeline stalls and camera loss
│   ├── backend/                       FastAPI service
│   │   ├── api/                       REST routes + operator review endpoint
│   │   ├── websocket/                 Live frame streaming and alerts
│   │   ├── db/                        SQLite audit log
│   │   └── tests/
│   ├── frontend/                      React + Vite + Tailwind touchscreen HMI
│   │   ├── src/components/            Live view, PASS/FAIL/RECHECK banner, failed-frame history, settings
│   │   └── src/charts/                Yield and defect-trend charts
│   └── deployment/                    Armbian/Ubuntu setup, systemd services, RKNN-Toolkit2 install
│
├── validation/                        Proof for KPIs and safety
│   ├── kpi_evidence/                  BOM cost, inspection speed, defect recall, structural FoS, thermal
│   ├── model_validation/              Confusion matrices, PR curves, threshold selection
│   ├── fmea/                          FMEA risk matrix
│   ├── standards_checklist.md         IP65 and industrial standards
│   └── stage3_plan/                   Shop-floor / MSME field deployment plan (post-selection)
│
├── evidence/                          Maker-journey proof
│   ├── lab_photos/                    Team at work, ID badges visible
│   ├── software_screenshots/          SolidWorks feature trees, KiCad schematics, FEA plots, dashboard
│   ├── iteration_log.md               Design progression logs
│   └── external_links.md              Drive and presentation links
│
├── submission/                        Final deliverable
│   ├── Vishwakarma_Stage2_ForgeSight.pptx
│   ├── slide_assets/                  Figures organized by slide
│   └── slide_content_map.md           Slide-to-folder mapping
│
├── REMEMBER.md                        Non-negotiable project notes & audit rules
├── AGENTS.md                          Codex / Antigravity / Superpowers workflow & Git rules
├── starter_code.md                    This document
├── README.md                          Project overview
├── CONTRIBUTING.md                    Commit/branch conventions
├── .gitignore                         Repository ignore rules
└── .gitattributes                     Git LFS configurations
```

---

## 5. Shared Contracts & Interface Specifications

### 5.1 Inspection Result Schema (`software/CONTRACT.md`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ForgeSightInspectionResult",
  "type": "object",
  "required": [
    "inspection_id",
    "timestamp",
    "result",
    "defect_type",
    "confidence",
    "per_stage_latency_ms",
    "soc_temp_c",
    "poka_yoke_status",
    "class_names"
  ],
  "properties": {
    "inspection_id": { "type": "string", "format": "uuid" },
    "timestamp": { "type": "string", "format": "date-time" },
    "result": { "type": "string", "enum": ["PASS", "FAIL", "RECHECK"] },
    "defect_type": {
      "type": "string",
      "enum": ["none", "burr", "flash", "crack", "scratch", "dimensional_error", "missing_hole", "part_misaligned"]
    },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "class_names": {
      "type": "array",
      "items": { "type": "string" },
      "default": ["burr", "flash", "crack", "scratch"]
    },
    "poka_yoke_status": {
      "type": "object",
      "required": ["part_present", "position_valid", "hole_present", "size_in_range"],
      "properties": {
        "part_present": { "type": "boolean" },
        "position_valid": { "type": "boolean" },
        "hole_present": { "type": "boolean" },
        "size_in_range": { "type": "boolean" }
      }
    },
    "per_stage_latency_ms": {
      "type": "object",
      "required": ["capture_ms", "poka_yoke_ms", "npu_inference_ms", "decision_ms", "total_ms"],
      "properties": {
        "capture_ms": { "type": "number" },
        "poka_yoke_ms": { "type": "number" },
        "npu_inference_ms": { "type": "number" },
        "decision_ms": { "type": "number" },
        "total_ms": { "type": "number" }
      }
    },
    "soc_temp_c": { "type": "number" },
    "detections": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["class_name", "confidence", "bbox"],
        "properties": {
          "class_name": { "type": "string" },
          "confidence": { "type": "number" },
          "bbox": {
            "type": "array",
            "items": { "type": "number" },
            "minItems": 4,
            "maxItems": 4
          }
        }
      }
    },
    "image_path": { "type": "string" }
  }
}
```

### 5.2 Pydantic Data Models (`software/common/schemas.py`)

```python
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class InspectionDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    RECHECK = "RECHECK"

class DefectType(str, Enum):
    NONE = "none"
    BURR = "burr"
    FLASH = "flash"
    CRACK = "crack"
    SCRATCH = "scratch"
    DIMENSIONAL_ERROR = "dimensional_error"
    MISSING_HOLE = "missing_hole"
    PART_MISALIGNED = "part_misaligned"

class PokaYokeStatus(BaseModel):
    part_present: bool = True
    position_valid: bool = True
    hole_present: bool = True
    size_in_range: bool = True

class LatencyBreakdown(BaseModel):
    capture_ms: float = Field(..., ge=0.0)
    poka_yoke_ms: float = Field(..., ge=0.0)
    npu_inference_ms: float = Field(..., ge=0.0)
    decision_ms: float = Field(..., ge=0.0)
    total_ms: float = Field(..., ge=0.0)

class DetectionBox(BaseModel):
    class_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: List[float] = Field(..., min_length=4, max_length=4)  # [x_min, y_min, x_max, y_max]

class InspectionResult(BaseModel):
    inspection_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    result: InspectionDecision
    defect_type: DefectType = DefectType.NONE
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_names: List[str] = ["burr", "flash", "crack", "scratch"]
    poka_yoke_status: PokaYokeStatus
    per_stage_latency_ms: LatencyBreakdown
    soc_temp_c: float
    detections: List[DetectionBox] = []
    image_path: Optional[str] = None
```

### 5.3 WebSocket Event Format
All WebSocket events over `/ws/live` use standard JSON framing:
```json
{
  "event": "inspection_result",
  "data": { ...InspectionResult payload... }
}
```
Supported event types:
- `inspection_result`: Full JSON inspection result upon each trigger.
- `inspection_frame`: Low-latency JPEG thumbnail stream (base64) for live preview.
- `watchdog_alert`: Health warning events (e.g., `camera_disconnected`, `pipeline_stall`, `overheating`).

### 5.4 REST Route Names
- `GET /health`: Health probe and service uptime.
- `GET /api/v1/inspections/latest`: Returns the most recent inspection record.
- `GET /api/v1/inspections/history`: Returns paginated inspection history with filters (`result`, `limit`, `offset`).
- `POST /api/v1/operator/review`: Submits operator corrections, saving annotated images and labels to `software/dataset/retraining/`.
- `GET /api/v1/system/status`: Returns Orange Pi 5 metrics (SoC temperature, RAM, current FPS, average latency).
- `POST /api/v1/settings/thresholds`: Updates PASS/FAIL/RECHECK confidence thresholds and LED ring PWM brightness.

---

## 6. Stub Inference Function (`software/edge/inference/stub_inference.py`)

A fully contract-compliant mock generator enabling backend and HMI development immediately:

```python
import random
import time
from datetime import datetime
from uuid import uuid4

def get_stub_inspection_result(simulated_defect_rate: float = 0.15) -> dict:
    """
    Generates a realistic, contract-compliant mock inspection result.
    Target KPI: total latency <= 100 ms, SoC temperature < 65 C.
    """
    capture_ms = round(random.uniform(6.0, 10.0), 2)
    poka_yoke_ms = round(random.uniform(10.0, 16.0), 2)
    npu_ms = round(random.uniform(22.0, 32.0), 2)
    decision_ms = round(random.uniform(1.5, 3.5), 2)
    total_ms = round(capture_ms + poka_yoke_ms + npu_ms + decision_ms, 2)

    roll = random.random()
    if roll < (1.0 - simulated_defect_rate):
        result = "PASS"
        defect = "none"
        conf = round(random.uniform(0.96, 0.99), 3)
        detections = []
    elif roll < (1.0 - simulated_defect_rate + 0.05):
        result = "RECHECK"
        defect = random.choice(["burr", "scratch"])
        conf = round(random.uniform(0.70, 0.79), 3)
        detections = [{"class_name": defect, "confidence": conf, "bbox": [120.0, 140.0, 160.0, 185.0]}]
    else:
        result = "FAIL"
        defect = random.choice(["burr", "flash", "crack", "scratch"])
        conf = round(random.uniform(0.85, 0.98), 3)
        detections = [{"class_name": defect, "confidence": conf, "bbox": [200.0, 150.0, 260.0, 210.0]}]

    return {
        "inspection_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "result": result,
        "defect_type": defect,
        "confidence": conf,
        "class_names": ["burr", "flash", "crack", "scratch"],
        "poka_yoke_status": {
            "part_present": True,
            "position_valid": True,
            "hole_present": True,
            "size_in_range": True
        },
        "per_stage_latency_ms": {
            "capture_ms": capture_ms,
            "poka_yoke_ms": poka_yoke_ms,
            "npu_inference_ms": npu_ms,
            "decision_ms": decision_ms,
            "total_ms": total_ms
        },
        "soc_temp_c": round(random.uniform(49.0, 56.5), 1),
        "detections": detections,
        "image_path": f"/data/frames/mock_frame_{int(time.time())}.jpg"
    }

if __name__ == "__main__":
    import json
    print(json.dumps(get_stub_inspection_result(), indent=2))
```

---

## 7. Project Notes & Rules (`REMEMBER.md`)

- **Keep native files**: Raw SolidWorks (`.SLDPRT`, `.SLDASM`) and KiCad (`.kicad_sch`) files must be committed directly to preserve creation timestamps for Stage 2 audit.
- **Large files**: Use Git LFS for `.rknn`, `.onnx`, `.pt`, and dataset archives; link Google Drive datasets from `software/dataset/DATASET_CARD.md`.
- **Stage boundary**: Stage 2 is virtual validation (CAD, FEA, KiCad, NPU benchmarks, HMI simulation); physical shop-floor / MSME deployment belongs in `validation/stage3_plan/`.
- **No firmware or 3D-print folders**: Orange Pi 5 runs standard Linux & Python (GPIO lives in `software/edge/io_control/`); mechanical enclosure uses off-the-shelf COTS IP65 ABS junction boxes.
- **Custom PCB is optional**: COTS modules (buck converter, PC817 module) connected via KiCad schematics and master interconnect.
- **Hard KPI Targets**:
  - Hardware cost: < ₹10,000 (Itemized BOM)
  - Inspection speed: ≤ 100 ms per part (RKNN NPU benchmark)
  - Defect recall: > 95% on burrs, cracks, flash (held-out test set)
  - Structural FoS: > 2.0 (SolidWorks static FEA)
  - Thermal headroom: SoC < 65 °C at 45 °C ambient (passive heatsink calculation)
  - Signal noise immunity: 100% opto-isolated GPIO (PC817 schematic)

---

## 8. Agentic Workflow & Git Rules (`AGENTS.md`)

### Workflow Before Implementation
1. Read `AGENTS.md`
2. Read `REMEMBER.md`
3. Read `docs/Project_Goals.md` and `starter_code.md`
4. Use Superpowers planning before coding.
5. For independent tasks, subagents may be used, but **they must never unilaterally redesign cross-team interfaces or schemas**.
6. Use `verification-before-completion` before declaring milestones complete.

### Git Rules
- Work on separate feature branches (`feat/`, `fix/`, `pair/`).
- Make small, logical commits with clear prefixes (`sw:`, `mech:`, `elec:`, `docs:`).
- Merge shared contracts before dependent work.
- Pull/rebase shared changes before integration.
- Avoid destructive Git operations (`rebase -i` on shared branches, force pushes).
- **Do not wait until Day 3 to integrate.** Commit every feature and stage frequently for an authentic audit trail.
- **Both software contributors need to review PRs of each other and then make changes accordingly which are related to each other.**
