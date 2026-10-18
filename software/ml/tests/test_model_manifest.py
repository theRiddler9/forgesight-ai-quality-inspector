import hashlib
import json

import pytest

from software.ml.model_manifest import ModelArtifactError, ModelManifest, verify_model_artifact
from software.profiles.registry import ProfileRegistry
from pathlib import Path


def configured(tmp_path):
    profile = ProfileRegistry(Path(__file__).resolve().parents[2] / "profiles" / "catalog").active
    raw = b"adapter-test-artifact-not-an-inference-model"
    root = tmp_path / "models"
    root.mkdir()
    (root / "plate.onnx").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    detector = profile.detector.model_copy(update={"backend":"onnx", "artifact_path":"plate.onnx",
                                          "artifact_sha256":digest})
    profile = profile.model_copy(update={"detector":detector})
    data = {"schema_version":"1.0.0", "model_id":detector.model_id,
            "model_version":detector.model_version, "backend":"onnx",
            "compatible_profile":f"{profile.profile_id}@{profile.version}",
            "profile_fingerprint":profile.fingerprint, "artifact_path":"plate.onnx",
            "artifact_sha256":digest, "input_width":1280, "input_height":800,
            "pixel_format":"RGB_FLOAT32", "preprocessing_fingerprint":profile.preprocessing_fingerprint,
            "class_map":{"burr":0}, "fail_confidence":0.8, "recheck_confidence":0.5,
            "output_format":"yolo11_raw_v1", "model_purpose":"trained_unverified"}
    return profile, root, data


def test_valid_metadata_and_hash_do_not_claim_runtime_ready(tmp_path):
    profile, root, data = configured(tmp_path)
    report = verify_model_artifact(profile, ModelManifest.model_validate(data), root)
    assert report["artifact_hash_verified"]
    assert not report["inference_ready"]


def test_missing_tampered_and_incompatible_models_fail(tmp_path):
    profile, root, data = configured(tmp_path)
    manifest = ModelManifest.model_validate(data)
    (root / "plate.onnx").write_bytes(b"tampered")
    with pytest.raises(ModelArtifactError, match="hash"):
        verify_model_artifact(profile, manifest, root)
    (root / "plate.onnx").unlink()
    with pytest.raises(ModelArtifactError, match="missing"):
        verify_model_artifact(profile, manifest, root)
    bad = data | {"profile_fingerprint":"f" * 64}
    with pytest.raises(ModelArtifactError, match="profile"):
        verify_model_artifact(profile, ModelManifest.model_validate(bad), root)
