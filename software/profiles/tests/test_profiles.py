import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from software.profiles.models import ComponentProfile
from software.profiles.registry import ProfileRegistry, UnknownProfile


CATALOG = Path(__file__).resolve().parents[1] / "catalog"


def profile_data():
    return json.loads((CATALOG / "metal-plate-v1.json").read_text(encoding="utf-8"))


def test_default_profile_loads_and_fingerprint_is_stable():
    registry = ProfileRegistry(CATALOG)
    profile = registry.active
    assert profile.profile_id == "metal-plate-v1"
    assert profile.version == "1.0.0"
    assert profile.replay_suitable
    assert not profile.real_inspection_ready
    assert len(profile.fingerprint) == 64
    assert profile.fingerprint == ComponentProfile.model_validate(profile_data()).fingerprint
    assert registry.list_profiles() == [profile]


@pytest.mark.parametrize("edit", [
    lambda p: p.pop("geometry"),
    lambda p: p.update(version="v1"),
    lambda p: p["image"].update(width=-1),
    lambda p: p["roi"].update(x=0.9, width=0.2),
    lambda p: p["geometry"].update(rules=["magic_rule"]),
    lambda p: p["detector"].update(backend="tensorflow"),
    lambda p: p["thresholds"].update(fail_confidence=0.4),
    lambda p: p["detector"].update(compatible_profiles=["other@1.0.0"]),
    lambda p: p["geometry"].update(physical_dimensions_mm=[-1, 20]),
    lambda p: p["calibration"].update(required=True),
])
def test_invalid_profiles_are_rejected(edit):
    data = profile_data()
    edit(data)
    with pytest.raises((ValidationError, ValueError)):
        ComponentProfile.model_validate(data)


def test_registry_selects_versioned_profiles_without_mutating_previous(tmp_path):
    first = profile_data()
    second = profile_data()
    second["version"] = "1.1.0"
    second["detector"]["compatible_profiles"] = ["metal-plate-v1@1.1.0"]
    second["geometry"]["center_tolerance_px"] = 25
    (tmp_path / "one.json").write_text(json.dumps(first), encoding="utf-8")
    (tmp_path / "two.json").write_text(json.dumps(second), encoding="utf-8")
    registry = ProfileRegistry(tmp_path)
    old = registry.active
    registry.select("metal-plate-v1", "1.1.0")
    assert registry.active.version == "1.1.0"
    assert registry.active.fingerprint != old.fingerprint
    assert registry.get("metal-plate-v1", "1.0.0") == old
    with pytest.raises(UnknownProfile):
        registry.select("washer-v1", "1.0.0")
    assert registry.active.version == "1.1.0"


def test_real_backend_requires_model_metadata_and_calibration():
    data = profile_data()
    data["detector"].update(backend="onnx", artifact_path="models/plate.onnx", artifact_sha256="a" * 64)
    data["calibration"].update(required=True, reference="calibration/plate-v1.json", pixels_per_mm=10.0)
    data["validation_status"] = "provisional"
    profile = ComponentProfile.model_validate(data)
    assert not profile.replay_suitable
    assert not profile.real_inspection_ready
    data["detector"].pop("artifact_sha256")
    with pytest.raises(ValidationError):
        ComponentProfile.model_validate(data)
