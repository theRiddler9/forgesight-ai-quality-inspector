"""Command-line entry point for benchmarking a local inference adapter."""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from software.ml.benchmarks.runner import benchmark_inference, write_report


def _load_adapter(specification: str) -> Callable[[Any], Any]:
    """Load a zero-argument local factory and return its inference callable."""
    module_name, separator, attribute_name = specification.partition(":")
    if not separator or not module_name or not attribute_name:
        raise ValueError("adapter must use module.path:factory_name syntax")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute_name, None)
    if not callable(factory):
        raise ValueError(f"adapter factory is not callable: {specification}")
    infer = factory()
    if not callable(infer):
        raise ValueError("adapter factory must return a callable accepting one frame")
    return infer


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark CLI argument parser."""
    parser = argparse.ArgumentParser(description="Benchmark a local inference adapter")
    parser.add_argument("--adapter", required=True, help="local zero-argument factory as module.path:name")
    parser.add_argument("--frames", required=True, type=Path, help=".npy frame or frame batch")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--artifact", type=Path, help="optional model file to hash before and after timing")
    parser.add_argument("--target-label", required=True, help="metadata label, not hardware verification")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load frames and adapter, run measurements, and write the JSON report."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.frames.is_file() or args.frames.suffix.lower() != ".npy":
        parser.error("--frames must point to an existing .npy file")
    try:
        frames = np.load(args.frames, mmap_mode="r", allow_pickle=False)
        if frames.ndim < 3:
            raise ValueError("frame data must have at least three dimensions")
        frame_sequence = [frames] if frames.ndim == 3 else frames
        infer = _load_adapter(args.adapter)
        report = benchmark_inference(
            infer,
            frame_sequence,
            warmup_runs=args.warmup,
            repetitions=args.repetitions,
            model_id=args.model_id,
            target_label=args.target_label,
            artifact_path=args.artifact,
        )
        write_report(report, args.output)
    except (OSError, ValueError, ImportError, AttributeError) as exc:
        parser.error(str(exc))
    print(f"Wrote {args.repetitions} inference samples to {args.output}")
    return 0
