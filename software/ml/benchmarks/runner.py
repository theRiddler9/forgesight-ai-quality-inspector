"""Framework-neutral repeated-call timing for inference adapters."""

from __future__ import annotations

import json
import hashlib
import math
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from software.ml.benchmarks.environment import collect_static_environment, read_soc_temperature_c


def benchmark_inference(
    infer: Callable[[Any], Any],
    frames: Sequence[Any],
    *,
    warmup_runs: int,
    repetitions: int,
    model_id: str,
    target_label: str,
    artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    """Measure repeated inference calls and return raw samples with run metadata.

    Frames are consumed in order and reused cyclically if repetitions exceed their
    count. Warmup calls are excluded from the measured samples. Exceptions raised
    by ``infer`` propagate and do not produce a report.
    """
    if len(frames) == 0:
        raise ValueError("frames must contain at least one input")
    if type(warmup_runs) is not int or warmup_runs < 0:
        raise ValueError("warmup_runs must be a non-negative integer")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id must not be empty")
    if not isinstance(target_label, str) or not target_label.strip():
        raise ValueError("target_label must not be empty")

    artifact = _artifact_identity(artifact_path) if artifact_path is not None else None
    environment = collect_static_environment()
    environment["soc_temp_c_before"] = read_soc_temperature_c()

    frame_count = len(frames)
    for index in range(warmup_runs):
        infer(frames[index % frame_count])

    samples_ms: list[float] = []
    for index in range(repetitions):
        frame = frames[index % frame_count]
        started_ns = time.perf_counter_ns()
        infer(frame)
        elapsed_ns = time.perf_counter_ns() - started_ns
        samples_ms.append(elapsed_ns / 1_000_000)

    if artifact_path is not None and _artifact_identity(artifact_path) != artifact:
        raise RuntimeError("model artifact changed during benchmark")
    environment["soc_temp_c_after"] = read_soc_temperature_c()

    ordered = sorted(samples_ms)
    p95_index = math.ceil(0.95 * len(ordered)) - 1
    return {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "artifact": artifact,
        "target_label": target_label,
        "target_label_is_metadata_only": True,
        "warmup_runs": warmup_runs,
        "repetitions": repetitions,
        "frame_count": frame_count,
        "latency_ms": {
            "samples": samples_ms,
            "mean": sum(samples_ms) / len(samples_ms),
            "median": _median(ordered),
            "p95_nearest_rank": ordered[p95_index],
            "min": ordered[0],
            "max": ordered[-1],
        },
        "environment": environment,
    }


def _median(ordered: Sequence[float]) -> float:
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _artifact_identity(artifact_path: str | Path) -> dict[str, Any]:
    """Return stable file identity fields without exposing its absolute path."""
    path = Path(artifact_path)
    if not path.is_file():
        raise ValueError("artifact_path must point to an existing file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"filename": path.name, "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def write_report(report: dict[str, Any], output_path: str | Path) -> None:
    """Write a benchmark report as formatted UTF-8 JSON, creating parent dirs."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
