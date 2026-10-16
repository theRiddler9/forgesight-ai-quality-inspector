"""SQLite persistence for shared inspection and watchdog event models."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypeAlias

from software.common.schemas import (
    InspectionDecision,
    InspectionResult,
    WatchdogAlert,
)

AuditEvent: TypeAlias = InspectionResult | WatchdogAlert
_RAW_ERROR_SAMPLE_LIMIT = 4096
_ERROR_REASON_LIMIT = 1000


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


class AuditStore:
    """Append-only SQLite storage; each operation owns its connection."""

    def __init__(self, db_path: str | Path, busy_timeout_ms: int = 5000):
        self.db_path = Path(db_path)
        self.busy_timeout_ms = max(0, int(busy_timeout_ms))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.db_path), timeout=self.busy_timeout_ms / 1000.0
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_key TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN ('inspection_result', 'watchdog_alert')
                    ),
                    event_timestamp TEXT NOT NULL,
                    inspection_id TEXT,
                    result TEXT,
                    defect_type TEXT,
                    confidence REAL,
                    soc_temp_c REAL,
                    total_latency_ms REAL,
                    envelope_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
                    ON audit_events(event_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_events_result
                    ON audit_events(result, event_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_events_type_timestamp
                    ON audit_events(event_type, event_timestamp DESC);
                CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only');
                END;
                CREATE TABLE IF NOT EXISTS ingestion_errors (
                    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    byte_offset INTEGER NOT NULL CHECK (byte_offset >= 0),
                    raw_sample BLOB NOT NULL,
                    reason TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _model_envelope(event: str, data: AuditEvent) -> dict[str, object]:
        if isinstance(data, InspectionResult):
            expected_event = "inspection_result"
        elif isinstance(data, WatchdogAlert):
            expected_event = "watchdog_alert"
        else:
            raise TypeError(f"unsupported audit event model: {type(data).__name__}")
        if event != expected_event:
            raise ValueError(f"{type(data).__name__} requires event '{expected_event}'")
        return {"event": event, "data": data.model_dump(mode="json")}

    def append_event(self, event: str, data: AuditEvent) -> bool:
        envelope = self._model_envelope(event, data)
        canonical = json.dumps(
            envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        event_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if isinstance(data, InspectionResult):
            event_timestamp = data.timestamp
            fields = (
                str(data.inspection_id),
                data.result.value,
                data.defect_type.value,
                data.confidence,
                data.soc_temp_c,
                data.per_stage_latency_ms.total_ms,
            )
        else:
            event_timestamp = data.timestamp
            fields = (None, None, None, None, None, None)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO audit_events (
                    event_key, event_type, event_timestamp, inspection_id, result,
                    defect_type, confidence, soc_temp_c, total_latency_ms, envelope_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_key,
                    event,
                    _utc_iso(event_timestamp),
                    *fields,
                    canonical,
                ),
            )
            return cursor.rowcount == 1

    def record_ingestion_error(
        self, byte_offset: int, raw_line: bytes, reason: str
    ) -> None:
        """Store a bounded evidence sample for a rejected event line."""
        if byte_offset < 0:
            raise ValueError("byte_offset must be non-negative")
        sample = bytes(raw_line[:_RAW_ERROR_SAMPLE_LIMIT])
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ingestion_errors (byte_offset, raw_sample, reason) VALUES (?, ?, ?)",
                (byte_offset, sample, reason[:_ERROR_REASON_LIMIT]),
            )

    def latest_inspection(self) -> InspectionResult | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT envelope_json FROM audit_events
                   WHERE event_type = 'inspection_result'
                   ORDER BY event_timestamp DESC, rowid DESC LIMIT 1"""
            ).fetchone()
        if row is None:
            return None
        return InspectionResult.model_validate(json.loads(row["envelope_json"])["data"])

    def inspection_history(
        self,
        result: InspectionDecision | None,
        limit: int,
        offset: int,
    ) -> tuple[list[InspectionResult], int]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        where = "event_type = 'inspection_result'"
        parameters: list[object] = []
        if result is not None:
            where += " AND result = ?"
            parameters.append(result.value)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM audit_events WHERE {where}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT envelope_json FROM audit_events WHERE {where}
                    ORDER BY event_timestamp DESC, rowid DESC LIMIT ? OFFSET ?""",
                [*parameters, limit, offset],
            ).fetchall()
        items = [
            InspectionResult.model_validate(json.loads(row["envelope_json"])["data"])
            for row in rows
        ]
        return items, total

    def status_snapshot(self, now: datetime) -> dict[str, object]:
        current = _utc_iso(now)
        since = _utc_iso(now - timedelta(seconds=5))
        with self._connect() as connection:
            latest = connection.execute(
                """SELECT event_timestamp, soc_temp_c FROM audit_events
                   WHERE event_type = 'inspection_result'
                   ORDER BY event_timestamp DESC, rowid DESC LIMIT 1"""
            ).fetchone()
            recent = connection.execute(
                """SELECT COUNT(*) FROM audit_events
                   WHERE event_type = 'inspection_result'
                     AND event_timestamp >= ? AND event_timestamp <= ?""",
                (since, current),
            ).fetchone()[0]
            latency_rows = connection.execute(
                """SELECT total_latency_ms FROM audit_events
                   WHERE event_type = 'inspection_result'
                   ORDER BY event_timestamp DESC, rowid DESC LIMIT 100"""
            ).fetchall()
        latencies = [row["total_latency_ms"] for row in latency_rows]
        return {
            "soc_temp_c": None if latest is None else latest["soc_temp_c"],
            "soc_temp_timestamp": None if latest is None else latest["event_timestamp"],
            "fps": recent / 5.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else None,
        }
