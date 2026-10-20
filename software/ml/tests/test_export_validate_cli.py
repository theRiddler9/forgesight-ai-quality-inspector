"""CLI tests for static ONNX export preflight."""

import json

import numpy as np
import pytest

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
