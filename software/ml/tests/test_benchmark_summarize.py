"""Tests for schema-checked, raw-sample benchmark summaries."""

import csv
import json

import pytest

from software.ml.benchmarks import summarize


def report(samples, *, repetitions=None):
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
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_summary_recomputes_statistics_from_raw_samples(tmp_path):
    source = write_report(tmp_path / "run.json", report([1.0, 2.0, 3.0, 4.0]))
    row = summarize.summarize_report(source)
    assert row["mean_ms"] == 2.5
    assert row["median_ms"] == 2.5
    assert row["p95_nearest_rank_ms"] == 4.0
    assert row["min_ms"] == 1.0 and row["max_ms"] == 4.0
    assert row["artifact_sha256"] == "a" * 64


def test_summary_rejects_schema_invalid_report(tmp_path):
    data = report([1.0])
    data["extra"] = "not permitted"
    source = write_report(tmp_path / "invalid.json", data)
    with pytest.raises(ValueError, match="schema"):
        summarize.summarize_report(source)


@pytest.mark.parametrize(
    ("samples", "repetitions"),
    [([], 1), ([1.0], 2), ([float("nan")], 1), ([-1.0], 1)],
)
def test_summary_rejects_invalid_sample_vectors(tmp_path, samples, repetitions):
    source = write_report(tmp_path / "invalid.json", report(samples, repetitions=repetitions))
    with pytest.raises(ValueError):
        summarize.summarize_report(source)


def test_summary_cli_expands_report_patterns_and_writes_csv(tmp_path):
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
    with pytest.raises(SystemExit):
        summarize.main([str(tmp_path / "missing-*.json"), "--output", str(tmp_path / "summary.csv")])
