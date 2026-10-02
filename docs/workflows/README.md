# ForgeSight Workflows

This folder converts the Stage 2 plan into checkable operating workflows.

## Active Workflow

- [`riya-stage2-execution-workflow.md`](riya-stage2-execution-workflow.md) - Riya's ordered software, edge-AI, integration, validation, and submission workflow.
- [`../forgesight-stage2-work-plan.md`](../forgesight-stage2-work-plan.md) - master scope, responsibilities, schedule, risks, and source reconciliation.

## How to Use This Folder

1. Keep only one primary gate active at a time.
2. Update the dashboard whenever a gate changes state.
3. Store evidence while doing the work, not at the end.
4. Do not mark a gate done until its acceptance check passes.
5. Record cross-team blockers with an owner, date, required decision, and impact.

The checklists here are project workflows, not GitHub Actions. Automated build and test workflows can be added under `.github/workflows/` after the software skeleton and test commands exist.
