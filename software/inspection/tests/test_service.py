from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from software.backend.database import AuditStore
from software.common.schemas import InspectionDecision
from software.inspection.events import validate_event
from software.inspection.service import ReplayService
from software.profiles.registry import ProfileRegistry


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.mark.parametrize(
    "scenario,expected,light",
    [
        ("clean_part", "PASS", "green"),
        ("heavy_burr", "FAIL", "red"),
        ("uncertain_burr", "RECHECK", "amber"),
        ("missing_hole", "FAIL", "red"),
        ("no_part", "RECHECK", "amber"),
        ("capture_fault", "RECHECK", "amber"),
    ],
)
def test_six_scenarios_persist_and_drive_mock_outputs(tmp_path, scenario, expected, light):
    store = AuditStore(tmp_path / "audit.sqlite3")
    service = ReplayService(store, FIXTURES)
    event, inserted = service.inspect(scenario)
    assert inserted
    validate_event(event)
    assert event["result"] == expected
    assert getattr(service.gpio.state, light)
    assert not (service.gpio.state.green and expected != "PASS")
    assert store.canonical_inspection(event["event_id"]) == event
    assert store.latest_inspection().result == InspectionDecision(expected)
    assert event["simulation"]["scenario_driven_detector"]
    if scenario == "capture_fault":
        assert event["faults"] == ["CAMERA_UNAVAILABLE"]
    if scenario == "missing_hole":
        assert "MISSING_HOLE" in event["poka_yoke"]["reasons"]


def test_repeating_event_id_does_not_duplicate_or_change_result(tmp_path):
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES)
    first, inserted = service.inspect("clean_part")
    assert inserted
    again, inserted = service.inspect("heavy_burr", event_id=first["event_id"])
    assert not inserted
    assert again == first
    assert service.store.canonical_history(None, 10, 0)[1] == 1


def test_persistence_failure_forces_safe_mock_state(tmp_path, monkeypatch):
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES)

    def fail(*_args):
        raise RuntimeError("database offline")

    monkeypatch.setattr(service.store, "append_inspection_pair", fail)
    with pytest.raises(RuntimeError, match="database offline"):
        service.inspect("clean_part")
    assert not service.gpio.state.green
    assert service.gpio.state.amber


def test_concurrent_replays_keep_each_committed_output_state(tmp_path, monkeypatch):
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES)
    from software.inspection import service as service_module

    original = service_module.build_event
    clean_waiting = Event()
    burr_reached_builder = Event()

    def delayed_event(result, scenario, packet, reason, fault=None, profile=None):
        if scenario.name == "clean_part":
            clean_waiting.set()
            burr_reached_builder.wait(0.5)
        else:
            burr_reached_builder.set()
        return original(result, scenario, packet, reason, fault, profile)

    monkeypatch.setattr(service_module, "build_event", delayed_event)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.inspect, "clean_part")
        assert clean_waiting.wait(2)
        second = pool.submit(service.inspect, "heavy_burr")
        clean = first.result()[0]
        burr = second.result()[0]
    assert clean["result"] == "PASS" and clean["mock_io_state"]["green"]
    assert burr["result"] == "FAIL" and burr["mock_io_state"]["red"]


def test_profile_identity_is_persisted_and_thresholds_change_without_decision_rewrite(tmp_path):
    catalog = Path(__file__).resolve().parents[2] / "profiles" / "catalog"
    registry = ProfileRegistry(catalog)
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES, registry)
    first, _ = service.inspect("heavy_burr")
    assert first["result"] == "FAIL"
    assert first["component_profile"]["fingerprint"] == registry.active.fingerprint
    assert first["model"]["runtime"] == "mock"
    assert service.store.canonical_inspection(first["event_id"]) == first
    second_profile = registry.active.model_copy(update={
        "version": "1.0.1",
        "thresholds": registry.active.thresholds.model_copy(update={"fail_confidence": 0.95}),
        "detector": registry.active.detector.model_copy(update={"compatible_profiles": ["metal-plate-v1@1.0.1"]}),
    })
    registry._profiles[(second_profile.profile_id, second_profile.version)] = second_profile
    registry.select("metal-plate-v1", "1.0.1")
    second, _ = service.inspect("heavy_burr")
    assert second["result"] == "RECHECK"
    assert second["component_profile"]["fingerprint"] == second_profile.fingerprint
    assert service.store.canonical_inspection(first["event_id"]) == first


def test_unavailable_real_detector_cannot_pass(tmp_path):
    catalog = Path(__file__).resolve().parents[2] / "profiles" / "catalog"
    registry = ProfileRegistry(catalog)
    real = registry.active.model_copy(update={
        "version": "2.0.0",
        "detector": registry.active.detector.model_copy(update={
            "backend": "onnx", "artifact_path": "models/plate.onnx",
            "artifact_sha256": "a" * 64, "compatible_profiles": ["metal-plate-v1@2.0.0"],
        }),
    })
    registry._profiles[(real.profile_id, real.version)] = real
    registry.select("metal-plate-v1", "2.0.0")
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES, registry)
    event, _ = service.inspect("clean_part")
    assert event["result"] == "RECHECK"
    assert event["faults"] == ["DETECTOR_UNAVAILABLE"]
    assert not service.gpio.state.green


def test_unsupported_geometry_profile_fails_closed(tmp_path):
    catalog = Path(__file__).resolve().parents[2] / "profiles" / "catalog"
    registry = ProfileRegistry(catalog)
    unsupported = registry.active.model_copy(update={
        "version": "3.0.0",
        "geometry": registry.active.geometry.model_copy(update={"adapter": "annular_v1"}),
        "detector": registry.active.detector.model_copy(update={"compatible_profiles": ["metal-plate-v1@3.0.0"]}),
    })
    registry._profiles[(unsupported.profile_id, unsupported.version)] = unsupported
    registry.select("metal-plate-v1", "3.0.0")
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES, registry)
    event, _ = service.inspect("clean_part")
    assert event["result"] == "RECHECK"
    assert event["faults"] == ["UNSUPPORTED_PROFILE"]
    assert service.store.canonical_inspection(event["event_id"]) == event


def test_profile_image_mismatch_fails_closed(tmp_path):
    catalog = Path(__file__).resolve().parents[2] / "profiles" / "catalog"
    registry = ProfileRegistry(catalog)
    mismatched = registry.active.model_copy(update={
        "version": "4.0.0",
        "image": registry.active.image.model_copy(update={"width": 640}),
        "detector": registry.active.detector.model_copy(update={"compatible_profiles": ["metal-plate-v1@4.0.0"]}),
    })
    registry._profiles[(mismatched.profile_id, mismatched.version)] = mismatched
    registry.select("metal-plate-v1", "4.0.0")
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES, registry)
    event, _ = service.inspect("clean_part")
    assert event["result"] == "RECHECK"
    assert event["faults"] == ["FRAME_FORMAT_MISMATCH"]
    assert not service.gpio.state.green


def test_changed_replay_preprocessing_cannot_silently_pass(tmp_path):
    catalog = Path(__file__).resolve().parents[2] / "profiles" / "catalog"
    registry = ProfileRegistry(catalog)
    changed = registry.active.model_copy(update={
        "version": "5.0.0",
        "preprocessing": registry.active.preprocessing.model_copy(update={"rotation_deg": 90}),
        "detector": registry.active.detector.model_copy(update={"compatible_profiles": ["metal-plate-v1@5.0.0"]}),
    })
    registry._profiles[(changed.profile_id, changed.version)] = changed
    registry.select("metal-plate-v1", "5.0.0")
    service = ReplayService(AuditStore(tmp_path / "audit.sqlite3"), FIXTURES, registry)
    event, _ = service.inspect("clean_part")
    assert event["result"] == "RECHECK"
    assert event["faults"] == ["UNSUPPORTED_PROFILE"]
