"""Command-line preflight for a profile-compatible exported ONNX artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from software.ml.export.onnx_contract import ExportValidationError, validate_onnx_artifact
from software.ml.model_manifest import ModelManifest
from software.profiles.registry import ProfileRegistry


def _profile_reference(value: str) -> tuple[str, str]:
    profile_id, separator, version = value.partition("@")
    if not separator or not profile_id or not version or "@" in version:
        raise ValueError("--profile must use profile-id@version syntax")
    return profile_id, version


def build_parser() -> argparse.ArgumentParser:
    """Build the ONNX export validation parser."""
    parser = argparse.ArgumentParser(description="Validate an ONNX artifact against a component profile")
    parser.add_argument("--profile-catalog", required=True, type=Path)
    parser.add_argument("--profile", required=True, help="component profile as profile-id@version")
    parser.add_argument("--model-manifest", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate the selected artifact and write a JSON-only static report."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        profile_id, version = _profile_reference(args.profile)
        registry = ProfileRegistry(args.profile_catalog, default_id=profile_id, default_version=version)
        profile = registry.get(profile_id, version)
        manifest = ModelManifest.model_validate_json(args.model_manifest.read_text(encoding="utf-8"))
        report = validate_onnx_artifact(profile, manifest, args.model_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, LookupError, json.JSONDecodeError, ExportValidationError) as exc:
        parser.error(str(exc))
    print(f"Validated static ONNX contract: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
