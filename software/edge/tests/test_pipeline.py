import json
import time
from pathlib import Path

import jsonschema
import pytest

from software.common.schemas import (
    AlertType, DefectType, DetectionBox, InspectionDecision as R, InspectionResult,
)
from software.edge.acquisition.camera import SyntheticCamera
from software.edge.config import EdgeConfig
from software.edge.inference.stub_inference import StubInferenceEngine
from software.edge.io_control.gpio import MockGPIOController
from software.edge.main import main
from software.edge.pipeline import InspectionPipeline
from software.edge.sinks import JsonLinesSink
from software.edge.watchdog.monitor import Watchdog

SCHEMA = json.loads((Path(__file__).parents[2] / "schema.json").read_text())


class FixedEngine:
    name = "fixed"

    def __init__(self, detections):
        self.detections, self.calls = detections, 0

    def infer(self, frame):
        self.calls += 1
        return self.detections


def build(camera=None, engine=None, sinks=(), config=EdgeConfig()):
    gpio = MockGPIOController()
    pipe = InspectionPipeline(
        camera or SyntheticCamera(seed=1),
        engine or FixedEngine([]),
        gpio, Watchdog(), lambda: 52.0, sinks, config,
    )
    return pipe, gpio


def lights(g):
    s = g.state
    return (s.green, s.red, s.amber, s.buzzer)


def test_good_part_passes_and_lights_green():
    pipe, gpio = build()
    r = pipe.run_once()
    assert r.result == R.PASS and r.defect_type == DefectType.NONE
    assert lights(gpio) == (True, False, False, False)
    assert r.image_path is None


def test_result_conforms_to_json_schema_and_latency_sums():
    pipe, _ = build(engine=StubInferenceEngine(0.5, seed=2))
    for _ in range(10):
        r = pipe.run_once()
        jsonschema.validate(r.model_dump(mode="json"), SCHEMA)
        lat = r.per_stage_latency_ms
        assert lat.total_ms == pytest.approx(
            lat.capture_ms + lat.poka_yoke_ms + lat.npu_inference_ms + lat.decision_ms, abs=0.01
        )


def test_geometry_fault_fails_without_using_the_npu():
    engine = FixedEngine([])
    pipe, gpio = build(camera=SyntheticCamera(seed=1, geometry_fault_rate=1.0), engine=engine)
    r = pipe.run_once()
    assert r.result == R.FAIL and engine.calls == 0
    assert r.per_stage_latency_ms.npu_inference_ms == 0.0
    assert lights(gpio) == (False, True, False, True)


def test_ai_detection_fails_with_red_and_buzzer():
    engine = FixedEngine([DetectionBox(class_name="crack", confidence=0.93, bbox=[1, 2, 3, 4])])
    pipe, gpio = build(engine=engine)
    r = pipe.run_once()
    assert (r.result, r.defect_type) == (R.FAIL, DefectType.CRACK) and engine.calls == 1
    assert lights(gpio) == (False, True, False, True)


def test_uncertain_detection_rechecks_with_amber():
    engine = FixedEngine([DetectionBox(class_name="burr", confidence=0.65, bbox=[1, 2, 3, 4])])
    pipe, gpio = build(engine=engine)
    assert pipe.run_once().result == R.RECHECK
    assert lights(gpio) == (False, False, True, False)


def test_failed_frames_are_saved_only_for_non_pass(tmp_path):
    engine = FixedEngine([DetectionBox(class_name="crack", confidence=0.93, bbox=[1, 2, 3, 4])])
    pipe, _ = build(engine=engine, config=EdgeConfig(frame_dir=tmp_path))
    r = pipe.run_once()
    assert r.image_path and Path(r.image_path).exists()
    pipe_ok, _ = build(config=EdgeConfig(frame_dir=tmp_path / "ok"))
    assert pipe_ok.run_once().image_path is None


def test_failed_frame_write_publishes_result_without_path(tmp_path, monkeypatch, caplog):
    engine = FixedEngine([DetectionBox(class_name="crack", confidence=0.93, bbox=[1, 2, 3, 4])])
    out = tmp_path / "events.jsonl"
    pipe, _ = build(
        engine=engine,
        sinks=[JsonLinesSink(str(out))],
        config=EdgeConfig(frame_dir=tmp_path / "frames"),
    )
    monkeypatch.setattr("software.edge.pipeline.cv2.imwrite", lambda *_args: False)

    result = pipe.run_once()

    assert result.image_path is None
    assert "could not save failure frame" in caplog.text
    event = json.loads(out.read_text().splitlines()[0])
    assert event["data"]["image_path"] is None


def test_camera_loss_shows_fault_and_trips_watchdog():
    pipe, gpio = build(camera=SyntheticCamera(disconnect_after=1))
    assert pipe.run_once() is not None
    for _ in range(3):
        assert pipe.run_once() is None
    assert lights(gpio) == (False, False, True, True)
    assert [a.alert_type for a in pipe.watchdog.alerts] == [AlertType.CAMERA_DISCONNECTED]


def test_failed_capture_publishes_recheck_audit_record(tmp_path):
    out = tmp_path / "events.jsonl"
    pipe, _ = build(
        camera=SyntheticCamera(disconnect_after=0), sinks=[JsonLinesSink(str(out))]
    )

    assert pipe.run_once() is None
    event = json.loads(out.read_text().splitlines()[0])
    result = InspectionResult.model_validate(event["data"])
    assert event["event"] == "inspection_result"
    assert result.result == R.RECHECK
    assert result.confidence == 0.0
    assert not result.poka_yoke_status.part_present
    assert result.per_stage_latency_ms.npu_inference_ms == 0.0


def test_stall_fault_stays_latched_until_next_pass_decision():
    class Clock:
        value = 0.0

        def __call__(self):
            return self.value

    clock = Clock()
    watchdog = Watchdog(clock=clock)

    class SlowOnceEngine(FixedEngine):
        def infer(self, frame):
            self.calls += 1
            if self.calls == 1:
                clock.value = 0.25
                watchdog.check()
            return []

    gpio = MockGPIOController()
    pipe = InspectionPipeline(
        SyntheticCamera(seed=1), SlowOnceEngine([]), gpio, watchdog, lambda: 52.0
    )
    assert pipe.run_once().result == R.PASS
    assert lights(gpio) == (False, False, True, True)
    assert pipe.run_once().result == R.PASS
    assert lights(gpio) == (True, False, False, False)


def test_overheating_raises_warning_but_still_reports_result():
    gpio = MockGPIOController()
    pipe = InspectionPipeline(SyntheticCamera(seed=1), FixedEngine([]), gpio, Watchdog(), lambda: 68.0)
    assert pipe.run_once().result == R.PASS
    assert pipe.watchdog.alerts[0].alert_type == AlertType.OVERHEATING


def test_jsonl_sink_writes_websocket_envelopes(tmp_path):
    out = tmp_path / "events.jsonl"
    pipe, _ = build(sinks=[JsonLinesSink(str(out))])
    pipe.run_once()
    event = json.loads(out.read_text().splitlines()[0])
    assert event["event"] == "inspection_result"
    InspectionResult.model_validate(event["data"])


def test_cli_runs_end_to_end_with_all_mocks(capsys):
    assert main(["--mock-hardware", "--mock-camera", "--use-stub-engine", "--count", "15", "--interval-ms", "0"]) == 0
    out = capsys.readouterr().out
    assert "15 inspections" in out


def test_cli_fails_after_camera_cannot_produce_requested_inspections(tmp_path, monkeypatch, capsys):
    out = tmp_path / "failed-captures.jsonl"
    monkeypatch.setattr(
        "software.edge.main.create_camera",
        lambda *args, **kwargs: SyntheticCamera(disconnect_after=0),
    )

    status = main([
        "--mock-hardware", "--mock-camera", "--use-stub-engine",
        "--count", "2", "--interval-ms", "0", "--jsonl", str(out),
    ])

    events = [json.loads(line) for line in out.read_text().splitlines()]
    assert status != 0
    assert len([e for e in events if e["event"] == "inspection_result"]) == 3
    assert "0/2 successful inspections after 3 capture attempts" in capsys.readouterr().out


def test_cli_refuses_real_hardware_until_implemented():
    with pytest.raises(SystemExit):
        main(["--mock-camera", "--use-stub-engine"])
