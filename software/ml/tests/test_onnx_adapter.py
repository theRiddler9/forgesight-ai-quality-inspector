"""Actual runtime tests using a generated, deterministic adapter fixture graph."""
import hashlib
from pathlib import Path

import numpy as np
import pytest

from software.inspection.detectors import DetectorUnavailable
from software.ml.model_manifest import ModelManifest
from software.profiles.models import ComponentProfile
from software.profiles.registry import ProfileRegistry


def fixture_configuration(tmp_path, **fixture_kwargs):
    from software.ml.fixture_model import write_fixture_model

    model_root = tmp_path / "models"
    model_root.mkdir()
    artifact = model_root / "adapter-test.onnx"
    write_fixture_model(artifact, **fixture_kwargs)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    original = ProfileRegistry(Path(__file__).resolve().parents[2] / "profiles" / "catalog").active
    data = original.model_dump(mode="json")
    data["version"] = "9.0.0"
    data["preprocessing"].update(model_width=64, model_height=64)
    data["detector"].update(backend="onnx", model_id="adapter-test-constant", model_version="0.0.1",
                            artifact_path=artifact.name, artifact_sha256=digest,
                            compatible_profiles=["metal-plate-v1@9.0.0"])
    profile = ComponentProfile.model_validate(data)
    manifest = ModelManifest.model_validate({
        "schema_version": "1.0.0", "model_id": profile.detector.model_id,
        "model_version": profile.detector.model_version, "backend": "onnx",
        "compatible_profile": "metal-plate-v1@9.0.0", "profile_fingerprint": profile.fingerprint,
        "artifact_path": artifact.name, "artifact_sha256": digest,
        "input_width": 64, "input_height": 64, "pixel_format": "RGB_FLOAT32",
        "preprocessing_fingerprint": profile.preprocessing_fingerprint,
        "class_map": {"burr": 0}, "fail_confidence": 0.8, "recheck_confidence": 0.5,
        "output_format": "yolo11_raw_v1", "model_purpose": "adapter_test_fixture",
    })
    return profile, manifest, model_root


def test_actual_runtime_decodes_fixture_and_restores_image_box(tmp_path):
    from software.inspection.onnx_detector import OnnxDetector

    profile, manifest, root = fixture_configuration(tmp_path)
    detector = OnnxDetector(profile, manifest, root)
    output = detector.detect(np.zeros((800, 1280, 3), dtype=np.uint8))
    assert not output.simulated
    assert output.backend == "onnx" and output.model_id == "adapter-test-constant"
    assert len(output.detections) == 1
    detection = output.detections[0]
    assert detection.class_name == "burr" and detection.confidence == pytest.approx(0.9)
    assert detection.bbox == pytest.approx([440, 300, 840, 500])
    assert output.duration_ms >= 0


@pytest.mark.parametrize("change", ["hash", "shape", "classes", "artifact"])
def test_invalid_model_cannot_initialize(tmp_path, change):
    from software.inspection.onnx_detector import OnnxDetector

    profile, manifest, root = fixture_configuration(tmp_path)
    if change == "hash":
        manifest = manifest.model_copy(update={"artifact_sha256": "f" * 64})
    elif change == "shape":
        manifest = manifest.model_copy(update={"input_width": 32})
    elif change == "classes":
        manifest = manifest.model_copy(update={"class_map": {"wrong": 0}})
    else:
        (root / manifest.artifact_path).write_bytes(b"corrupted graph")
        manifest = manifest.model_copy(update={"artifact_sha256": hashlib.sha256(b"corrupted graph").hexdigest()})
        profile = profile.model_copy(update={"detector": profile.detector.model_copy(update={"artifact_sha256": manifest.artifact_sha256})})
        manifest = manifest.model_copy(update={"profile_fingerprint": profile.fingerprint})
    with pytest.raises(DetectorUnavailable):
        OnnxDetector(profile, manifest, root)


def test_actual_runtime_low_score_is_not_actionable(tmp_path):
    from software.inspection.onnx_detector import OnnxDetector
    profile, manifest, root = fixture_configuration(tmp_path, confidence=0.4)
    assert OnnxDetector(profile, manifest, root).detect(np.zeros((800, 1280, 3), dtype=np.uint8)).detections == ()


def test_unsupported_actual_output_is_rejected(tmp_path):
    from software.inspection.onnx_detector import OnnxDetector
    profile, manifest, root = fixture_configuration(tmp_path, output_channels=6)
    detector = OnnxDetector(profile, manifest, root)
    with pytest.raises(DetectorUnavailable, match="shape"):
        detector.detect(np.zeros((800, 1280, 3), dtype=np.uint8))


def test_runtime_failure_is_wrapped_as_unavailable(tmp_path, monkeypatch):
    from software.inspection.onnx_detector import OnnxDetector
    profile, manifest, root = fixture_configuration(tmp_path)
    detector = OnnxDetector(profile, manifest, root)
    monkeypatch.setattr(detector.session, "run", lambda *_: (_ for _ in ()).throw(RuntimeError("runtime failed")))
    with pytest.raises(DetectorUnavailable, match="runtime failed"):
        detector.detect(np.zeros((800, 1280, 3), dtype=np.uint8))


def test_missing_runtime_and_wrong_graph_input_fail_safely(tmp_path, monkeypatch):
    from software.inspection.onnx_detector import OnnxDetector
    import sys
    profile, manifest, root = fixture_configuration(tmp_path, input_height=32)
    with pytest.raises(DetectorUnavailable, match="input shape"):
        OnnxDetector(profile, manifest, root)
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    with pytest.raises(DetectorUnavailable, match="unavailable"):
        OnnxDetector(profile, manifest, root)
