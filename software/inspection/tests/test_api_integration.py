from pathlib import Path
from functools import partial

import pytest
from jsonschema import ValidationError
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from software.backend.app import create_app as production_app
from software.inspection.events import validate_event


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
create_app = partial(production_app, allow_test_host=True)


def test_replay_is_committed_before_websocket_and_retrievable(tmp_path):
    app = create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/inspections") as ws:
            response = client.post("/api/v1/inspections/replay", json={"scenario": "heavy_burr"})
            assert response.status_code == 200
            event = response.json()["event"]
            assert response.json()["inserted"]
            validate_event(event)
            assert event["result"] == "FAIL"
            assert client.get(f"/api/v1/inspections/{event['event_id']}").json() == event
            assert ws.receive_json() == {"event": "inspection_event", "data": event}
        history = client.get("/api/v1/inspections?result=FAIL&limit=1")
        assert history.json()["total"] == 1
        assert history.json()["items"] == [event]
        assert client.get("/api/v1/metrics/summary").json()["FAIL"] == 1


def test_six_scenario_api_results_and_idempotency(tmp_path):
    expected = {
        "clean_part": "PASS", "heavy_burr": "FAIL", "uncertain_burr": "RECHECK",
        "missing_hole": "FAIL", "no_part": "RECHECK", "capture_fault": "RECHECK",
    }
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        for name, decision in expected.items():
            response = client.post("/api/v1/inspections/replay", json={"scenario": name})
            assert response.status_code == 200, response.text
            assert response.json()["event"]["result"] == decision
        first = client.get("/api/v1/inspections?limit=1").json()["items"][0]
        duplicate = client.post(
            "/api/v1/inspections/replay",
            json={"scenario": "clean_part", "event_id": first["event_id"]},
        )
        assert duplicate.status_code == 200
        assert not duplicate.json()["inserted"]
        assert client.get("/api/v1/inspections").json()["total"] == 6
        assert client.get("/api/v1/metrics/summary").json()["total"] == 6


def test_invalid_scenario_and_remote_mutation_are_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        assert client.post("/api/v1/inspections/replay", json={"scenario": "../escape"}).status_code == 404
        assert client.post("/api/v1/inspections/replay", json={"scenario": "clean_part", "event_id": "bad"}).status_code == 422
        assert client.get("/api/v1/fixtures/../secret").status_code in {404, 400}


def test_review_keeps_original_decision_and_returns_history(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        event = client.post("/api/v1/inspections/replay", json={"scenario": "uncertain_burr"}).json()["event"]
        response = client.post(
            f"/api/v1/inspections/{event['event_id']}/review",
            json={"reviewer_id": "operator-1", "corrected_result": "FAIL", "note": "visible burr"},
        )
        assert response.status_code == 200
        assert client.get(f"/api/v1/inspections/{event['event_id']}").json()["result"] == "RECHECK"
        reviews = client.get(f"/api/v1/inspections/{event['event_id']}/reviews").json()
        assert len(reviews) == 1 and reviews[0]["corrected_result"] == "FAIL"


def test_database_failure_does_not_broadcast(tmp_path, monkeypatch):
    app = create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.audit_store, "append_inspection_pair", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
        response = client.post("/api/v1/inspections/replay", json={"scenario": "clean_part"})
        assert response.status_code == 503
        assert client.get("/api/v1/inspections").json()["total"] == 0
        assert app.state.websocket_hub.client_count == 0


@pytest.mark.parametrize("scenario,result", [
    ("clean_part", "PASS"), ("heavy_burr", "FAIL"),
    ("uncertain_burr", "RECHECK"), ("missing_hole", "FAIL"),
    ("no_part", "RECHECK"), ("capture_fault", "RECHECK"),
])
def test_scenario_commits_before_websocket_and_survives_restart(tmp_path, scenario, result):
    db_path = tmp_path / "audit.sqlite3"
    with TestClient(create_app(db_path, fixture_dir=FIXTURES)) as client:
        with client.websocket_connect("/ws/inspections") as ws:
            response = client.post("/api/v1/inspections/replay", json={"scenario": scenario})
            assert response.status_code == 200
            event = response.json()["event"]
            validate_event(event)
            assert event["result"] == result
            assert client.get(f"/api/v1/inspections/{event['event_id']}").json() == event
            assert ws.receive_json() == {"event": "inspection_event", "data": event}
    with TestClient(create_app(db_path, fixture_dir=FIXTURES)) as restarted:
        assert restarted.get(f"/api/v1/inspections/{event['event_id']}").json() == event


def test_websocket_rejects_foreign_origin(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/inspections", headers={"origin": "https://other.example"}):
                pass


def test_websocket_accepts_local_preview_origin(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        with client.websocket_connect("/ws/inspections", headers={"origin": "http://127.0.0.1:4173"}) as ws:
            response = client.post("/api/v1/inspections/replay", json={"scenario": "clean_part"})
            assert ws.receive_json()["data"]["event_id"] == response.json()["event"]["event_id"]


def test_health_mock_output_uses_canonical_ring_field(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        client.post("/api/v1/inspections/replay", json={"scenario": "capture_fault"})
        output = client.get("/api/v1/health").json()["mock_io_state"]
        assert output["amber"] is True
        assert output["ring_light_pwm"] == 0
        assert "ring_pwm_pct" not in output


def test_publish_failure_leaves_committed_event_retrievable(tmp_path, monkeypatch):
    app = create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)
    with TestClient(app) as client:
        def fail(_event):
            raise RuntimeError("socket fanout unavailable")
        monkeypatch.setattr(app.state.websocket_hub, "publish", fail)
        response = client.post("/api/v1/inspections/replay", json={"scenario": "clean_part"})
        assert response.status_code == 200
        event = response.json()["event"]
        assert client.get(f"/api/v1/inspections/{event['event_id']}").json() == event


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000", "testserver"])
def test_trusted_local_hosts_can_inspect(tmp_path, host):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        response = client.post(
            "/api/v1/inspections/replay", headers={"host": host}, json={"scenario": "clean_part"}
        )
        assert response.status_code == 200
        assert client.get("/api/v1/inspections").json()["total"] == 1


def test_untrusted_host_cannot_mutate_or_open_websocket(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        rejected = client.post(
            "/api/v1/inspections/replay",
            headers={"host": "attacker.example"}, json={"scenario": "clean_part"},
        )
        assert rejected.status_code == 400
        assert client.get("/api/v1/inspections").json()["total"] == 0
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/inspections", headers={"host": "attacker.example"}):
                pass


def test_production_host_configuration_excludes_testserver(tmp_path):
    with TestClient(production_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        rejected = client.post("/api/v1/inspections/replay", json={"scenario": "clean_part"})
        assert rejected.status_code == 400
        accepted = client.post(
            "/api/v1/inspections/replay", headers={"host": "localhost:8000"},
            json={"scenario": "clean_part"},
        )
        assert accepted.status_code == 200


def test_untrusted_host_cannot_append_review(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        event_id = client.post("/api/v1/inspections/replay", json={"scenario": "clean_part"}).json()["event"]["event_id"]
        rejected = client.post(
            f"/api/v1/inspections/{event_id}/review", headers={"host": "attacker.example"},
            json={"reviewer_id": "tester", "corrected_result": "FAIL", "note": "test"},
        )
        assert rejected.status_code == 400
        assert client.get(f"/api/v1/inspections/{event_id}/reviews").json() == []


def test_foreign_browser_origin_cannot_mutate_even_with_trusted_host(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)) as client:
        response = client.post(
            "/api/v1/inspections/replay",
            headers={"origin": "https://attacker.example"}, json={"scenario": "clean_part"},
        )
        assert response.status_code == 403
        assert client.get("/api/v1/inspections").json()["total"] == 0


def test_remote_client_cannot_mutate_with_trusted_host(tmp_path):
    with TestClient(
        create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES),
        client=("192.0.2.5", 12345),
    ) as client:
        response = client.post("/api/v1/inspections/replay", json={"scenario": "clean_part"})
        assert response.status_code == 403
        assert client.get("/api/v1/inspections").json()["total"] == 0


@pytest.mark.parametrize("stage,failure", [
    ("persistence", ValueError("private path C:/secret")),
    ("event_validation", ValidationError("private schema detail")),
])
def test_internal_validation_failure_returns_stable_error_and_safe_outputs(tmp_path, monkeypatch, stage, failure):
    app = create_app(tmp_path / "audit.sqlite3", fixture_dir=FIXTURES)
    with TestClient(app, raise_server_exceptions=False) as client:
        if stage == "persistence":
            monkeypatch.setattr(
                app.state.audit_store, "append_inspection_pair",
                lambda *_: (_ for _ in ()).throw(failure),
            )
        else:
            monkeypatch.setattr(
                "software.inspection.service.build_event",
                lambda *_: (_ for _ in ()).throw(failure),
            )
        response = client.post("/api/v1/inspections/replay", json={"scenario": "clean_part"})
        assert response.status_code == 503
        assert response.json() == {"detail": "inspection or audit unavailable"}
        assert client.get("/api/v1/inspections").json()["total"] == 0
        outputs = client.get("/api/v1/health").json()["mock_io_state"]
        assert outputs["green"] is False
        assert outputs["amber"] is True
