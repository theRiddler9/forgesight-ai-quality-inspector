import json
from pathlib import Path

import jsonschema

from software.common.schemas import (
    DetectionBox,
    InspectionDecision,
    InspectionResult,
    LatencyBreakdown,
    PokaYokeStatus,
)
from software.inspection.events import build_event, validate_event
from software.inspection.replay import ReplayFrameSource, ScenarioCatalog


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "software" / "fixtures"


def test_existing_example_remains_valid_after_additive_schema_change():
    example = json.loads((ROOT / "software/contracts/examples/inspection-event.example.json").read_text())
    validate_event(example)


def test_canonical_event_has_explicit_simulation_and_decision_reason():
    scenario = ScenarioCatalog(FIXTURES).get("heavy_burr")
    with ReplayFrameSource(FIXTURES / "images", scenario) as source:
        packet = source.capture()
    result = InspectionResult(
        result=InspectionDecision.FAIL,
        defect_type="burr",
        confidence=0.91,
        poka_yoke_status=PokaYokeStatus(),
        per_stage_latency_ms=LatencyBreakdown.from_stages(2, 3, 1, 1),
        soc_temp_c=-1,
        detections=[DetectionBox(class_name="burr", confidence=0.91, bbox=[1, 2, 3, 4])],
    )
    event = build_event(result, scenario, packet, "burr detected")
    validate_event(event)
    assert event["event_id"] == str(result.inspection_id)
    assert event["decision_reasons"] == ["burr detected"]
    assert event["simulation"] == {
        "synthetic_fixture": True, "scenario_driven_detector": True, "mock_io": True
    }
    assert event["image"]["sha256"] == packet.sha256
    assert event["model"]["runtime"] == "mock"
    assert event["soc_temperature_c"] is None


def test_capture_fault_has_no_fabricated_image_hash():
    scenario = ScenarioCatalog(FIXTURES).get("capture_fault")
    result = InspectionResult(
        result=InspectionDecision.RECHECK,
        confidence=0,
        poka_yoke_status=PokaYokeStatus(part_present=False),
        per_stage_latency_ms=LatencyBreakdown.from_stages(0, 0, 0, 0),
        soc_temp_c=-1,
    )
    event = build_event(result, scenario, None, "capture unavailable", "CAMERA_UNAVAILABLE")
    validate_event(event)
    assert event["image"]["sha256"] is None
    assert event["faults"] == ["CAMERA_UNAVAILABLE"]
    assert event["part_id"] == "virtual-component-v1"
