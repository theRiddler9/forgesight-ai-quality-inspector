"""SQLite persistence for shared inspection and watchdog event models."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, TypeAlias
from uuid import uuid4

from software.common.schemas import (
    InspectionDecision,
    InspectionResult,
    WatchdogAlert,
)
from software.inspection.events import validate_event

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

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
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
                CREATE TABLE IF NOT EXISTS canonical_inspections (
                    event_id TEXT PRIMARY KEY,
                    event_timestamp TEXT NOT NULL,
                    result TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL', 'RECHECK')),
                    event_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_canonical_inspections_timestamp
                    ON canonical_inspections(event_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_canonical_inspections_result
                    ON canonical_inspections(result, event_timestamp DESC);
                CREATE TRIGGER IF NOT EXISTS canonical_inspections_no_update
                BEFORE UPDATE ON canonical_inspections
                BEGIN SELECT RAISE(ABORT, 'canonical_inspections is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS canonical_inspections_no_delete
                BEFORE DELETE ON canonical_inspections
                BEGIN SELECT RAISE(ABORT, 'canonical_inspections is append-only'); END;
                CREATE TABLE IF NOT EXISTS inspection_reviews (
                    review_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES canonical_inspections(event_id),
                    reviewed_at TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    corrected_result TEXT NOT NULL CHECK (corrected_result IN ('PASS', 'FAIL', 'RECHECK')),
                    note TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_inspection_reviews_event
                    ON inspection_reviews(event_id, reviewed_at);
                CREATE TRIGGER IF NOT EXISTS inspection_reviews_no_update
                BEFORE UPDATE ON inspection_reviews
                BEGIN SELECT RAISE(ABORT, 'inspection_reviews is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS inspection_reviews_no_delete
                BEFORE DELETE ON inspection_reviews
                BEGIN SELECT RAISE(ABORT, 'inspection_reviews is append-only'); END;
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

        with self._connection() as connection:
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

    def append_inspection_pair(self, result: InspectionResult, event: dict) -> bool:
        """Commit canonical evidence and the legacy read projection atomically."""
        validate_event(event)
        if event["event_id"] != str(result.inspection_id) or event["result"] != result.result.value:
            raise ValueError("canonical event and inspection result disagree")
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        envelope = self._model_envelope("inspection_result", result)
        projection = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        event_key = hashlib.sha256(projection.encode("utf-8")).hexdigest()
        with self._connection() as connection:
            inserted = connection.execute(
                """INSERT OR IGNORE INTO canonical_inspections
                   (event_id, event_timestamp, result, event_json) VALUES (?, ?, ?, ?)""",
                (event["event_id"], _utc_iso(result.timestamp), result.result.value, canonical),
            ).rowcount
            if not inserted:
                return False
            connection.execute(
                """INSERT INTO audit_events
                   (event_key, event_type, event_timestamp, inspection_id, result,
                    defect_type, confidence, soc_temp_c, total_latency_ms, envelope_json)
                   VALUES (?, 'inspection_result', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_key, _utc_iso(result.timestamp), str(result.inspection_id),
                    result.result.value, result.defect_type.value, result.confidence,
                    result.soc_temp_c, result.per_stage_latency_ms.total_ms, projection,
                ),
            )
        return True

    def canonical_inspection(self, event_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT event_json FROM canonical_inspections WHERE event_id = ?", (event_id,)
            ).fetchone()
        return json.loads(row["event_json"]) if row else None

    def canonical_history(self, result: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("invalid pagination")
        where = "" if result is None else "WHERE result = ?"
        params: tuple = () if result is None else (result,)
        with self._connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM canonical_inspections {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT event_json FROM canonical_inspections {where}
                    ORDER BY event_timestamp DESC, rowid DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
        return [json.loads(row["event_json"]) for row in rows], total

    def canonical_metrics(self) -> dict[str, int | float | None]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT result, COUNT(*) AS amount FROM canonical_inspections GROUP BY result"
            ).fetchall()
            latency = connection.execute(
                """SELECT AVG(total_latency_ms) FROM audit_events
                   WHERE event_type = 'inspection_result' AND inspection_id IN
                   (SELECT event_id FROM canonical_inspections)"""
            ).fetchone()[0]
        counts: dict[str, int | float | None] = {"PASS": 0, "FAIL": 0, "RECHECK": 0}
        for row in rows:
            counts[row["result"]] = row["amount"]
        counts["total"] = sum(int(counts[key]) for key in ("PASS", "FAIL", "RECHECK"))
        counts["average_latency_ms"] = latency
        return counts

    def append_review(self, event_id: str, reviewer_id: str, corrected_result: str, note: str) -> dict:
        if corrected_result not in {"PASS", "FAIL", "RECHECK"}:
            raise ValueError("invalid corrected result")
        review = {
            "review_id": str(uuid4()), "event_id": event_id,
            "reviewed_at": _utc_iso(datetime.now(timezone.utc)),
            "reviewer_id": reviewer_id, "corrected_result": corrected_result, "note": note,
        }
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM canonical_inspections WHERE event_id = ?", (event_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(event_id)
            connection.execute(
                """INSERT INTO inspection_reviews
                   (review_id, event_id, reviewed_at, reviewer_id, corrected_result, note)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                tuple(review.values()),
            )
        return review

    def review_history(self, event_id: str) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT review_id, event_id, reviewed_at, reviewer_id, corrected_result, note
                   FROM inspection_reviews WHERE event_id = ? ORDER BY reviewed_at, rowid""",
                (event_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_ingestion_error(
        self, byte_offset: int, raw_line: bytes, reason: str
    ) -> None:
        """Store a bounded evidence sample for a rejected event line."""
        if byte_offset < 0:
            raise ValueError("byte_offset must be non-negative")
        sample = bytes(raw_line[:_RAW_ERROR_SAMPLE_LIMIT])
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO ingestion_errors (byte_offset, raw_sample, reason) VALUES (?, ?, ?)",
                (byte_offset, sample, reason[:_ERROR_REASON_LIMIT]),
            )

    def latest_inspection(self) -> InspectionResult | None:
        with self._connection() as connection:
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
        with self._connection() as connection:
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
        with self._connection() as connection:
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
