from pathlib import Path

import pytest

from software.backend.database import AuditStore
from software.inspection.events import validate_event
from software.inspection.service import ReplayService
from software.ml.tests.test_onnx_adapter import fixture_configuration


ROOT = Path(__file__).resolve().parents[2]


def test_local_image_runs_actual_onnx_and_persists_test_fixture_recheck(tmp_path):
    profile, manifest, model_root = fixture_configuration(tmp_path)
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), ROOT / "fixtures")
    raw = (ROOT / "fixtures" / "images" / "clean.png").read_bytes()
    event, inserted = service.inspect_image_bytes(raw, profile, manifest, model_root, "clean.png")
    assert inserted
    validate_event(event)
    assert event["result"] == "RECHECK"
    assert event["model"]["runtime"] == "onnx"
    assert event["model"]["purpose"] == "adapter_test_fixture"
    assert event["defects"][0]["type"] == "burr"
    assert event["defects"][0]["bbox_normalized"] == pytest.approx([440/1280, 300/800, 400/1280, 200/800])
    assert event["latency_ms"]["inference"] > 0
    assert event["simulation"] == {"synthetic_fixture": False, "scenario_driven_detector": False,
                                   "mock_io": True, "test_model": True}
    assert event["image"]["sha256"]
    assert not service.gpio.state.green and service.gpio.state.amber
    assert service.store.canonical_inspection(event["event_id"]) == event


@pytest.mark.parametrize("fault", ["corrupt_image", "wrong_dimensions", "missing_model", "wrong_profile", "missing_calibration"])
def test_local_onnx_faults_cannot_pass(tmp_path, fault):
    profile, manifest, model_root = fixture_configuration(tmp_path)
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), ROOT / "fixtures")
    raw = (ROOT / "fixtures" / "images" / "clean.png").read_bytes()
    if fault == "corrupt_image":
        raw = b"not an image"
    elif fault == "wrong_dimensions":
        raw = (ROOT / "fixtures" / "images" / "clean.png").read_bytes()
        import cv2
        import numpy as np
        decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        raw = cv2.imencode(".png", decoded[:500])[1].tobytes()
    elif fault == "missing_model":
        (model_root / manifest.artifact_path).unlink()
    elif fault == "wrong_profile":
        profile = profile.model_copy(update={"version": "9.0.1"})
    else:
        profile = profile.model_copy(update={"calibration": profile.calibration.model_copy(update={"required": True, "reference": None})})
    event, _ = service.inspect_image_bytes(raw, profile, manifest, model_root, "input.png")
    assert event["result"] == "RECHECK"
    assert event["faults"]
    assert not service.gpio.state.green
    assert service.store.canonical_inspection(event["event_id"]) == event


def test_real_runtime_failure_is_persisted_as_recheck(tmp_path, monkeypatch):
    from software.inspection.onnx_detector import OnnxDetector
    profile, manifest, model_root = fixture_configuration(tmp_path)
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), ROOT / "fixtures")
    monkeypatch.setattr(OnnxDetector, "infer", lambda *_: (_ for _ in ()).throw(TimeoutError("runtime timeout")))
    event, _ = service.inspect_image_bytes((ROOT / "fixtures" / "images" / "clean.png").read_bytes(),
                                           profile, manifest, model_root)
    assert event["result"] == "RECHECK"
    assert event["faults"] == ["PIPELINE_ERROR"]
    assert service.gpio.state.amber and not service.gpio.state.green
