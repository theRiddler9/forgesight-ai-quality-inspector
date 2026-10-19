# ForgeSight Project Goals

## Stage 2 Objective

Design and virtually validate a low-cost, edge-AI quality-inspection system for MSMEs. The Stage 2 result must be technically reproducible, auditable, and ready for physical construction in Stage 3.

## Binding Scope

- Inspect one metal component type.
- Detect heavy burrs as the primary defect.
- Run all inspection logic locally on an Orange Pi 5.
- Combine deterministic OpenCV Poka-Yoke checks with an INT8 RKNN detector.
- Produce PASS, FAIL, or RECHECK with an auditable reason.
- Store inspection events in SQLite and expose them through FastAPI and WebSocket.
- Display live status, history, yield, and fault information in a touchscreen HMI.
- Use COTS mechanical and electrical components with a hardware BOM below Rs 10,000.
- Validate Stage 2 with source files, simulations, tests, benchmark logs, and screenshots.

## Stage 2 Acceptance Targets

| Area | Target | Evidence |
|---|---|---|
| Cost | Hardware BOM below Rs 10,000 | Itemized sourcing sheet |
| End-to-end latency | At or below 100 ms per inspection | Per-stage Orange Pi benchmark log |
| Heavy-burr recall | Above 95% on the held-out real test set | Evaluation report and confusion matrix |
| Structural safety | Factor of Safety above 2.0 | SolidWorks static FEA |
| Thermal performance | SoC below 65 C at 45 C ambient | Thermal calculation and sustained benchmark |
| GPIO isolation | All external industrial I/O opto-isolated | KiCad schematic and interconnect table |

## Explicitly Outside Stage 2

- Physical prototype fabrication.
- Shop-floor deployment or production claims.
- Long-duration field reliability claims.
- Closed-loop reject actuators.
- Multi-part or multi-camera inspection.
- Cloud services.
- Defect classes beyond heavy burrs unless the primary acceptance target is already met.

## Open Team Decisions

The following decisions do not block repository and contract work, but must be closed before dataset collection:

1. Exact physical component and its nominal dimensions.
2. Operational definition and minimum measurable size of a heavy burr.
3. Maximum acceptable false-reject rate.
4. Exact Stage 2 submission deadline.

Until these are approved, software must use recorded fixtures and configuration-driven dimensions rather than hard-coded part assumptions.
