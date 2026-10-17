from pathlib import Path

import numpy as np
import pytest

from software.inspection.detectors import DetectorUnavailable, ScenarioDetector, detector_for
from software.inspection.replay import ScenarioCatalog
from software.profiles.registry import ProfileRegistry


ROOT = Path(__file__).resolve().parents[2]


def test_simulated_detector_is_explicit_and_has_no_fabricated_location():
    profile = ProfileRegistry(ROOT / "profiles" / "catalog").active
    scenario = ScenarioCatalog(ROOT / "fixtures").get("heavy_burr")
    output = ScenarioDetector(scenario, profile).detect(np.zeros((800, 1280, 3), dtype=np.uint8))
    assert output.simulated
    assert output.backend == "scenario_simulation"
    assert output.coordinate_system == "image_pixels"
    assert output.model_id == profile.detector.model_id
    assert output.detections[0].confidence == 0.91
    assert output.detections[0].bbox == [0, 0, 0, 0]
    assert output.duration_ms >= 0
    assert output.segmentation_polygons_normalized is None
    assert not output.uncertain


def test_simulated_uncertainty_uses_profile_thresholds():
    profile = ProfileRegistry(ROOT / "profiles" / "catalog").active
    scenario = ScenarioCatalog(ROOT / "fixtures").get("uncertain_burr")
    output = ScenarioDetector(scenario, profile).detect(np.zeros((800, 1280, 3), dtype=np.uint8))
    assert output.uncertain


def test_real_detector_boundary_fails_without_runtime_or_artifact():
    profile = ProfileRegistry(ROOT / "profiles" / "catalog").active
    real = profile.model_copy(update={"detector": profile.detector.model_copy(update={"backend": "onnx"})})
    scenario = ScenarioCatalog(ROOT / "fixtures").get("clean_part")
    detector = detector_for(real, scenario)
    with pytest.raises(DetectorUnavailable, match="not installed or validated"):
        detector.infer(np.zeros((800, 1280, 3), dtype=np.uint8))
