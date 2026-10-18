import json
from pathlib import Path

from software.ml.tests.test_onnx_adapter import fixture_configuration


def test_local_image_cli_uses_explicit_profile_and_persists(tmp_path, monkeypatch, capsys):
    from software.inspection.__main__ import main
    profile, manifest, model_root = fixture_configuration(tmp_path)
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "profile.json").write_text(profile.model_dump_json(), encoding="utf-8")
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    image = Path(__file__).resolve().parents[2] / "fixtures" / "images" / "clean.png"
    database = tmp_path / "audit.sqlite3"
    monkeypatch.setattr("sys.argv", ["inspection", str(image), "--profile-catalog", str(catalog),
                                     "--profile", "metal-plate-v1@9.0.0", "--model-manifest", str(manifest_path),
                                     "--model-root", str(model_root), "--db", str(database)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["result"] == "RECHECK"
    assert database.is_file()
