"""Regression tests for repeated inference timing and report output."""

import json

import pytest

from software.ml.benchmarks import runner


def test_benchmark_excludes_warmup_and_cycles_frames(monkeypatch):
    """Warmups stay outside samples while measured calls cycle input frames."""
    calls = []
    ticks = iter([0, 1_000_000, 10_000_000, 12_000_000, 20_000_000, 23_000_000])
    monkeypatch.setattr(runner.time, "perf_counter_ns", lambda: next(ticks))
    monkeypatch.setattr(runner, "collect_static_environment", lambda: {})
    monkeypatch.setattr(runner, "read_soc_temperature_c", lambda: None)

    report = runner.benchmark_inference(
        calls.append, ["a", "b"], warmup_runs=2, repetitions=3,
        model_id="model", target_label="host-label",
    )

    assert calls == ["a", "b", "a", "b", "a"]
    assert report["latency_ms"]["samples"] == [1.0, 2.0, 3.0]
    assert report["latency_ms"]["mean"] == 2.0
    assert report["latency_ms"]["median"] == 2.0
    assert report["latency_ms"]["p95_nearest_rank"] == 3.0
    assert report["target_label_is_metadata_only"] is True
    assert report["environment"]["soc_temp_c_before"] is None


def test_benchmark_reports_nearest_rank_p99_from_measured_samples(monkeypatch):
    """Nearest-rank p95 and p99 use the measured sample vector."""
    ticks = iter(value for milliseconds in range(1, 101)
                 for value in (0, milliseconds * 1_000_000))
    monkeypatch.setattr(runner.time, "perf_counter_ns", lambda: next(ticks))
    monkeypatch.setattr(runner, "collect_static_environment", lambda: {})
    monkeypatch.setattr(runner, "read_soc_temperature_c", lambda: None)
    report = runner.benchmark_inference(
        lambda _frame: None, [1], warmup_runs=0, repetitions=100,
        model_id="model", target_label="host",
    )
    assert report["latency_ms"]["p95_nearest_rank"] == 95.0
    assert report["latency_ms"]["p99_nearest_rank"] == 99.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"frames": []}, "frames"),
        ({"warmup_runs": -1}, "warmup_runs"),
        ({"warmup_runs": True}, "warmup_runs"),
        ({"repetitions": 0}, "repetitions"),
        ({"model_id": " "}, "model_id"),
        ({"target_label": ""}, "target_label"),
    ],
)
def test_benchmark_rejects_invalid_inputs_before_inference(overrides, message):
    """Invalid run configuration fails before any adapter call."""
    calls = []
    args = dict(frames=[1], warmup_runs=0, repetitions=1, model_id="id", target_label="host")
    args.update(overrides)
    with pytest.raises(ValueError, match=message):
        runner.benchmark_inference(calls.append, **args)
    assert calls == []


def test_benchmark_propagates_inference_errors(monkeypatch):
    """A failed adapter call aborts the run rather than producing statistics."""
    monkeypatch.setattr(runner, "collect_static_environment", lambda: {})
    monkeypatch.setattr(runner, "read_soc_temperature_c", lambda: None)

    def fail(_frame):
        """Raise a controlled adapter error during measurement."""
        raise RuntimeError("adapter failed")

    with pytest.raises(RuntimeError, match="adapter failed"):
        runner.benchmark_inference(
            fail, [1], warmup_runs=0, repetitions=1,
            model_id="model", target_label="host",
        )


def test_artifact_change_aborts_report(monkeypatch, tmp_path):
    """A model whose hash changes during measurement invalidates the run."""
    identities = iter([{"sha256": "first"}, {"sha256": "second"}])
    monkeypatch.setattr(runner, "_artifact_identity", lambda _path: next(identities))
    monkeypatch.setattr(runner, "collect_static_environment", lambda: {})
    monkeypatch.setattr(runner, "read_soc_temperature_c", lambda: None)
    with pytest.raises(RuntimeError, match="artifact changed"):
        runner.benchmark_inference(
            lambda _frame: None, [1], warmup_runs=0, repetitions=1,
            model_id="model", target_label="host", artifact_path=tmp_path / "model.onnx",
        )


def test_report_writer_disallows_non_json_numbers(tmp_path):
    """Non-finite numbers cannot be serialized into benchmark evidence."""
    with pytest.raises(ValueError):
        runner.write_report({"latency": float("nan")}, tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_report_writer_creates_parent_and_writes_json(tmp_path):
    """Report output creates its parent directory and remains readable JSON."""
    destination = tmp_path / "nested" / "report.json"
    runner.write_report({"repetitions": 1}, destination)
    assert json.loads(destination.read_text(encoding="utf-8")) == {"repetitions": 1}
