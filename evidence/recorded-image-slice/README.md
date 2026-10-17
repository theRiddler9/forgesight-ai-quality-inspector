# Recorded-image browser evidence

These screenshots were captured from the rendered Chrome HMI by `npm run test:e2e` with `FORGESIGHT_CAPTURE_EVIDENCE=1` set on 2026-10-17, using the `recorded-image-slice` branch at code revision `32961f1` and the synthetic fixtures in `software/fixtures/`. The test ran a local FastAPI backend, Vite preview, and a unique temporary SQLite database. The source of truth is the Playwright test in `software/frontend/e2e/inspection.spec.ts` and the canonical audit event stored by that test.

| Screenshot | Visible evidence |
|---|---|
| `clean_part.png` | PASS, synthetic fixture, mock outputs, and history |
| `heavy_burr.png` | FAIL with scenario-driven simulated burr |
| `uncertain_burr.png` | RECHECK for uncertain simulated burr |
| `capture_fault.png` | RECHECK for simulated capture failure |
| `inspection-detail.png` | Decision, geometry, detector, faults, timing, and simulation metadata |
| `history-metrics-health.png` | Six-scenario history, counts, chart, and mock I/O health |
| `operator-review.png` | Append-only operator review while original RECHECK remains visible |

The images are **software demonstration evidence only**. They do not show a trained model, real metal-part images, Orange Pi performance, electrical GPIO behavior, or physical safety validation. Timestamps, UUIDs, and local timing values belong to this one test run and are not benchmarks.
