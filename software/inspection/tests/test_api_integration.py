from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from software.backend.app import create_app
from software.inspection.events import validate_event


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


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
