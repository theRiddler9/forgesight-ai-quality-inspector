"""Adapt the team's InspectionResult to the Stage 2 canonical audit schema."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from software.common.schemas import InspectionDecision, InspectionResult
from software.inspection.replay import FramePacket, Scenario


@lru_cache(maxsize=1)
def event_schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "contracts" / "inspection-event.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_event(event: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(event_schema(), format_checker=jsonschema.FormatChecker()).validate(event)


def _geometry_reasons(result: InspectionResult) -> list[str]:
    status = result.poka_yoke_status
    if not status.part_present:
        return ["NO_PART"]
    reasons = []
    if not status.position_valid:
        reasons.append("PART_MISALIGNED")
    if not status.hole_present:
        reasons.append("MISSING_HOLE")
    if not status.size_in_range:
        reasons.append("SIZE_OUT_OF_RANGE")
    return reasons


def build_event(
    result: InspectionResult,
    scenario: Scenario,
    packet: FramePacket | None,
    decision_reason: str,
    fault_code: str | None = None,
) -> dict[str, Any]:
    """Create a schema-valid event without claiming a real part or trained model."""
    status = result.poka_yoke_status
    latency = result.per_stage_latency_ms
    width = packet.width if packet else 1
    height = packet.height if packet else 1
    defects = []
    for detection in result.detections:
        x1, y1, x2, y2 = detection.bbox
        defects.append({
            "type": detection.class_name,
            "confidence": detection.confidence,
            "bbox_normalized": [
                max(0.0, min(1.0, x1 / width)),
                max(0.0, min(1.0, y1 / height)),
                max(0.0, min(1.0, (x2 - x1) / width)),
                max(0.0, min(1.0, (y2 - y1) / height)),
            ] if packet and x2 > x1 and y2 > y1 else None,
        })
    event = {
        "schema_version": "1.0.0",
        "event_id": str(result.inspection_id),
        "timestamp": result.model_dump(mode="json")["timestamp"],
        # This identifies the virtual inspection profile, never a physical part.
        "part_id": "virtual-component-v1",
        "result": result.result.value,
        "defects": defects,
        "poka_yoke": {
            "part_present": status.part_present,
            "position_ok": status.position_valid if status.part_present else None,
            "orientation_ok": None,  # not independently measured by the team engine
            "hole_present": status.hole_present if status.part_present else None,
            "size_in_range": status.size_in_range if status.part_present else None,
            "reasons": _geometry_reasons(result),
        },
        "latency_ms": {
            "capture": latency.capture_ms,
            "preprocess": 0.0,
            "poka_yoke": latency.poka_yoke_ms,
            "inference": latency.npu_inference_ms,
            "postprocess": 0.0,
            "decision": latency.decision_ms,
            "io": 0.0,
            "total": latency.total_ms,
        },
        "soc_temperature_c": None if result.soc_temp_c == -1 else result.soc_temp_c,
        "image": {
            "source_id": packet.source_id if packet else "synthetic-recorded-v1",
            "input_uri": packet.source_uri if packet else f"scenario:{scenario.name}",
            "evidence_uri": result.image_path,
            "sha256": packet.sha256 if packet else None,
        },
        "model": {
            "name": "scenario-driven-burr-simulator",
            "version": "1.0.0",
            "runtime": "mock",
            "artifact_sha256": None,
        },
        "configuration_version": "virtual-profile-v1",
        "operator_review": {
            "status": "PENDING" if result.result == InspectionDecision.RECHECK else "NOT_REQUIRED",
            "reviewed_at": None,
            "reviewer_id": None,
            "corrected_result": None,
            "note": None,
        },
        "faults": [fault_code] if fault_code else [],
        "decision_reasons": [decision_reason],
        "simulation": {
            "synthetic_fixture": True,
            "scenario_driven_detector": True,
            "mock_io": True,
        },
        "scenario": scenario.name,
    }
    validate_event(event)
    return event
