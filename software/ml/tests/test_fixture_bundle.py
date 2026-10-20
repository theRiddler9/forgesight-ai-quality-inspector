from pathlib import Path
import pytest

pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")

from software.ml.model_manifest import ModelManifest
from software.profiles.registry import ProfileRegistry


def test_test_only_bundle_registers_explicit_onnx_profile(tmp_path):
    from software.ml.fixture_model import write_fixture_bundle
    destination = tmp_path / "adapter-bundle"
    write_fixture_bundle(destination)
    registry = ProfileRegistry(destination / "catalog")
    profile = registry.get("metal-plate-v1", "9.0.0")
    manifest = ModelManifest.model_validate_json((destination / "model-manifest.json").read_text(encoding="utf-8"))
    assert registry.active.version == "1.0.0"
    assert profile.validation_status == "provisional"
    assert manifest.model_purpose == "adapter_test_fixture"
    assert (destination / "models" / manifest.artifact_path).is_file()
