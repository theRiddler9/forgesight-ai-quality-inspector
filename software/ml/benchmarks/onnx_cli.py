"""Benchmark the repository's profile-validated CPU ONNX detector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from software.inspection.onnx_detector import OnnxDetector
from software.ml.benchmarks.runner import benchmark_inference, write_report
from software.ml.model_manifest import ModelManifest
from software.profiles.registry import ProfileRegistry


def _profile_reference(value: str) -> tuple[str, str]:
    profile_id, separator, version = value.partition("@")
    if not separator or not profile_id or not version or "@" in version:
        raise ValueError("--profile must use profile-id@version syntax")
    return profile_id, version


def build_parser() -> argparse.ArgumentParser:
    """Build the profile-aware ONNX benchmark parser."""
    parser = argparse.ArgumentParser(description="Benchmark the local profile-validated ONNX detector")
    parser.add_argument("--profile-catalog", required=True, type=Path)
    parser.add_argument("--profile", required=True, help="component profile as profile-id@version")
    parser.add_argument("--model-manifest", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=Path, help="NumPy BGR8 image or frame batch")
    parser.add_argument("--input-layout", required=True, choices=("bgr", "bgr-batch"))
    parser.add_argument("--target-label", required=True, help="metadata label; does not verify target hardware")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ONNX inference over saved BGR8 frames and write a standard report."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.frames.is_file() or args.frames.suffix.lower() != ".npy":
        parser.error("--frames must point to an existing .npy file")
    if not args.model_manifest.is_file():
        parser.error("--model-manifest must point to an existing file")
    try:
        profile_id, version = _profile_reference(args.profile)
        registry = ProfileRegistry(args.profile_catalog, default_id=profile_id, default_version=version)
        profile = registry.get(profile_id, version)
        manifest = ModelManifest.model_validate_json(args.model_manifest.read_text(encoding="utf-8"))
        frames = np.load(args.frames, mmap_mode="r", allow_pickle=False)
        expected_dimensions = 3 if args.input_layout == "bgr" else 4
        if frames.ndim != expected_dimensions:
            raise ValueError(f"{args.input_layout} input must have {expected_dimensions} dimensions")
        if args.input_layout == "bgr-batch" and frames.shape[0] == 0:
            raise ValueError("frame batch must contain at least one image")
        if frames.dtype != np.uint8:
            raise ValueError("frame data must use uint8 pixel values")
        if frames.shape[-1] != 3:
            raise ValueError("BGR input must have three channels on its final axis")
        if tuple(frames.shape[-3:-1]) != (profile.image.height, profile.image.width):
            raise ValueError("frame dimensions do not match the selected component profile")
        frame_sequence = [frames] if args.input_layout == "bgr" else frames
        detector = OnnxDetector(profile, manifest, args.model_root)
        artifact_path = (args.model_root.resolve() / manifest.artifact_path).resolve()
        report = benchmark_inference(
            detector.detect,
            frame_sequence,
            warmup_runs=args.warmup,
            repetitions=args.repetitions,
            model_id=manifest.model_id,
            target_label=args.target_label,
            artifact_path=artifact_path,
        )
        report["onnx_context"] = {
            "backend": manifest.backend,
            "profile_id": profile.profile_id,
            "profile_version": profile.version,
            "profile_fingerprint": profile.fingerprint,
            "model_version": manifest.model_version,
            "model_purpose": manifest.model_purpose,
            "preprocessing_fingerprint": manifest.preprocessing_fingerprint,
        }
        write_report(report, args.output)
    except (OSError, ValueError, RuntimeError, LookupError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Wrote {args.repetitions} ONNX inference samples to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
