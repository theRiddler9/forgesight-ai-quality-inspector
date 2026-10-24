"""CLI tests for profile-aware ONNX inference benchmark wiring."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from software.ml.benchmarks import onnx_cli
from software.ml.model_manifest import ModelManifest
from software.profiles.models import ComponentProfile
from software.profiles.registry import ProfileRegistry


def bundle(tmp_path):
    """Build compatible provisional profile and manifest files for CLI tests."""
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    model_root = tmp_path / "models"
    model_root.mkdir()
    artifact = model_root / "test.onnx"
    artifact.write_bytes(b"test-only model artifact")
    base = ProfileRegistry(Path(__file__).parents[2] / "profiles" / "catalog").active
    profile_data = base.model_dump(mode="json")
    profile_data["version"] = "9.1.0"
    profile_data["preprocessing"].update(model_width=base.image.width, model_height=base.image.height)
    profile_data["detector"].update(
        backend="onnx", model_id="test-onnx", model_version="1.2.3",
        artifact_path=artifact.name,
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        compatible_profiles=["metal-plate-v1@9.1.0"],
    )
    profile = ComponentProfile.model_validate(profile_data)
    (catalog / "test.json").write_text(profile.model_dump_json(), encoding="utf-8")
    manifest = ModelManifest(
        schema_version="1.0.0", model_id=profile.detector.model_id,
        model_version=profile.detector.model_version, backend="onnx",
        compatible_profile="metal-plate-v1@9.1.0", profile_fingerprint=profile.fingerprint,
        artifact_path=artifact.name, artifact_sha256=profile.detector.artifact_sha256,
        input_width=profile.preprocessing.model_width, input_height=profile.preprocessing.model_height,
        pixel_format="RGB_FLOAT32", preprocessing_fingerprint=profile.preprocessing_fingerprint,
        class_map={name: index for index, name in enumerate(profile.detector.defect_classes)},
        fail_confidence=profile.thresholds.fail_confidence,
        recheck_confidence=profile.thresholds.recheck_confidence,
        output_format="yolo11_raw_v1", model_purpose="trained_unverified",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    return catalog, model_root, manifest_path, profile


class FakeDetector:
    """Record submitted frames while exposing a declared CPU provider."""
    def __init__(self, profile, manifest, model_root):
        """Retain constructor inputs for contract assertions."""
        self.profile, self.manifest, self.model_root = profile, manifest, model_root
        self.frames = []
        self.session = type("Session", (), {"get_providers": lambda self: ["CPUExecutionProvider"]})()

    def detect(self, frame):
        """Capture one frame without depending on model execution."""
        self.frames.append(frame)
        return object()


def arguments(tmp_path, catalog, model_root, manifest_path, frames_path, layout="bgr"):
    """Assemble the standard profile-aware benchmark command arguments."""
    return [
        "--profile-catalog", str(catalog), "--profile", "metal-plate-v1@9.1.0",
        "--model-manifest", str(manifest_path), "--model-root", str(model_root),
        "--frames", str(frames_path), "--input-layout", layout,
        "--target-label", "dev-computer", "--warmup", "0", "--repetitions", "2",
        "--output", str(tmp_path / "report.json"),
    ]


def test_onnx_cli_benchmarks_single_bgr_frame_and_writes_artifact_provenance(monkeypatch, tmp_path):
    """A valid frame produces profile, model, provider, and sample metadata."""
    catalog, model_root, manifest_path, profile = bundle(tmp_path)
    frame = np.zeros((profile.image.height, profile.image.width, 3), dtype=np.uint8)
    frames_path = tmp_path / "frame.npy"
    np.save(frames_path, frame)
    real_load = np.load
    load_options = {}

    def load_frames(*args, **kwargs):
        """Record NumPy loading options while calling the real loader."""
        load_options.update(kwargs)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(onnx_cli.np, "load", load_frames)
    detector = FakeDetector(profile, None, model_root)
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *args: detector)

    assert onnx_cli.main(arguments(tmp_path, catalog, model_root, manifest_path, frames_path)) == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["model_id"] == "test-onnx"
    assert report["target_label_is_metadata_only"] is True
    assert report["artifact"]["filename"] == "test.onnx"
    assert report["onnx_context"]["profile_id"] == "metal-plate-v1"
    assert report["onnx_context"]["profile_version"] == "9.1.0"
    assert report["onnx_context"]["model_version"] == "1.2.3"
    assert report["onnx_context"]["execution_providers"] == ["CPUExecutionProvider"]
    assert report["onnx_context"]["model_initialization_ms"] >= 0
    assert report["onnx_context"]["timing_scope"] == "detector_call_including_preprocess_postprocess"
    assert len(report["latency_ms"]["samples"]) == 2
    assert len(detector.frames) == 2
    assert detector.frames[0].dtype == np.uint8
    assert "mmap_mode" not in load_options
    assert load_options["allow_pickle"] is False


def test_onnx_cli_benchmarks_batch_as_individual_frames(monkeypatch, tmp_path):
    """A BGR batch submits separate full-resolution frames to the detector."""
    catalog, model_root, manifest_path, profile = bundle(tmp_path)
    frames_path = tmp_path / "batch.npy"
    np.save(frames_path, np.zeros((2, profile.image.height, profile.image.width, 3), dtype=np.uint8))
    detector = FakeDetector(profile, None, model_root)
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *args: detector)
    assert onnx_cli.main(arguments(tmp_path, catalog, model_root, manifest_path, frames_path, "bgr-batch")) == 0
    assert len(detector.frames) == 2
    assert all(frame.shape == (profile.image.height, profile.image.width, 3) for frame in detector.frames)


@pytest.mark.parametrize(
    "frame",
    [
        np.zeros((700, 1200, 3), dtype=np.uint8),
        np.zeros((800, 1280, 3), dtype=np.float32),
        np.zeros((800, 1280, 1), dtype=np.uint8),
    ],
)
def test_onnx_cli_rejects_incompatible_frames_before_detector_creation(monkeypatch, tmp_path, frame):
    """Wrong shape, pixel type, or channel count fails before model loading."""
    catalog, model_root, manifest_path, _profile = bundle(tmp_path)
    frames_path = tmp_path / "bad.npy"
    np.save(frames_path, frame)
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *_: pytest.fail("detector should not be created"))
    with pytest.raises(SystemExit):
        onnx_cli.main(arguments(tmp_path, catalog, model_root, manifest_path, frames_path))


def test_onnx_cli_rejects_invalid_profile_reference(tmp_path):
    """A profile selector must include exactly one ID and version."""
    catalog, model_root, manifest_path, _profile = bundle(tmp_path)
    frames_path = tmp_path / "frame.npy"
    np.save(frames_path, np.zeros((800, 1280, 3), dtype=np.uint8))
    args = arguments(tmp_path, catalog, model_root, manifest_path, frames_path)
    args[args.index("metal-plate-v1@9.1.0")] = "invalid"
    with pytest.raises(SystemExit):
        onnx_cli.main(args)


def test_onnx_cli_reports_unknown_profile_without_traceback(monkeypatch, tmp_path):
    """An unknown component version yields a controlled CLI error."""
    catalog, model_root, manifest_path, profile = bundle(tmp_path)
    frames_path = tmp_path / "frame.npy"
    np.save(frames_path, np.zeros((profile.image.height, profile.image.width, 3), dtype=np.uint8))
    args = arguments(tmp_path, catalog, model_root, manifest_path, frames_path)
    args[args.index("metal-plate-v1@9.1.0")] = "missing-profile@1.0.0"
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *_: pytest.fail("unknown profile must fail first"))
    with pytest.raises(SystemExit):
        onnx_cli.main(args)


def test_onnx_cli_rejects_empty_batch_before_detector_creation(monkeypatch, tmp_path):
    """A zero-frame batch cannot initialize a benchmark detector."""
    catalog, model_root, manifest_path, profile = bundle(tmp_path)
    frames_path = tmp_path / "empty.npy"
    np.save(frames_path, np.zeros((0, profile.image.height, profile.image.width, 3), dtype=np.uint8))
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *_: pytest.fail("empty batch must fail first"))
    with pytest.raises(SystemExit):
        onnx_cli.main(arguments(tmp_path, catalog, model_root, manifest_path, frames_path, "bgr-batch"))


def test_onnx_cli_runs_generated_fixture_through_real_cpu_runtime(tmp_path):
    """The deterministic graph executes in ONNX Runtime and records test provenance."""
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from software.ml.fixture_model import write_fixture_bundle

    bundle_dir = tmp_path / "onnx-fixture"
    write_fixture_bundle(bundle_dir)
    frames_path = tmp_path / "frames.npy"
    np.save(frames_path, np.zeros((800, 1280, 3), dtype=np.uint8))
    output_path = tmp_path / "report.json"
    args = [
        "--profile-catalog", str(bundle_dir / "catalog"),
        "--profile", "metal-plate-v1@9.0.0",
        "--model-manifest", str(bundle_dir / "model-manifest.json"),
        "--model-root", str(bundle_dir / "models"),
        "--frames", str(frames_path), "--input-layout", "bgr",
        "--target-label", "test-cpu-only", "--warmup", "1", "--repetitions", "2",
        "--output", str(output_path),
    ]

    assert onnx_cli.main(args) == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["model_id"] == "adapter-test-constant"
    assert report["artifact"]["filename"] == "adapter-test.onnx"
    assert report["onnx_context"]["model_purpose"] == "adapter_test_fixture"
    assert report["onnx_context"]["execution_providers"] == ["CPUExecutionProvider"]
    assert len(report["latency_ms"]["samples"]) == 2
