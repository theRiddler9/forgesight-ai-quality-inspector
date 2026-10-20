"""Explicit local image intake. No network access or executable archive handling."""
from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

import cv2
import numpy as np

from software.dataset.manifest import DatasetManifest


class IntakeError(ValueError):
    pass


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024


def _archive_files(archive: Path) -> list[str]:
    try:
        with zipfile.ZipFile(archive) as source:
            names = []
            total = 0
            seen = set()
            for entry in source.infolist():
                name = entry.filename
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or not name:
                    raise IntakeError(f"unsafe archive path: {name}")
                if name in seen:
                    raise IntakeError(f"duplicate archive path: {name}")
                seen.add(name)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise IntakeError(f"archive symlink refused: {name}")
                if entry.is_dir():
                    continue
                if mode and not stat.S_ISREG(mode) and (mode & stat.S_IFMT(mode)):
                    raise IntakeError(f"non-file archive entry refused: {name}")
                if entry.file_size > _MAX_IMAGE_BYTES:
                    raise IntakeError(f"archive image too large: {name}")
                total += entry.file_size
                if total > _MAX_ARCHIVE_BYTES:
                    raise IntakeError("archive exceeds intake size limit")
                if path.suffix.lower() in _IMAGE_SUFFIXES:
                    names.append(name)
            return sorted(names)
    except (OSError, zipfile.BadZipFile) as exc:
        raise IntakeError("cannot read authorized ZIP archive") from exc


def _directory_files(source: Path) -> list[str]:
    names = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise IntakeError(f"source symlink refused: {path.name}")
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
            if path.stat().st_size > _MAX_IMAGE_BYTES:
                raise IntakeError(f"image too large: {path.name}")
            names.append(path.relative_to(source).as_posix())
    return names


def _read(source: Path, name: str, archive: bool) -> bytes:
    if archive:
        with zipfile.ZipFile(source) as stream:
            with stream.open(name) as entry:
                raw = entry.read(_MAX_IMAGE_BYTES + 1)
    else:
        raw = (source / name).read_bytes()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise IntakeError(f"image too large: {name}")
    return raw


def import_dataset(
    source: str | Path,
    destination: str | Path,
    dataset_version: str,
    profile: str,
    source_name: str,
    source_license: str,
    capture_session: str | None,
    dry_run: bool = False,
) -> dict:
    """Validate first, then publish a new manifest/raw directory atomically."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source_license.strip() or source_license.strip().lower() in {"unknown", "unspecified", "none"}:
        raise IntakeError("explicit source license or team ownership attestation required")
    if not source_name.strip():
        raise IntakeError("source name required")
    if destination.exists():
        raise IntakeError("destination already exists; raw intake is immutable")
    if source.is_dir():
        names, archive = _directory_files(source), False
    elif source.is_file() and source.suffix.lower() == ".zip":
        names, archive = _archive_files(source), True
    else:
        raise IntakeError("source must be a local directory or explicitly supplied ZIP archive")
    if not names:
        raise IntakeError("no supported images found")
    entries = []
    by_hash = defaultdict(list)
    for index, name in enumerate(names, 1):
        try:
            raw = _read(source, name, archive)
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        except (OSError, zipfile.BadZipFile, RuntimeError, cv2.error) as exc:
            raise IntakeError(f"cannot decode image {name}") from exc
        if image is None or image.ndim not in (2, 3):
            raise IntakeError(f"cannot decode image {name}")
        digest = hashlib.sha256(raw).hexdigest()
        image_id = f"img-{index:06d}"
        by_hash[digest].append(image_id)
        entries.append({
            "image_id": image_id, "source": source_name, "source_license": source_license,
            "component_profile": profile, "capture_session": capture_session,
            "physical_part_id": None, "batch_id": None,
            "image_path": f"raw/{digest}{PurePosixPath(name).suffix.lower()}",
            "sha256": digest, "width": int(image.shape[1]), "height": int(image.shape[0]),
            "annotation_path": None, "annotation_format": None, "defect_labels": [],
            "review_status": "unreviewed", "split": None,
        })
    manifest = DatasetManifest.model_validate({"dataset_version": dataset_version, "entries": entries})
    report = {
        "dry_run": dry_run,
        "image_count": len(entries),
        "duplicate_groups": [ids for ids in by_hash.values() if len(ids) > 1],
        "license_claim": source_license,
        "source_name": source_name,
        "profile": profile,
        "capture_session": capture_session,
        "provenance_verified": False,
    }
    if dry_run:
        return report
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".forgesight-intake-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        (stage / "raw").mkdir()
        for name, item in zip(names, manifest.entries):
            raw = _read(source, name, archive)
            if hashlib.sha256(raw).hexdigest() != item.sha256:
                raise IntakeError(f"source changed during intake: {name}")
            target = stage / item.image_path
            if not target.exists():
                target.write_bytes(raw)
        (stage / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        (stage / "intake-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            raise IntakeError("destination already exists")
        stage.rename(destination)
    return report
