# Contributing to ForgeSight

## Working Agreement

1. Work only within the folder owned by your subsystem unless an interface change is agreed first.
2. Make small, coherent commits after verification. Do not combine unrelated changes.
3. Keep native source files; an image or export alone is not an engineering deliverable.
4. Never report an estimate, simulation, or mock result as a physical test.
5. Record decisions that affect another subsystem in `docs/design_decisions.md`.

## Commit Format

Use:

```text
<work-package>: <delivered outcome>
```

Examples:

```text
R0: define inspection event schema
R1: add part-separated dataset manifest
R2: verify hole-presence replay rule
R6: persist operator review audit fields
```

Every commit must contain one concern and leave its affected checks passing.

## Evidence Rule

A completed engineering deliverable contains:

1. Native source.
2. Export or screenshot suitable for review.
3. Test, calculation, simulation, or benchmark output.
4. Configuration and version information needed to reproduce it.
5. Commit reference.

Place slide-ready copies in `evidence/` or `submission/assets/`, while keeping the authoritative source in its subsystem folder.

## Large Files

Use Git LFS for model binaries, raw datasets, videos, SolidWorks files, and other large artifacts. When data cannot be stored in Git, add a versioned manifest, checksum, access location, license/provenance, and retrieval instructions.

## Review Requirements

- Software contracts: Riya and Akash.
- Camera geometry or mounting: Akash and Rudra.
- GPIO, voltage, and safe-state behavior: Aratrik and Kartikay.
- Claims used in the submission: the accountable subsystem owner plus Riya for evidence traceability.
