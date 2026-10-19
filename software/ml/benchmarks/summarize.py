"""Validate benchmark samples and export concise run comparisons as CSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any


def summarize_report(path: str | Path) -> dict[str, Any]:
    """Load one report and recompute latency statistics from its raw samples."""
    source = Path(path)
    report = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError(f"report must be a JSON object: {source}")
    if report.get("schema_version") != "1.0.0":
        raise ValueError(f"unsupported report schema in {source}")
    latency = report.get("latency_ms")
    if not isinstance(latency, dict):
        raise ValueError(f"latency_ms must be an object in {source}")
    samples = latency.get("samples")
    repetitions = report.get("repetitions")
    if not isinstance(samples, list) or not samples or len(samples) != repetitions:
        raise ValueError(f"sample count does not match repetitions in {source}")
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError(f"invalid latency sample in {source}")
    ordered = sorted(float(value) for value in samples)
    env = report.get("environment", {})
    if not isinstance(env, dict):
        raise ValueError(f"environment must be an object in {source}")
    artifact = report.get("artifact") or {}
    return {
        "report": source.name,
        "created_at": report.get("created_at"),
        "model_id": report.get("model_id"),
        "artifact_sha256": artifact.get("sha256"),
        "target_label": report.get("target_label"),
        "hardware_model": env.get("hardware_model"),
        "machine": env.get("machine"),
        "warmup_runs": report.get("warmup_runs"),
        "repetitions": repetitions,
        "mean_ms": statistics.fmean(ordered),
        "median_ms": statistics.median(ordered),
        "p95_nearest_rank_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "soc_temp_c_before": env.get("soc_temp_c_before"),
        "soc_temp_c_after": env.get("soc_temp_c_after"),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the report summarizer argument parser."""
    parser = argparse.ArgumentParser(description="Summarize inference benchmark JSON reports")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path, help="destination CSV path")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate reports and write one CSV row per benchmark run."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rows = [summarize_report(path) for path in args.reports]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote {len(rows)} benchmark summaries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
