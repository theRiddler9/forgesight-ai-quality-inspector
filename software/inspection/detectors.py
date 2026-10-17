"""Backend-neutral detector boundary. Real inference is unavailable until validated."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np

from software.common.schemas import DetectionBox
from software.inspection.replay import Scenario
from software.profiles.models import ComponentProfile


class DetectorUnavailable(RuntimeError):
    """A configured backend or compatible, verified artifact is unavailable."""


@dataclass(frozen=True)
class DetectorOutput:
    detections: tuple[DetectionBox, ...]
    backend: Literal["scenario_simulation", "onnx", "rknn"]
    model_id: str
    model_version: str
    duration_ms: float
    coordinate_system: Literal["image_pixels"] = "image_pixels"
    segmentation_polygons_normalized: tuple[tuple[tuple[float, float], ...], ...] | None = None
    uncertain: bool = False
    simulated: bool = True


class DetectorAdapter(Protocol):
    def detect(self, frame: np.ndarray) -> DetectorOutput: ...

    def infer(self, frame: np.ndarray) -> list[DetectionBox]: ...


class ScenarioDetector:
    """Scenario metadata drives the output; image pixels do not infer defects."""

    def __init__(self, scenario: Scenario, profile: ComponentProfile):
        self.scenario = scenario
        self.profile = profile

    def detect(self, frame: np.ndarray) -> DetectorOutput:
        start = time.perf_counter()
        if self.scenario.detection_class is None:
            detections = ()
        else:
            if self.scenario.detection_class not in self.profile.detector.defect_classes:
                raise DetectorUnavailable("scenario defect class incompatible with profile")
            detections = (DetectionBox(
                class_name=self.scenario.detection_class,
                confidence=self.scenario.detection_confidence,
                bbox=[0, 0, 0, 0],  # no image-derived localization
            ),)
        return DetectorOutput(
            detections=detections,
            backend="scenario_simulation",
            model_id=self.profile.detector.model_id,
            model_version=self.profile.detector.model_version,
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            uncertain=bool(detections and self.profile.thresholds.recheck_confidence <= detections[0].confidence < self.profile.thresholds.fail_confidence),
        )

    def infer(self, frame: np.ndarray) -> list[DetectionBox]:
        return list(self.detect(frame).detections)


class UnavailableRealDetector:
    """Fail closed; this is an integration boundary, not fake inference."""

    def __init__(self, profile: ComponentProfile):
        self.profile = profile

    def detect(self, frame: np.ndarray) -> DetectorOutput:
        raise DetectorUnavailable(f"{self.profile.detector.backend} inference is not installed or validated")

    def infer(self, frame: np.ndarray) -> list[DetectionBox]:
        self.detect(frame)
        raise AssertionError("unreachable")


def detector_for(profile: ComponentProfile, scenario: Scenario) -> DetectorAdapter:
    if profile.detector.backend == "scenario_simulation":
        return ScenarioDetector(scenario, profile)
    return UnavailableRealDetector(profile)
