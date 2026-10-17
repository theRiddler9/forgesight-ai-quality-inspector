import json
import random
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from software.common.schemas import (
    DetectionBox,
    InspectionDecision,
    InspectionResult,
    LatencyBreakdown,
    PokaYokeStatus,
    WatchdogAlert,
)
from software.edge.inference.stub_inference import (
    StubInferenceEngine,
    get_stub_inspection_result,
)

SCHEMA = json.loads((Path(__file__).parents[2] / "schema.json").read_text())


def test_schema_json_is_a_valid_draft7_schema():
    jsonschema.Draft7Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("seed", range(25))
def test_stub_result_satisfies_json_schema_and_pydantic(seed):
    payload = get_stub_inspection_result(0.5, rng=random.Random(seed))
    jsonschema.validate(payload, SCHEMA)
    parsed = InspectionResult.model_validate(payload)
    assert parsed.per_stage_latency_ms.total_ms <= 100.0
    assert parsed.soc_temp_c < 65.0


def test_pydantic_json_dump_satisfies_json_schema():
    result = InspectionResult(
        result=InspectionDecision.PASS,
        confidence=0.99,
        poka_yoke_status=PokaYokeStatus(),
        per_stage_latency_ms=LatencyBreakdown.from_stages(8, 12, 25, 2),
        soc_temp_c=52.0,
    )
    payload = result.model_dump(mode="json")
    jsonschema.validate(payload, SCHEMA)
    assert payload["timestamp"].endswith("Z")


def test_latency_total_is_sum_of_stages():
    lat = LatencyBreakdown.from_stages(8.0, 12.0, 25.0, 2.0)
    assert lat.total_ms == 47.0


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        DetectionBox(class_name="burr", confidence=1.5, bbox=[0, 0, 1, 1])


def test_bbox_must_have_four_values():
    with pytest.raises(ValidationError):
        DetectionBox(class_name="burr", confidence=0.9, bbox=[0, 0, 1])


def test_poka_yoke_all_ok_property():
    assert PokaYokeStatus().all_ok
    assert not PokaYokeStatus(hole_present=False).all_ok


def test_watchdog_alert_serialises():
    alert = WatchdogAlert(
        alert_type="pipeline_stall", severity="critical", message="stalled", value=250.0
    )
    assert alert.model_dump(mode="json")["alert_type"] == "pipeline_stall"


def test_stub_engine_is_seedable_and_returns_detection_boxes():
    a = StubInferenceEngine(1.0, seed=3).infer(None)
    b = StubInferenceEngine(1.0, seed=3).infer(None)
    assert a == b and a and isinstance(a[0], DetectionBox)
