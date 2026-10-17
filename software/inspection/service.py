"""One local replay through the inherited edge pipeline and audit store."""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import numpy as np

from software.backend.database import AuditStore
from software.common.schemas import (
    DetectionBox, InspectionDecision, InspectionResult, LatencyBreakdown, PokaYokeStatus,
    WatchdogAlert,
)
from software.edge.decision.engine import decide
from software.edge.inference.base import InferenceEngine
from software.edge.io_control.gpio import MockGPIOController
from software.edge.pipeline import InspectionPipeline
from software.edge.watchdog.monitor import Watchdog
from software.inspection.events import build_event
from software.inspection.replay import ReplayError, ReplayFrameSource, Scenario, ScenarioCatalog


log = logging.getLogger(__name__)


class ScenarioDetector(InferenceEngine):
    """Scenario-driven simulation: the image pixels do not determine burr confidence."""

    name = "scenario-driven-burr-simulator"

    def __init__(self, scenario: Scenario):
        self.scenario = scenario

    def infer(self, frame: np.ndarray) -> list[DetectionBox]:
        if self.scenario.detection_class is None:
            return []
        return [DetectionBox(
            class_name=self.scenario.detection_class,
            confidence=self.scenario.detection_confidence,
            bbox=[0, 0, 0, 0],  # no image-derived localization
        )]


class _CaptureSink:
    def __init__(self):
        self.result: InspectionResult | None = None
        self.alerts: list[WatchdogAlert] = []

    def publish_result(self, result: InspectionResult) -> None:
        self.result = result

    def publish_alert(self, alert: WatchdogAlert) -> None:
        self.alerts.append(alert)


class ReplayService:
    def __init__(self, store: AuditStore, fixture_dir: str | Path):
        self.store = store
        self.catalog = ScenarioCatalog(fixture_dir)
        self.gpio = MockGPIOController()

    def inspect(self, scenario_name: str, event_id: str | None = None) -> tuple[dict, bool]:
        scenario = self.catalog.get(scenario_name)
        requested_id = UUID(event_id) if event_id else None
        if requested_id is not None:
            existing = self.store.canonical_inspection(str(requested_id))
            if existing is not None:
                return existing, False

        self.gpio.show_result(InspectionDecision.RECHECK)  # clear any previous PASS
        source = ReplayFrameSource(self.catalog.fixture_dir / "images", scenario)
        sink = _CaptureSink()
        try:
            with source:
                pipeline = InspectionPipeline(
                    source, ScenarioDetector(scenario), self.gpio, Watchdog(),
                    lambda: -1.0, sinks=[sink],
                )
                try:
                    pipeline.run_once()
                except Exception:
                    log.exception("replay pipeline failed")
                    self.gpio.show_fault()
                    sink.result = InspectionResult(
                        result=InspectionDecision.RECHECK,
                        confidence=0.0,
                        poka_yoke_status=PokaYokeStatus(part_present=False),
                        per_stage_latency_ms=LatencyBreakdown.from_stages(0, 0, 0, 0),
                        soc_temp_c=-1,
                    )
                    fault = "PIPELINE_ERROR"
                else:
                    fault = source.last_error.code if source.last_error else None
            result = sink.result
            if result is None:
                raise RuntimeError("inspection pipeline produced no audit result")
            if requested_id:
                result = result.model_copy(update={"inspection_id": requested_id})
            if fault:
                reason = fault.replace("_", " ").lower()
            else:
                reason = decide(result.poka_yoke_status, result.detections).reason
            event = build_event(result, scenario, source.last_packet, reason, fault)
            event["mock_io_state"] = {
                "green": self.gpio.state.green,
                "red": self.gpio.state.red,
                "amber": self.gpio.state.amber,
                "buzzer": self.gpio.state.buzzer,
                "ring_light_pwm": self.gpio.state.ring_pwm_pct,
            }
            inserted = self.store.append_inspection_pair(result, event)
            if not inserted:
                existing = self.store.canonical_inspection(event["event_id"])
                return existing, False
            return event, True
        except Exception:
            self.gpio.show_fault()
            raise
