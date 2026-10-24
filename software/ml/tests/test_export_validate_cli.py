"""CLI tests for static ONNX export preflight."""

import json

import numpy as np
import pytest
import jsonschema

from software.ml.export import validate


def test_export_cli_writes_static_validation_report(tmp_path):
    from software.ml.fixture_model import write_fixture_bundle

    bundle = tmp_path / "bundle"
    write_fixture_bundle(bundle)
    output = tmp_path / "reports" / "validation.json"
    status = validate.main([
        "--profile-catalog", str(bundle / "catalog"), "--profile", "metal-plate-v1@9.0.0",
        "--model-manifest", str(bundle / "model-manifest.json"), "--model-root", str(bundle / "models"),
        "--output", str(output),
    ])
    assert status == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["validation"] == "static_contract_valid"
    assert report["inference_executed"] is False
    assert report["hardware_verified"] is False
    assert report["graph"]["outputs"][0]["shape"] == [1, 5, 1]
    schema = json.loads((__import__("pathlib").Path(__file__).parents[1] / "export" / "validation-report.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(report)


@pytest.mark.parametrize("bad_profile", ["metal-plate-v1", "missing@1.0.0"])
def test_export_cli_rejects_invalid_profile_reference(tmp_path, bad_profile):
    from software.ml.fixture_model import write_fixture_bundle

    bundle = tmp_path / "bundle"
    write_fixture_bundle(bundle)
    with pytest.raises(SystemExit):
        validate.main([
            "--profile-catalog", str(bundle / "catalog"), "--profile", bad_profile,
            "--model-manifest", str(bundle / "model-manifest.json"), "--model-root", str(bundle / "models"),
            "--output", str(tmp_path / "report.json"),
        ])


def test_export_cli_rejects_corrupt_model_manifest(tmp_path):
    from software.ml.fixture_model import write_fixture_bundle

    bundle = tmp_path / "bundle"
    write_fixture_bundle(bundle)
    (bundle / "model-manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        validate.main([
            "--profile-catalog", str(bundle / "catalog"), "--profile", "metal-plate-v1@9.0.0",
            "--model-manifest", str(bundle / "model-manifest.json"), "--model-root", str(bundle / "models"),
            "--output", str(tmp_path / "report.json"),
        ])


@pytest.mark.parametrize("target", ["artifact", "manifest", "profile", "normalized-artifact"])
def test_export_cli_cannot_overwrite_validation_inputs(tmp_path, target):
    """A rejected report destination leaves each selected input byte-for-byte intact."""
    from software.ml.fixture_model import write_fixture_bundle

    bundle = tmp_path / "bundle"
    write_fixture_bundle(bundle)
    inputs = {
        "artifact": bundle / "models" / "adapter-test.onnx",
        "manifest": bundle / "model-manifest.json",
        "profile": bundle / "catalog" / "adapter-test.json",
        "normalized-artifact": bundle / "models" / ".." / "models" / "adapter-test.onnx",
    }
    output = inputs[target]
    before = output.read_bytes()
    with pytest.raises(SystemExit, match="2"):
        validate.main([
            "--profile-catalog", str(bundle / "catalog"), "--profile", "metal-plate-v1@9.0.0",
            "--model-manifest", str(bundle / "model-manifest.json"),
            "--model-root", str(bundle / "models"), "--output", str(output),
        ])
    assert output.read_bytes() == before


def test_export_cli_rejects_symlink_alias_of_manifest(tmp_path):
    """Resolving a symlink must protect the underlying manifest bytes."""
    from software.ml.fixture_model import write_fixture_bundle

    bundle = tmp_path / "bundle"
    write_fixture_bundle(bundle)
    manifest = bundle / "model-manifest.json"
    alias = tmp_path / "manifest-alias.json"
    try:
        alias.symlink_to(manifest)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this Windows host")
    before = manifest.read_bytes()
    with pytest.raises(SystemExit, match="2"):
        validate.main([
            "--profile-catalog", str(bundle / "catalog"), "--profile", "metal-plate-v1@9.0.0",
            "--model-manifest", str(manifest), "--model-root", str(bundle / "models"),
            "--output", str(alias),
        ])
    assert manifest.read_bytes() == before
