"""Validate benchmark samples and export concise run comparisons as CSV."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).with_name("report.schema.json")
_RFC3339_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", re.IGNORECASE)


def _validate_timestamp(value: str) -> None:
    """Check report time without relying on jsonschema's optional format extras."""
    if not _RFC3339_TIMESTAMP.fullmatch(value):
        raise ValueError("created_at must be an RFC 3339 timestamp with timezone")
    try:
        datetime.fromisoformat(value.replace("z", "Z"))
    except ValueError as exc:
        raise ValueError("created_at must be an RFC 3339 timestamp with timezone") from exc


def _validate_report(report: dict[str, Any]) -> None:
    """Validate one report against the versioned local JSON Schema."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker, ValidationError
    except ImportError as exc:
        raise RuntimeError(
            "report validation requires the development dependencies; "
            "install software/requirements-dev.txt"
        ) from exc
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
    except ValidationError as exc:
        raise ValueError(f"report does not match the benchmark schema: {exc.message}") from exc


def summarize_report(path: str | Path) -> dict[str, Any]:
    """Load one report and recompute latency statistics from its raw samples."""
    source = Path(path)
    report = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError(f"report must be a JSON object: {source}")
    _validate_report(report)
    _validate_timestamp(report["created_at"])
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
    if not isinstance(artifact, dict):
        raise ValueError(f"artifact must be an object or null in {source}")
    onnx_context = report.get("onnx_context") or {}
    if not isinstance(onnx_context, dict):
        raise ValueError(f"onnx_context must be an object in {source}")
    return {
        "report": source.name,
        "created_at": report.get("created_at"),
        "model_id": report.get("model_id"),
        "artifact_sha256": artifact.get("sha256"),
        "target_label": report.get("target_label"),
        "backend": onnx_context.get("backend"),
        "profile_id": onnx_context.get("profile_id"),
        "profile_version": onnx_context.get("profile_version"),
        "profile_fingerprint": onnx_context.get("profile_fingerprint"),
        "model_version": onnx_context.get("model_version"),
        "model_purpose": onnx_context.get("model_purpose"),
        "preprocessing_fingerprint": onnx_context.get("preprocessing_fingerprint"),
        "execution_providers": ";".join(onnx_context.get("execution_providers", [])),
        "model_initialization_ms": onnx_context.get("model_initialization_ms"),
        "timing_scope": onnx_context.get("timing_scope", "adapter_call"),
        "hardware_model": env.get("hardware_model"),
        "machine": env.get("machine"),
        "warmup_runs": report.get("warmup_runs"),
        "repetitions": repetitions,
        "mean_ms": statistics.fmean(ordered),
        "median_ms": statistics.median(ordered),
        "p95_nearest_rank_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "p99_nearest_rank_ms": ordered[math.ceil(0.99 * len(ordered)) - 1],
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
        report_paths: list[Path] = []
        for path in args.reports:
            matches = sorted(glob.glob(str(path)))
            if matches:
                report_paths.extend(Path(match) for match in matches)
            elif glob.has_magic(str(path)):
                parser.error(f"report pattern matched no files: {path}")
            else:
                report_paths.append(path)
        rows = [summarize_report(path) for path in report_paths]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"Wrote {len(rows)} benchmark summaries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
