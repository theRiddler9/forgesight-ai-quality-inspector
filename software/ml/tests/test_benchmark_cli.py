"""Tests for explicit NumPy frame layouts and local adapter loading."""

import sys
import types

import numpy as np
import pytest

from software.ml.benchmarks import cli


@pytest.mark.parametrize(
    ("layout", "shape", "expected_count"),
    [
        ("gray", (12, 16), 1),
        ("gray-batch", (2, 12, 16), 2),
        ("bgr", (12, 16, 3), 1),
        ("bgr-batch", (2, 12, 16, 3), 2),
    ],
)
def test_cli_passes_explicit_frame_sequence_to_runner(monkeypatch, tmp_path, layout, shape, expected_count):
    frames_path = tmp_path / "frames.npy"
    np.save(frames_path, np.zeros(shape, dtype=np.uint8))
    captured = {}
    monkeypatch.setattr(cli, "_load_adapter", lambda _spec: lambda _frame: None)

    def benchmark(infer, frames, **kwargs):
        captured.update(frames=list(frames), kwargs=kwargs)
        return {"latency_ms": {"samples": [0.1]}}

    monkeypatch.setattr(cli, "benchmark_inference", benchmark)
    monkeypatch.setattr(cli, "write_report", lambda report, path: captured.update(report=report, output=path))

    status = cli.main([
        "--adapter", "local:factory", "--frames", str(frames_path),
        "--input-layout", layout, "--model-id", "test-model", "--target-label", "dev-host",
        "--output", str(tmp_path / "report.json"), "--warmup", "0", "--repetitions", "1",
    ])

    assert status == 0
    assert len(captured["frames"]) == expected_count
    assert captured["kwargs"]["model_id"] == "test-model"
    assert captured["kwargs"]["target_label"] == "dev-host"


@pytest.mark.parametrize(
    ("layout", "array"),
    [
        ("gray", np.zeros((2, 12, 16), dtype=np.uint8)),
        ("gray-batch", np.zeros((12, 16), dtype=np.uint8)),
        ("bgr", np.zeros((12, 16, 4), dtype=np.uint8)),
        ("bgr-batch", np.zeros((2, 12, 16, 1), dtype=np.uint8)),
    ],
)
def test_cli_rejects_layout_mismatch_before_writing_report(monkeypatch, tmp_path, layout, array):
    frames_path = tmp_path / "frames.npy"
    np.save(frames_path, array)
    monkeypatch.setattr(cli, "_load_adapter", lambda _spec: lambda _frame: None)
    monkeypatch.setattr(cli, "write_report", lambda *_: pytest.fail("unexpected report"))

    with pytest.raises(SystemExit):
        cli.main([
            "--adapter", "local:factory", "--frames", str(frames_path),
            "--input-layout", layout, "--model-id", "model", "--target-label", "host",
            "--output", str(tmp_path / "report.json"),
        ])


def test_cli_rejects_non_numpy_numeric_dtype_before_benchmark(monkeypatch, tmp_path):
    frames_path = tmp_path / "frames.npy"
    np.save(frames_path, np.zeros((4, 5), dtype=np.float32))
    monkeypatch.setattr(cli, "_load_adapter", lambda _spec: lambda _frame: None)
    with pytest.raises(SystemExit):
        cli.main([
            "--adapter", "local:factory", "--frames", str(frames_path),
            "--input-layout", "gray", "--model-id", "model", "--target-label", "host",
            "--output", str(tmp_path / "report.json"),
        ])


def test_adapter_loader_requires_factory_syntax_and_callable(monkeypatch):
    module = types.ModuleType("test_adapter_module")
    module.create = lambda: (lambda _frame: "result")
    module.not_callable = "value"
    monkeypatch.setitem(sys.modules, module.__name__, module)
    assert cli._load_adapter("test_adapter_module:create")(None) == "result"
    with pytest.raises(ValueError, match="module.path"):
        cli._load_adapter("test_adapter_module")
    with pytest.raises(ValueError, match="not callable"):
        cli._load_adapter("test_adapter_module:not_callable")


def test_cli_does_not_write_report_after_inference_error(monkeypatch, tmp_path):
    frames_path = tmp_path / "frames.npy"
    np.save(frames_path, np.zeros((4, 5), dtype=np.uint8))
    monkeypatch.setattr(cli, "_load_adapter", lambda _spec: lambda _frame: None)
    monkeypatch.setattr(cli, "benchmark_inference", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("inference failed")))
    monkeypatch.setattr(cli, "write_report", lambda *_: pytest.fail("unexpected report"))
    with pytest.raises(RuntimeError, match="inference failed"):
        cli.main([
            "--adapter", "local:factory", "--frames", str(frames_path),
            "--input-layout", "gray", "--model-id", "model", "--target-label", "host",
            "--output", str(tmp_path / "report.json"),
        ])
