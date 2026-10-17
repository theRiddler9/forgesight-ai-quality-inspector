from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from software.backend.database import AuditStore
from software.common.schemas import InspectionDecision
from software.inspection.events import validate_event
from software.inspection.service import ReplayService


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

    def delayed_event(result, scenario, packet, reason, fault=None):
        if scenario.name == "clean_part":
            clean_waiting.set()
            burr_reached_builder.wait(0.5)
        else:
            burr_reached_builder.set()
        return original(result, scenario, packet, reason, fault)

    monkeypatch.setattr(service_module, "build_event", delayed_event)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.inspect, "clean_part")
        assert clean_waiting.wait(2)
        second = pool.submit(service.inspect, "heavy_burr")
        clean = first.result()[0]
        burr = second.result()[0]
    assert clean["result"] == "PASS" and clean["mock_io_state"]["green"]
    assert burr["result"] == "FAIL" and burr["mock_io_state"]["red"]
