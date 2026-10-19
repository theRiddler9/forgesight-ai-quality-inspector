# ForgeSight Roles and Responsibilities

## Riya - Software and Edge-AI Co-Lead

Riya owns day-to-day delivery of:

- Dataset card, labeling guide, manifests, split integrity, and calibration set.
- OpenCV Poka-Yoke replay pipeline.
- YOLO training, evaluation, error analysis, and threshold selection.
- ONNX parity checks, INT8 RKNN compilation, and Orange Pi benchmarking.
- PASS / FAIL / RECHECK decision engine, I/O adapter, and watchdog behavior.
- FastAPI, SQLite, and WebSocket audit pipeline.
- React touchscreen HMI.
- Software validation evidence, FMEA coordination, and slide-ready artifacts.

Akash is co-lead and reviewer for dataset, model, edge runtime, and system architecture decisions.

## Other Owners

| Member | Accountable area | Required interface with Riya |
|---|---|---|
| Akash | Master assembly, FEA, software/AI co-lead | Camera geometry, model review, software architecture |
| Rudra | Enclosure, stalk, optical cowl, thermal interface | Camera height, field of view, mounting envelope |
| Aratrik | Power regulation and opto-isolation | Voltage levels, isolated GPIO allocation, safe state |
| Kartikay | Trigger, indicators, buzzer, and lighting drivers | Trigger behavior, debounce, output timing, PWM range |

## RACI Summary

| Deliverable | Riya | Akash | Rudra | Aratrik | Kartikay |
|---|---:|---:|---:|---:|---:|
| Dataset and labeling | A/R | A/R | I | I | C |
| Model training and RKNN | A/R | A/R | I | I | I |
| OpenCV and decision engine | A/R | A/R | I | C | C |
| Backend and HMI | A/R | A/R | I | I | I |
| Software architecture diagram | A/R | A/R | I | C | C |
| Electrical design | I | I | C | A/R | A/R |
| Mechanical design and FEA | I | A/R | A/R | C | C |
| FMEA and submission evidence | R | A | R | R | R |

Legend: A = accountable, R = responsible, C = consulted, I = informed.

## Approval Boundaries

- Riya and Akash approve software contracts and model acceptance evidence.
- Aratrik and Kartikay approve voltage levels, pin allocation, active states, and output safety behavior.
- Akash and Rudra approve camera geometry and mechanical mounting assumptions.
- Interface changes must be recorded in `docs/design_decisions.md` before dependent implementation changes.
