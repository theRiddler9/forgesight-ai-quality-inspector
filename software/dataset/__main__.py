"""Read-only validation/reporting; split writes only to an explicit output path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from software.dataset.audit import audit_dataset, split_manifest, validate_images
from software.dataset.manifest import DatasetManifest


def main() -> int:
    parser = argparse.ArgumentParser(description="ForgeSight dataset manifest tools")
    parser.add_argument("action", choices=["validate", "report", "split"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, help="dataset root; defaults to manifest directory")
    parser.add_argument("--group-by", choices=["physical_part_id", "capture_session", "batch_id", "source"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, help="new output manifest for split")
    args = parser.parse_args()
    manifest = DatasetManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    root = args.root or args.manifest.parent
    if args.action == "validate":
        errors = validate_images(manifest, root)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        return 1 if errors else 0
    if args.action == "report":
        print(json.dumps(audit_dataset(manifest, args.group_by), indent=2))
        return 0
    if not args.group_by or not args.output:
        parser.error("split requires --group-by and --output")
    output = args.output.resolve()
    if output.exists() or output == args.manifest.resolve():
        parser.error("split output must be a new file; existing manifests are never overwritten")
    split = split_manifest(manifest, args.group_by, args.seed)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(split.model_dump_json(indent=2) + "\n")
    print(json.dumps(audit_dataset(split, args.group_by), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
