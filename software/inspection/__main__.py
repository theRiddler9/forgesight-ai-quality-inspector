"""Explicit local-image ONNX inspection; no remote paths or model downloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from software.backend.database import AuditStore
from software.inspection.local_image import MAX_IMAGE_BYTES
from software.inspection.service import ReplayService
from software.ml.model_manifest import ModelManifest
from software.profiles.registry import ProfileRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect one local image through a configured ONNX model")
    parser.add_argument("image", type=Path)
    parser.add_argument("--profile-catalog", type=Path, required=True)
    parser.add_argument("--profile", required=True, help="component-id@version")
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("data/audit.sqlite3"))
    args = parser.parse_args()
    if args.image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
        parser.error("PNG, JPEG, or BMP image required")
    if "@" not in args.profile:
        parser.error("profile must be component-id@version")
    try:
        if args.image.stat().st_size > MAX_IMAGE_BYTES:
            parser.error("image exceeds 8 MiB limit")
        raw = args.image.read_bytes()
        identifier, version = args.profile.rsplit("@", 1)
        registry = ProfileRegistry(args.profile_catalog, identifier, version)
        profile = registry.active
        manifest = ModelManifest.model_validate_json(args.model_manifest.read_text(encoding="utf-8"))
        fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        service = ReplayService(AuditStore(args.db), fixtures, registry)
        event, _ = service.inspect_image_bytes(raw, profile, manifest, args.model_root, args.image.name)
    except (OSError, ValueError, LookupError) as exc:
        parser.error(str(exc))
    print(json.dumps(event, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
