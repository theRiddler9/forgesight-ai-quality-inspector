import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from software.backend.database import AuditStore
from software.common.schemas import InspectionDecision, InspectionResult, LatencyBreakdown, PokaYokeStatus
from software.inspection.events import build_event
from software.inspection.replay import ScenarioCatalog


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def sample():
    result = InspectionResult(
        result=InspectionDecision.PASS,
        confidence=0.99,
        poka_yoke_status=PokaYokeStatus(),
        per_stage_latency_ms=LatencyBreakdown.from_stages(1, 2, 0, 1),
        soc_temp_c=-1,
    )
    scenario = ScenarioCatalog(FIXTURES).get("clean_part")
    return result, build_event(result, scenario, None, "clean")


def test_pair_is_atomic_idempotent_and_survives_restart(tmp_path):
    path = tmp_path / "audit.sqlite3"
    store = AuditStore(path)
    result, event = sample()
    assert store.append_inspection_pair(result, event)
    assert not store.append_inspection_pair(result, event)
    reopened = AuditStore(path)
    assert reopened.canonical_inspection(str(result.inspection_id)) == event
    assert reopened.canonical_history(None, 10, 0) == ([event], 1)
    assert reopened.latest_inspection() == result


def test_invalid_event_and_projection_failure_leave_no_partial_commit(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    result, event = sample()
    bad = dict(event, result="UNKNOWN")
    with pytest.raises(Exception):
        store.append_inspection_pair(result, bad)
    assert store.canonical_history(None, 10, 0) == ([], 0)

    # Force the second insert to fail after the canonical row was attempted.
    with sqlite3.connect(store.db_path) as connection:
        connection.execute("DROP TABLE audit_events")
    with pytest.raises(sqlite3.Error):
        store.append_inspection_pair(result, event)
    assert store.canonical_history(None, 10, 0) == ([], 0)


def test_reviews_are_append_only_and_original_decision_remains(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    result, event = sample()
    store.append_inspection_pair(result, event)
    first = store.append_review(str(result.inspection_id), "operator-1", "FAIL", "visual correction")
    second = store.append_review(str(result.inspection_id), "operator-2", "PASS", "second review")
    assert first["review_id"] != second["review_id"]
    assert [r["corrected_result"] for r in store.review_history(str(result.inspection_id))] == ["FAIL", "PASS"]
    assert store.canonical_inspection(str(result.inspection_id))["result"] == "PASS"
    assert store.latest_inspection().result == InspectionDecision.PASS
    with pytest.raises(KeyError):
        store.append_review(str(uuid4()), "operator", "FAIL", "missing")


def test_history_filters_and_paginates(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    for decision in (InspectionDecision.PASS, InspectionDecision.FAIL, InspectionDecision.RECHECK):
        result, event = sample()
        result = result.model_copy(update={"result": decision})
        event = dict(event, result=decision.value)
        store.append_inspection_pair(result, event)
    items, total = store.canonical_history("FAIL", 2, 0)
    assert total == 1 and [e["result"] for e in items] == ["FAIL"]
    page, total = store.canonical_history(None, 1, 1)
    assert total == 3 and len(page) == 1
