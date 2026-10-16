"""One inspection: capture -> Poka-Yoke -> (NPU) -> decision + GPIO -> result.

Fixed Stage 2 order (AGENTS.md). Poka-Yoke failures skip the NPU.
"""
import logging
import time
from pathlib import Path
from typing import Callable, Optional, Sequence
from uuid import uuid4

import cv2

from software.common.schemas import (
    AlertSeverity,
    InspectionDecision,
    InspectionResult,
    LatencyBreakdown,
    WatchdogAlert,
)
from software.edge.acquisition.camera import FrameSource
from software.edge.acquisition.preprocess import adjust_contrast
from software.edge.config import EdgeConfig
from software.edge.decision.engine import decide
from software.edge.inference.base import InferenceEngine
from software.edge.io_control.gpio import GPIOController
from software.edge.poka_yoke.rules import check_poka_yoke
from software.edge.sinks import ResultSink
from software.edge.watchdog.monitor import Watchdog

log = logging.getLogger(__name__)


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


class InspectionPipeline:
    def __init__(
        self,
        camera: FrameSource,
        engine: InferenceEngine,
        gpio: GPIOController,
        watchdog: Watchdog,
        temp_reader: Callable[[], float],
        sinks: Sequence[ResultSink] = (),
        config: EdgeConfig = EdgeConfig(),
    ):
        self.camera, self.engine, self.gpio = camera, engine, gpio
        self.watchdog, self.temp_reader = watchdog, temp_reader
        self.sinks, self.config = list(sinks), config
        self.watchdog.subscribe(self._on_alert)

    def _on_alert(self, alert: WatchdogAlert) -> None:
        if alert.severity == AlertSeverity.CRITICAL:
            self.gpio.show_fault()
        for s in self.sinks:
            s.publish_alert(alert)

    def run_once(self) -> Optional[InspectionResult]:
        """Run one inspection on trigger. Returns None if no frame could be captured."""
        cfg = self.config
        self.watchdog.begin_inspection()
        try:
            # 1. capture + contrast adjustment
            t = time.perf_counter()
            frame = self.camera.read()
            if frame is None:
                self.watchdog.report_frame(False)
                self.gpio.show_fault()  # never leave the previous part's light on
                return None
            self.watchdog.report_frame(True)
            enhanced = adjust_contrast(frame, cfg.contrast_clip_limit)  # AI branch only
            capture_ms = _ms(t)

            # 2. deterministic geometry checks on the raw frame
            t = time.perf_counter()
            report = check_poka_yoke(frame, cfg.poka_yoke)
            poka_yoke_ms = _ms(t)

            # 3. NPU only when geometry is fine
            detections, npu_ms = [], 0.0
            if report.status.all_ok:
                t = time.perf_counter()
                detections = self.engine.infer(enhanced)
                npu_ms = _ms(t)

            # 4. decision + indicator outputs
            t = time.perf_counter()
            decision = decide(report.status, detections, cfg.thresholds)
            self.gpio.show_result(decision.result)
            decision_ms = _ms(t)

            # 5. bookkeeping (outside the latency budget)
            inspection_id = uuid4()
            image_path = None
            if cfg.frame_dir and decision.result != InspectionDecision.PASS:
                image_path = self._save_frame(frame, inspection_id)
            soc_c = self.temp_reader()
            self.watchdog.report_temperature(soc_c)

            result = InspectionResult(
                inspection_id=inspection_id,
                result=decision.result,
                defect_type=decision.defect_type,
                confidence=decision.confidence,
                poka_yoke_status=report.status,
                per_stage_latency_ms=LatencyBreakdown.from_stages(
                    capture_ms, poka_yoke_ms, npu_ms, decision_ms
                ),
                soc_temp_c=soc_c,
                detections=detections,
                image_path=image_path,
            )
            if result.per_stage_latency_ms.total_ms > cfg.latency_budget_ms:
                log.warning("latency %.1f ms exceeds %.0f ms budget", result.per_stage_latency_ms.total_ms, cfg.latency_budget_ms)
            for s in self.sinks:
                s.publish_result(result)
            return result
        finally:
            self.watchdog.end_inspection()

    def _save_frame(self, frame, inspection_id) -> str:
        directory = Path(self.config.frame_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{inspection_id}.jpg"
        cv2.imwrite(str(path), frame)
        return str(path)
