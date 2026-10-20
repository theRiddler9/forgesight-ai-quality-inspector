from datetime import datetime, timedelta, timezone
import asyncio
from functools import partial

from fastapi.testclient import TestClient

import software.backend.app as app_module
from software.backend.app import create_app as production_app
from software.backend.database import AuditStore
from software.common.schemas import (
    AlertSeverity,
    AlertType,
    InspectionDecision,
    InspectionResult,
    LatencyBreakdown,
    PokaYokeStatus,
    WatchdogAlert,
)

create_app = partial(production_app, allow_test_host=True)


def make_inspection(
    timestamp: datetime,
    result: InspectionDecision = InspectionDecision.PASS,
    soc_temp_c: float = 52.0,
    latency_ms: float = 47.0,
) -> InspectionResult:
    return InspectionResult(
        timestamp=timestamp,
        result=result,
        confidence=0.91,
        poka_yoke_status=PokaYokeStatus(),
        per_stage_latency_ms=LatencyBreakdown(
            capture_ms=latency_ms,
            poka_yoke_ms=0,
            npu_inference_ms=0,
            decision_ms=0,
            total_ms=latency_ms,
        ),
        soc_temp_c=soc_temp_c,
    )


def test_empty_read_routes_have_contract_shapes_and_cors(tmp_path):
    app = create_app(tmp_path / "audit.sqlite3")
    with TestClient(app) as client:
        health = client.get("/health")
        latest = client.get("/api/v1/inspections/latest")
        history = client.get("/api/v1/inspections/history")
        status = client.get("/api/v1/system/status")
        cors = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert set(health.json()) == {"status", "uptime_seconds"}
    assert health.json()["status"] == "ok"
    assert health.json()["uptime_seconds"] >= 0
    assert latest.json() is None
    assert history.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
    assert set(status.json()) == {
        "soc_temp_c",
        "soc_temp_timestamp",
        "ram_used_mb",
        "ram_total_mb",
        "fps",
        "avg_latency_ms",
    }
    assert status.json()["soc_temp_c"] is None
    assert status.json()["soc_temp_timestamp"] is None
    assert status.json()["avg_latency_ms"] is None
    assert status.json()["ram_total_mb"] > 0
    assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_trusted_host_accepts_bracketed_ipv6_authority(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3"), base_url="http://[::1]:8000") as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_component_profiles_are_read_only_and_identified(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3")) as client:
        response = client.get("/api/v1/component-profiles")
    assert response.status_code == 200
    assert response.json()["active"] == "metal-plate-v1@1.0.0"
    profile = response.json()["profiles"][0]
    assert profile["id"] == "metal-plate-v1"
    assert profile["validation_status"] == "provisional"
    assert profile["replay_suitable"]
    assert not profile["real_inspection_ready"]
    assert len(profile["fingerprint"]) == 64


def test_database_initialization_runs_outside_the_async_event_loop(tmp_path, monkeypatch):
    original_initialize = AuditStore.initialize
    calls = []

    def track_initialize(store):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            calls.append("worker")
        else:
            calls.append("event_loop")
        original_initialize(store)

    monkeypatch.setattr(app_module.AuditStore, "initialize", track_initialize)
    with TestClient(create_app(tmp_path / "audit.sqlite3")):
        pass

    assert calls == ["worker"]


def test_latest_and_history_return_shared_inspection_models(tmp_path):
    db_path = tmp_path / "audit.sqlite3"
    store = AuditStore(db_path)
    now = datetime.now(timezone.utc)
    first = make_inspection(now - timedelta(seconds=2))
    second = make_inspection(now - timedelta(seconds=1), InspectionDecision.FAIL)
    store.append_event("inspection_result", first)
    store.append_event("inspection_result", second)

    with TestClient(create_app(db_path)) as client:
        latest = client.get("/api/v1/inspections/latest")
        history = client.get("/api/v1/inspections/history?result=FAIL&limit=5&offset=0")

    assert latest.json()["inspection_id"] == str(second.inspection_id)
    assert history.json() == {
        "items": [second.model_dump(mode="json")],
        "total": 1,
        "limit": 5,
        "offset": 0,
    }


def test_history_rejects_invalid_query_values(tmp_path):
    with TestClient(create_app(tmp_path / "audit.sqlite3")) as client:
        assert client.get("/api/v1/inspections/history?limit=0").status_code == 422
        assert client.get("/api/v1/inspections/history?offset=-1").status_code == 422
        assert client.get("/api/v1/inspections/history?result=BAD").status_code == 422


def test_status_nulls_unavailable_temperature_and_preserves_sample_time(tmp_path):
    db_path = tmp_path / "audit.sqlite3"
    store = AuditStore(db_path)
    now = datetime.now(timezone.utc)
    sample_time = now - timedelta(minutes=3)
    store.append_event(
        "inspection_result", make_inspection(sample_time, soc_temp_c=-1.0)
    )
    with TestClient(create_app(db_path)) as client:
        unavailable = client.get("/api/v1/system/status").json()
    assert unavailable["soc_temp_c"] is None
    assert unavailable["soc_temp_timestamp"] is None

    store.append_event(
        "inspection_result",
        make_inspection(sample_time + timedelta(seconds=1), soc_temp_c=54.5),
    )
    with TestClient(create_app(db_path)) as client:
        available = client.get("/api/v1/system/status").json()
    assert available["soc_temp_c"] == 54.5
    assert datetime.fromisoformat(
        available["soc_temp_timestamp"].replace("Z", "+00:00")
    ) == sample_time + timedelta(seconds=1)


def test_status_rate_excludes_alerts(tmp_path):
    db_path = tmp_path / "audit.sqlite3"
    store = AuditStore(db_path)
    now = datetime.now(timezone.utc)
    store.append_event("inspection_result", make_inspection(now))
    store.append_event(
        "inspection_result",
        make_inspection(now - timedelta(seconds=1)),
    )
    store.append_event(
        "watchdog_alert",
        WatchdogAlert(
            alert_type=AlertType.PIPELINE_STALL,
            severity=AlertSeverity.CRITICAL,
            message="stall",
            timestamp=now,
        ),
    )

    with TestClient(create_app(db_path)) as client:
        status = client.get("/api/v1/system/status").json()

    assert status["fps"] == 0.4


def test_status_average_uses_latest_100_inspections(tmp_path):
    db_path = tmp_path / "audit.sqlite3"
    store = AuditStore(db_path)
    now = datetime.now(timezone.utc)
    for index in range(102):
        result = make_inspection(
            now - timedelta(seconds=10 * index), latency_ms=float(index)
        )
        store.append_event("inspection_result", result)

    with TestClient(create_app(db_path)) as client:
        status = client.get("/api/v1/system/status").json()

    assert status["avg_latency_ms"] == 49.5


def test_live_websocket_route_sends_events_from_the_hub(tmp_path):
    app = create_app(tmp_path / "audit.sqlite3")
    envelope = {"event": "inspection_result", "data": {"result": "PASS"}}
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            client.portal.call(app.state.websocket_hub.publish, envelope)
            assert websocket.receive_json() == envelope


def test_status_returns_503_when_system_memory_is_unavailable(tmp_path, monkeypatch):
    def fail_metrics():
        raise OSError("memory metrics unavailable")

    monkeypatch.setattr(app_module.psutil, "virtual_memory", fail_metrics)
    with TestClient(
        create_app(tmp_path / "audit.sqlite3"), raise_server_exceptions=False
    ) as client:
        response = client.get("/api/v1/system/status")

    assert response.status_code == 503
