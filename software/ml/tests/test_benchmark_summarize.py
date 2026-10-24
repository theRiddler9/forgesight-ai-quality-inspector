"""Tests for schema-checked, raw-sample benchmark summaries."""

import csv
import json

import pytest
from jsonschema import Draft202012Validator

from software.ml.benchmarks import summarize


def report(samples, *, repetitions=None):
    """Build a schema-shaped report with intentionally stale cached statistics."""
    return {
        "schema_version": "1.0.0",
        "created_at": "2026-10-20T12:00:00+00:00",
        "model_id": "local-model",
        "artifact": {"filename": "model.onnx", "size_bytes": 4, "sha256": "a" * 64},
        "target_label": "not-verified-board",
        "target_label_is_metadata_only": True,
        "warmup_runs": 1,
        "repetitions": len(samples) if repetitions is None else repetitions,
        "frame_count": 2,
        "latency_ms": {
            "samples": samples, "mean": 999.0, "median": 999.0,
            "p95_nearest_rank": 999.0, "min": 999.0, "max": 999.0,
        },
        "environment": {
            "python_version": "3.13.0", "platform": "test", "machine": "test-machine",
            "processor": None, "hardware_model": None,
            "runtime_packages": {"onnxruntime": "1.20.0"},
            "soc_temp_c_before": None, "soc_temp_c_after": None,
        },
    }


def write_report(path, data):
    """Persist one synthetic report for summary validation tests."""
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_summary_recomputes_statistics_from_raw_samples(tmp_path):
    """CSV statistics must come from raw samples, not cached report fields."""
    source = write_report(tmp_path / "run.json", report([1.0, 2.0, 3.0, 4.0]))
    row = summarize.summarize_report(source)
    assert row["mean_ms"] == 2.5
    assert row["median_ms"] == 2.5
    assert row["p95_nearest_rank_ms"] == 4.0
    assert row["min_ms"] == 1.0 and row["max_ms"] == 4.0
    assert row["artifact_sha256"] == "a" * 64


def test_summary_recomputes_p99_from_raw_samples(tmp_path):
    """Nearest-rank p99 is derived from validated samples."""
    source = write_report(tmp_path / "run.json", report(list(range(1, 101))))
    row = summarize.summarize_report(source)
    assert row["p95_nearest_rank_ms"] == 95.0
    assert row["p99_nearest_rank_ms"] == 99.0


def test_summary_preserves_profile_context_for_onnx_reports(tmp_path):
    """Model and provider identity survive the JSON-to-CSV projection."""
    data = report([1.0])
    data["onnx_context"] = {
        "backend": "onnx", "profile_id": "metal-plate-v1", "profile_version": "9.1.0",
        "profile_fingerprint": "b" * 64, "model_version": "1.2.3",
        "model_purpose": "trained_unverified", "preprocessing_fingerprint": "c" * 64,
        "execution_providers": ["CPUExecutionProvider"],
        "model_initialization_ms": 2.5,
        "timing_scope": "detector_call_including_preprocess_postprocess",
    }
    row = summarize.summarize_report(write_report(tmp_path / "onnx.json", data))
    assert row["backend"] == "onnx"
    assert row["profile_id"] == "metal-plate-v1"
    assert row["profile_version"] == "9.1.0"
    assert row["model_purpose"] == "trained_unverified"
    assert row["execution_providers"] == "CPUExecutionProvider"
    assert row["model_initialization_ms"] == 2.5
    assert row["timing_scope"] == "detector_call_including_preprocess_postprocess"


def test_summary_leaves_legacy_missing_timing_scope_blank(tmp_path):
    """Legacy reports without a scope must not acquire invented metadata."""
    data = report([1.0])
    data["onnx_context"] = {
        "backend": "onnx", "profile_id": "metal-plate-v1", "profile_version": "9.1.0",
        "profile_fingerprint": "b" * 64, "model_version": "1.2.3",
        "model_purpose": "trained_unverified", "preprocessing_fingerprint": "c" * 64,
    }
    source = write_report(tmp_path / "legacy-onnx.json", data)
    assert summarize.summarize_report(source)["timing_scope"] is None
    output = tmp_path / "summary.csv"
    assert summarize.main([str(source), "--output", str(output)]) == 0
    with output.open(encoding="utf-8", newline="") as stream:
        assert list(csv.DictReader(stream))[0]["timing_scope"] == ""


def test_summary_rejects_schema_invalid_report(tmp_path):
    """Unexpected report fields fail versioned schema validation."""
    data = report([1.0])
    data["extra"] = "not permitted"
    source = write_report(tmp_path / "invalid.json", data)
    with pytest.raises(ValueError, match="schema"):
        summarize.summarize_report(source)


@pytest.mark.parametrize("created_at", [
    "not-a-timestamp", "2026-10-20T12:00:00", "2026-02-30T12:00:00Z",
    "2026-10-20T25:00:00Z", "2026-10-20T12:00:00+99:00",
])
@pytest.mark.parametrize("schema_format_check", [True, False])
def test_summary_rejects_invalid_rfc3339_timestamp_without_optional_format_package(
    tmp_path, monkeypatch, created_at, schema_format_check,
):
    """Invalid timestamps fail with or without schema's optional format check."""
    if not schema_format_check:
        schema = json.loads(summarize._SCHEMA_PATH.read_text(encoding="utf-8"))
        monkeypatch.setattr(
            summarize, "_validate_report",
            lambda value: Draft202012Validator(schema).validate(value),
        )
    data = report([1.0])
    data["created_at"] = created_at
    with pytest.raises(ValueError):
        summarize.summarize_report(write_report(tmp_path / "invalid-time.json", data))


@pytest.mark.parametrize("created_at", ["2026-10-20T12:00:00Z", "2026-10-20T12:00:00.123+05:30"])
def test_summary_accepts_rfc3339_timestamp(tmp_path, created_at):
    """UTC and offset RFC 3339 timestamps retain their source text."""
    data = report([1.0])
    data["created_at"] = created_at
    assert summarize.summarize_report(write_report(tmp_path / "valid-time.json", data))["created_at"] == created_at


@pytest.mark.parametrize(
    ("samples", "repetitions"),
    [([], 1), ([1.0], 2), ([float("nan")], 1), ([-1.0], 1)],
)
def test_summary_rejects_invalid_sample_vectors(tmp_path, samples, repetitions):
    """Empty, non-finite, negative, and count-mismatched samples are rejected."""
    source = write_report(tmp_path / "invalid.json", report(samples, repetitions=repetitions))
    with pytest.raises(ValueError):
        summarize.summarize_report(source)


def test_summary_cli_expands_report_patterns_and_writes_csv(tmp_path):
    """Literal wildcard arguments expand in stable filename order on Windows."""
    write_report(tmp_path / "run-2.json", report([2.0]))
    write_report(tmp_path / "run-1.json", report([1.0]))
    output = tmp_path / "summary.csv"
    status = summarize.main([str(tmp_path / "run-*.json"), "--output", str(output)])

    assert status == 0
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["report"] for row in rows] == ["run-1.json", "run-2.json"]
    assert [row["mean_ms"] for row in rows] == ["1.0", "2.0"]


def test_summary_cli_rejects_pattern_without_matches(tmp_path):
    """An unmatched report glob cannot create an empty comparison table."""
    with pytest.raises(SystemExit):
        summarize.main([str(tmp_path / "missing-*.json"), "--output", str(tmp_path / "summary.csv")])
