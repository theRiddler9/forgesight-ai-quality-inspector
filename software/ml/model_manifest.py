"""Artifact identity verification; approval is separate from adapter execution."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from software.profiles.models import ComponentProfile


class ModelArtifactError(ValueError):
    pass


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0.0"]
    model_id: str = Field(min_length=1)
    model_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    backend: Literal["onnx", "rknn"]
    compatible_profile: str = Field(min_length=1)
    profile_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_width: int = Field(ge=32)
    input_height: int = Field(ge=32)
    pixel_format: Literal["RGB_FLOAT32"]
    preprocessing_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    class_map: dict[str, int] = Field(min_length=1)
    fail_confidence: float = Field(ge=0, le=1)
    recheck_confidence: float = Field(ge=0, le=1)
    output_format: Literal["yolo11_raw_v1"]
    model_purpose: Literal["adapter_test_fixture", "trained_unverified", "trained_validated"]

    @model_validator(mode="after")
    def internal_consistency(self):
        path = PurePosixPath(self.artifact_path)
        if path.is_absolute() or ".." in path.parts or "\\" in self.artifact_path or ":" in self.artifact_path:
            raise ValueError("model path must be relative to model root")
        if sorted(self.class_map.values()) != list(range(len(self.class_map))):
            raise ValueError("model class IDs must be contiguous from zero")
        if self.recheck_confidence >= self.fail_confidence:
            raise ValueError("threshold ordering invalid")
        return self


def verify_model_artifact(profile: ComponentProfile, manifest: ModelManifest, model_root: str | Path) -> dict:
    reference = f"{profile.profile_id}@{profile.version}"
    if manifest.compatible_profile != reference or manifest.profile_fingerprint != profile.fingerprint:
        raise ModelArtifactError("model incompatible with component profile")
    detector = profile.detector
    if (manifest.backend != detector.backend or manifest.model_id != detector.model_id
            or manifest.model_version != detector.model_version
            or manifest.artifact_path != detector.artifact_path
            or manifest.artifact_sha256 != detector.artifact_sha256):
        raise ModelArtifactError("model metadata differs from profile detector reference")
    if [name for name, _ in sorted(manifest.class_map.items(), key=lambda pair: pair[1])] != detector.defect_classes:
        raise ModelArtifactError("model classes differ from profile")
    if (manifest.input_width != (profile.preprocessing.model_width or profile.image.width)
            or manifest.input_height != (profile.preprocessing.model_height or profile.image.height)
            or manifest.preprocessing_fingerprint != profile.preprocessing_fingerprint):
        raise ModelArtifactError("model input or preprocessing incompatible with profile")
    if (manifest.fail_confidence != profile.thresholds.fail_confidence
            or manifest.recheck_confidence != profile.thresholds.recheck_confidence):
        raise ModelArtifactError("model thresholds differ from profile")
    root = Path(model_root).resolve()
    artifact = (root / manifest.artifact_path).resolve()
    if not artifact.is_relative_to(root):
        raise ModelArtifactError("model path escapes model root")
    if not artifact.is_file():
        raise ModelArtifactError("model artifact missing")
    digest = hashlib.sha256()
    with artifact.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest.artifact_sha256:
        raise ModelArtifactError("model artifact hash mismatch")
    runtime_module = "onnxruntime" if manifest.backend == "onnx" else "rknn"
    return {"artifact_hash_verified": True, "runtime_available": importlib.util.find_spec(runtime_module) is not None,
            "inference_ready": False, "reason": "artifact identity alone does not establish model validation or operational approval"}
