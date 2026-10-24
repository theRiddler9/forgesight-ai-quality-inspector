"""Static ONNX export contract tests using the deterministic fixture graph."""

import hashlib
from pathlib import Path

import numpy as np
import pytest

from software.ml.export.onnx_contract import ExportValidationError, inspect_onnx_graph, validate_onnx_artifact
from software.ml.model_manifest import ModelManifest
from software.profiles.models import ComponentProfile
from software.profiles.registry import ProfileRegistry

onnx = pytest.importorskip("onnx")
from onnx.external_data_helper import convert_model_to_external_data


def make_bundle(tmp_path, *, output_channels=5, input_height=64, input_width=64):
    from software.ml.fixture_model import write_fixture_model

    root = tmp_path / "models"
    root.mkdir()
    artifact = root / "fixture.onnx"
    write_fixture_model(artifact, output_channels=output_channels, input_height=input_height)
    base = ProfileRegistry(Path(__file__).parents[2] / "profiles" / "catalog").active
    profile_data = base.model_dump(mode="json")
    profile_data["version"] = "9.2.0"
    profile_data["preprocessing"].update(model_width=input_width, model_height=input_height)
    profile_data["detector"].update(
        backend="onnx", model_id="fixture", model_version="1.0.0",
        artifact_path=artifact.name, artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        compatible_profiles=["metal-plate-v1@9.2.0"],
    )
    profile = ComponentProfile.model_validate(profile_data)
    manifest = ModelManifest(
        schema_version="1.0.0", model_id="fixture", model_version="1.0.0", backend="onnx",
        compatible_profile="metal-plate-v1@9.2.0", profile_fingerprint=profile.fingerprint,
        artifact_path=artifact.name, artifact_sha256=profile.detector.artifact_sha256,
        input_width=input_width, input_height=input_height, pixel_format="RGB_FLOAT32",
        preprocessing_fingerprint=profile.preprocessing_fingerprint,
        class_map={"burr": 0}, fail_confidence=0.8, recheck_confidence=0.5,
        output_format="yolo11_raw_v1", model_purpose="adapter_test_fixture",
    )
    return profile, manifest, root, artifact


def test_inspection_returns_static_graph_metadata(tmp_path):
    _profile, _manifest, _root, artifact = make_bundle(tmp_path)
    graph = inspect_onnx_graph(artifact)
    assert graph["inputs"][0]["shape"] == [1, 3, 64, 64]
    assert graph["inputs"][0]["dtype"] == 1
    assert graph["outputs"][0]["shape"] == [1, 5, 1]


def test_validation_matches_profile_manifest_and_artifact(tmp_path):
    profile, manifest, root, artifact = make_bundle(tmp_path)
    report = validate_onnx_artifact(profile, manifest, root)
    assert report["validation"] == "static_contract_valid"
    assert report["inference_executed"] is False
    assert report["hardware_verified"] is False
    assert report["artifact"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert report["profile"]["fingerprint"] == profile.fingerprint


@pytest.mark.parametrize(
    "change",
    ["wrong-input-size", "wrong-output-channels", "wrong-hash", "wrong-backend"],
)
def test_validation_rejects_contract_mismatches(tmp_path, change):
    profile, manifest, root, _artifact = make_bundle(tmp_path)
    if change == "wrong-input-size":
        manifest = manifest.model_copy(update={"input_width": 32})
    elif change == "wrong-output-channels":
        manifest = manifest.model_copy(update={"class_map": {"burr": 0, "scratch": 1}})
    elif change == "wrong-hash":
        manifest = manifest.model_copy(update={"artifact_sha256": "f" * 64})
    else:
        manifest = manifest.model_copy(update={"backend": "rknn"})
    with pytest.raises(ExportValidationError):
        validate_onnx_artifact(profile, manifest, root)


def test_validation_rejects_missing_artifact(tmp_path):
    profile, manifest, root, artifact = make_bundle(tmp_path)
    artifact.unlink()
    with pytest.raises(ExportValidationError, match="missing"):
        validate_onnx_artifact(profile, manifest, root)


def _externalize_fixture(artifact):
    """Move an initializer to an adjacent, deliberately untracked weights file."""
    graph = onnx.load(str(artifact))
    convert_model_to_external_data(
        graph, all_tensors_to_one_file=True, location="weights.bin", size_threshold=0,
    )
    onnx.save_model(graph, str(artifact))
    return artifact.with_name("weights.bin")


def test_external_tensor_data_is_rejected_before_path_dependent_check(tmp_path, monkeypatch):
    """External tensors are unsupported even when their sidecar exists elsewhere."""
    _profile, _manifest, _root, artifact = make_bundle(tmp_path)
    weights = _externalize_fixture(artifact)
    assert weights.is_file()
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    with pytest.raises(ExportValidationError, match="external tensor data"):
        inspect_onnx_graph(artifact)
    weights.unlink()
    with pytest.raises(ExportValidationError, match="external tensor data"):
        inspect_onnx_graph(artifact)


def test_external_weights_cannot_hide_behind_verified_onnx_hash(tmp_path):
    """The current single-file identity contract rejects untracked sidecars."""
    profile, manifest, root, artifact = make_bundle(tmp_path)
    weights = _externalize_fixture(artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    profile_data = profile.model_dump(mode="json")
    profile_data["detector"]["artifact_sha256"] = digest
    profile = ComponentProfile.model_validate(profile_data)
    manifest = manifest.model_copy(update={
        "artifact_sha256": digest, "profile_fingerprint": profile.fingerprint,
    })
    weights.write_bytes(b"changed external weights")
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
    with pytest.raises(ExportValidationError, match="external tensor data"):
        validate_onnx_artifact(profile, manifest, root)


def test_full_check_rejects_inferable_output_shape_disagreement(tmp_path):
    """A declared output dimension that contradicts Add must fail static checks."""
    _profile, _manifest, _root, artifact = make_bundle(tmp_path)
    graph = onnx.load(str(artifact))
    graph.graph.output[0].type.tensor_type.shape.dim[-1].dim_value = 2
    onnx.save_model(graph, str(artifact))
    with pytest.raises(ExportValidationError, match="invalid ONNX graph"):
        inspect_onnx_graph(artifact)
