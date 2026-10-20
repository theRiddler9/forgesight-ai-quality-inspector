from pathlib import Path
from functools import partial
import pytest

pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")

from fastapi.testclient import TestClient

from software.backend.app import create_app as production_app
from software.ml.tests.test_onnx_adapter import fixture_configuration


ROOT = Path(__file__).resolve().parents[2]
create_app = partial(production_app, allow_test_host=True)


def test_local_upload_commits_before_websocket_and_detail(tmp_path):
    profile, manifest, model_root = fixture_configuration(tmp_path)
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    from software.profiles.registry import ProfileRegistry
    default = ProfileRegistry(ROOT / "profiles" / "catalog").active
    (catalog / "default.json").write_text(default.model_dump_json(), encoding="utf-8")
    (catalog / "plate.json").write_text(profile.model_dump_json(), encoding="utf-8")
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    app = create_app(tmp_path / "audit.sqlite3", ROOT / "fixtures",
                     profile_catalog=catalog, model_manifest_path=manifest_path, model_root=model_root)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/inspections") as ws:
            response = client.post("/api/v1/inspections/image?profile_id=metal-plate-v1&version=9.0.0",
                                   content=(ROOT / "fixtures" / "images" / "clean.png").read_bytes(),
                                   headers={"content-type": "image/png"})
            assert response.status_code == 200, response.text
            event = response.json()["event"]
            assert event["result"] == "RECHECK" and event["model"]["purpose"] == "adapter_test_fixture"
            assert client.get(f"/api/v1/inspections/{event['event_id']}").json() == event
            assert ws.receive_json() == {"event": "inspection_event", "data": event}


def test_upload_rejects_unsupported_type_and_size(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", ROOT / "fixtures")) as client:
        assert client.post("/api/v1/inspections/image?profile_id=metal-plate-v1&version=1.0.0",
                           content=b"bad", headers={"content-type": "text/plain"}).status_code == 415
        assert client.post("/api/v1/inspections/image?profile_id=metal-plate-v1&version=1.0.0",
                           content=b"x" * (8 * 1024 * 1024 + 1),
                           headers={"content-type": "image/png"}).status_code == 413
