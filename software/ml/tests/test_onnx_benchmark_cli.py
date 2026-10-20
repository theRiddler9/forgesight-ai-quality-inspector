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
    def __init__(self, profile, manifest, model_root):
        self.profile, self.manifest, self.model_root = profile, manifest, model_root
        self.frames = []

    def detect(self, frame):
        self.frames.append(frame)
        return object()


def arguments(tmp_path, catalog, model_root, manifest_path, frames_path, layout="bgr"):
    return [
        "--profile-catalog", str(catalog), "--profile", "metal-plate-v1@9.1.0",
        "--model-manifest", str(manifest_path), "--model-root", str(model_root),
        "--frames", str(frames_path), "--input-layout", layout,
        "--target-label", "dev-computer", "--warmup", "0", "--repetitions", "2",
        "--output", str(tmp_path / "report.json"),
    ]


def test_onnx_cli_benchmarks_single_bgr_frame_and_writes_artifact_provenance(monkeypatch, tmp_path):
    catalog, model_root, manifest_path, profile = bundle(tmp_path)
    frame = np.zeros((profile.image.height, profile.image.width, 3), dtype=np.uint8)
    frames_path = tmp_path / "frame.npy"
    np.save(frames_path, frame)
    real_load = np.load
    load_options = {}

    def load_frames(*args, **kwargs):
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
    assert len(report["latency_ms"]["samples"]) == 2
    assert len(detector.frames) == 2
    assert detector.frames[0].dtype == np.uint8
    assert "mmap_mode" not in load_options
    assert load_options["allow_pickle"] is False


def test_onnx_cli_benchmarks_batch_as_individual_frames(monkeypatch, tmp_path):
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
    catalog, model_root, manifest_path, _profile = bundle(tmp_path)
    frames_path = tmp_path / "bad.npy"
    np.save(frames_path, frame)
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *_: pytest.fail("detector should not be created"))
    with pytest.raises(SystemExit):
        onnx_cli.main(arguments(tmp_path, catalog, model_root, manifest_path, frames_path))


def test_onnx_cli_rejects_invalid_profile_reference(tmp_path):
    catalog, model_root, manifest_path, _profile = bundle(tmp_path)
    frames_path = tmp_path / "frame.npy"
    np.save(frames_path, np.zeros((800, 1280, 3), dtype=np.uint8))
    args = arguments(tmp_path, catalog, model_root, manifest_path, frames_path)
    args[args.index("metal-plate-v1@9.1.0")] = "invalid"
    with pytest.raises(SystemExit):
        onnx_cli.main(args)


def test_onnx_cli_reports_unknown_profile_without_traceback(monkeypatch, tmp_path):
    catalog, model_root, manifest_path, profile = bundle(tmp_path)
    frames_path = tmp_path / "frame.npy"
    np.save(frames_path, np.zeros((profile.image.height, profile.image.width, 3), dtype=np.uint8))
    args = arguments(tmp_path, catalog, model_root, manifest_path, frames_path)
    args[args.index("metal-plate-v1@9.1.0")] = "missing-profile@1.0.0"
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *_: pytest.fail("unknown profile must fail first"))
    with pytest.raises(SystemExit):
        onnx_cli.main(args)


def test_onnx_cli_rejects_empty_batch_before_detector_creation(monkeypatch, tmp_path):
    catalog, model_root, manifest_path, profile = bundle(tmp_path)
    frames_path = tmp_path / "empty.npy"
    np.save(frames_path, np.zeros((0, profile.image.height, profile.image.width, 3), dtype=np.uint8))
    monkeypatch.setattr(onnx_cli, "OnnxDetector", lambda *_: pytest.fail("empty batch must fail first"))
    with pytest.raises(SystemExit):
        onnx_cli.main(arguments(tmp_path, catalog, model_root, manifest_path, frames_path, "bgr-batch"))


def test_onnx_cli_runs_generated_fixture_through_real_cpu_runtime(tmp_path):
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
    assert len(report["latency_ms"]["samples"]) == 2
