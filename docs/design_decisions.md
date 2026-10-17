# ForgeSight Design Decisions

This is the authoritative decision log for choices that affect more than one subsystem.

## Accepted Decisions

### DD-001 - COTS-first enclosure and frame

- **Decision:** Use an IP65 ABS junction box, 2020 extrusion, standard glands, isolators, and an external heatsink.
- **Reason:** Reduces Stage 2 cost, manufacturing lead time, and fabrication risk.
- **Consequence:** Custom 3D-printed enclosure concepts are historical references, not the current baseline.

### DD-002 - Hardware budget

- **Decision:** The binding hardware BOM target is below Rs 10,000.
- **Reason:** Newer project goals supersede the Rs 15,000 concept estimate.
- **Consequence:** Every hardware substitution must update the itemized BOM.

### DD-003 - Stage 2 validation boundary

- **Decision:** Stage 2 uses CAD, FEA, schematics, executable software, model evaluation, and benchmark evidence. Physical fabrication and shop-floor validation are Stage 3.
- **Reason:** Matches the current competition stage and available evidence.
- **Consequence:** Stage 2 materials must not claim completed physical or field tests.

### DD-004 - Burr-first acceptance scope

- **Decision:** Heavy burrs are the primary learned defect. Other defects are stretch objectives.
- **Reason:** A focused, measurable detector is more defensible than an under-supported multi-defect claim.
- **Consequence:** Dataset and KPI reports must separate heavy-burr acceptance from exploratory classes.

### DD-005 - Inspection result vocabulary

- **Decision:** Every completed inspection returns exactly one of `PASS`, `FAIL`, or `RECHECK`.
- **Reason:** Operators need a safe outcome for uncertain models, invalid geometry, and image-quality faults.
- **Consequence:** Uncertainty and recoverable acquisition/quality failures produce RECHECK, not an invented PASS or FAIL.

### DD-006 - Total latency target

- **Decision:** Track preprocessing, inference, postprocessing, decision, and I/O separately; use total trigger-to-decision time at or below 100 ms as the final KPI.
- **Reason:** Inference time alone does not represent production throughput.
- **Consequence:** All benchmark records require per-stage and total timing.

## Open Decisions

| ID | Decision needed | Owner(s) | Needed before | Temporary rule |
|---|---|---|---|---|
| OD-001 | Exact component and nominal dimensions | Akash, Riya | Dataset capture | Use configuration-driven fixtures only |
| OD-002 | Minimum heavy-burr definition | Akash, Riya | Labeling | Do not create acceptance labels |
| OD-003 | Maximum false-reject rate | Team | Threshold freeze | Report the measured value without claiming acceptance |
| OD-004 | Submission deadline | Team | Schedule freeze | Use the four-week relative roadmap |
| OD-005 | GPIO pins, voltage levels, and active states | Aratrik, Kartikay | Hardware I/O | Use the mock adapter only |
| OD-006 | Camera, lens, height, and field of view | Akash, Rudra, Kartikay | Dataset capture | Use recorded images and keep geometry configurable |

To close an open decision, add its accepted outcome, date, evidence, and approving owners. Do not delete the history.
