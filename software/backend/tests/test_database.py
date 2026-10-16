import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from software.backend.database import AuditStore
import software.backend.database as database_module
from software.common.schemas import (
    AlertSeverity,
    AlertType,
    InspectionDecision,
    InspectionResult,
    LatencyBreakdown,
    PokaYokeStatus,
    WatchdogAlert,
)


def inspection(timestamp: datetime, result: InspectionDecision = InspectionDecision.PASS):
    return InspectionResult(
        timestamp=timestamp,
        result=result,
        confidence=0.91,
        poka_yoke_status=PokaYokeStatus(),
        per_stage_latency_ms=LatencyBreakdown.from_stages(8, 12, 25, 2),
        soc_temp_c=52.0,
    )


def test_audit_store_enables_wal_and_rejects_updates_and_deletes(tmp_path):
    path = tmp_path / "audit.sqlite3"
    store = AuditStore(path)
    record = inspection(datetime(2026, 10, 16, tzinfo=timezone.utc))
    assert store.append_event("inspection_result", record)

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE audit_events SET result = 'FAIL'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM audit_events")


def test_ingestion_errors_keep_only_a_bounded_raw_sample(tmp_path):
    path = tmp_path / "audit.sqlite3"
    store = AuditStore(path)
    raw_line = b"x" * 5000

    store.record_ingestion_error(23, raw_line, "invalid utf-8")

    with sqlite3.connect(path) as connection:
        offset, sample, reason = connection.execute(
            "SELECT byte_offset, raw_sample, reason FROM ingestion_errors"
        ).fetchone()
    assert offset == 23
    assert sample == b"x" * 4096
    assert reason == "invalid utf-8"


def test_each_operation_closes_its_sqlite_connection(tmp_path, monkeypatch):
    store = AuditStore(tmp_path / "audit.sqlite3")
    original_connect = database_module.sqlite3.connect
    connections = []

    class TrackingConnection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(database_module.sqlite3, "connect", tracked_connect)
    assert store.latest_inspection() is None

    assert len(connections) == 1
    assert connections[0].closed


def test_append_event_is_idempotent_and_shared_models_round_trip(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    timestamp = datetime(2026, 10, 16, tzinfo=timezone.utc)
    result = inspection(timestamp)
    alert = WatchdogAlert(
        alert_type=AlertType.PIPELINE_STALL,
        severity=AlertSeverity.CRITICAL,
        message="stalled",
        timestamp=timestamp,
        value=250.0,
    )

    assert store.append_event("inspection_result", result)
    assert not store.append_event("inspection_result", result)
    assert store.append_event("watchdog_alert", alert)
    assert store.latest_inspection() == result
    assert store.inspection_history(None, 50, 0) == ([result], 1)


def test_latest_empty_and_history_filters_pagination_and_timestamp_ties(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    assert store.latest_inspection() is None
    assert store.inspection_history(None, 50, 0) == ([], 0)

    timestamp = datetime(2026, 10, 16, tzinfo=timezone.utc)
    first = inspection(timestamp)
    second = inspection(timestamp, InspectionDecision.FAIL)
    later = inspection(timestamp + timedelta(seconds=1), InspectionDecision.RECHECK)
    for result in (first, second, later):
        store.append_event("inspection_result", result)

    page, total = store.inspection_history(None, 2, 0)
    assert [item.inspection_id for item in page] == [later.inspection_id, second.inspection_id]
    assert total == 3
    failures, total_failures = store.inspection_history(InspectionDecision.FAIL, 50, 0)
    assert [item.inspection_id for item in failures] == [second.inspection_id]
    assert total_failures == 1
