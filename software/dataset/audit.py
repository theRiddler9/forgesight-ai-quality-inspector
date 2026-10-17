"""Integrity checks, exact duplicate audit, and deterministic group splits."""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from software.dataset.manifest import DatasetManifest, ImageRecord


GroupBy = Literal["physical_part_id", "capture_session", "batch_id", "source"]


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1)
    xywh_normalized: tuple[float, float, float, float]

    @model_validator(mode="after")
    def bounds(self):
        x, y, w, h = self.xywh_normalized
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1 and x + w <= 1 and y + h <= 1):
            raise ValueError("annotation box must fit image and have positive area")
        return self


class Annotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    boxes: list[Box]


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("dataset path escapes root")
    return path


def validate_images(manifest: DatasetManifest, root: str | Path) -> list[str]:
    """Return all integrity/annotation errors; raw images remain untouched."""
    root = Path(root).resolve()
    errors = []
    for item in manifest.entries:
        try:
            raw = _inside(root, item.image_path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != item.sha256:
                errors.append(f"{item.image_id}: image hash mismatch")
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if image is None or image.shape[1] != item.width or image.shape[0] != item.height:
                errors.append(f"{item.image_id}: image decode or dimensions mismatch")
        except (OSError, ValueError, cv2.error) as exc:
            errors.append(f"{item.image_id}: image unavailable or invalid: {exc}")
        if item.annotation_path:
            try:
                data = json.loads(_inside(root, item.annotation_path).read_text(encoding="utf-8"))
                annotation = Annotation.model_validate(data)
                if {box.label for box in annotation.boxes} != set(item.defect_labels):
                    errors.append(f"{item.image_id}: annotation labels disagree with manifest")
            except (OSError, ValueError) as exc:
                errors.append(f"{item.image_id}: annotation invalid: {exc}")
    return errors


def split_manifest(
    manifest: DatasetManifest,
    group_by: GroupBy,
    seed: int = 42,
    fractions: tuple[float, float, float] = (0.7, 0.15, 0.15),
) -> DatasetManifest:
    """Allocate whole groups. Refuse missing keys rather than imply leakage protection."""
    if len(fractions) != 3 or any(not 0 < x < 1 for x in fractions) or abs(sum(fractions) - 1) > 1e-9:
        raise ValueError("train/validation/test fractions must be positive and sum to one")
    groups: dict[str, list[ImageRecord]] = defaultdict(list)
    for item in manifest.entries:
        key = getattr(item, group_by)
        if not key:
            raise ValueError(f"missing grouping key {group_by} for {item.image_id}")
        groups[key].append(item)
    keys = sorted(groups)
    if len(keys) < 3:
        raise ValueError("at least three independent groups are needed for a three-way split")
    random.Random(seed).shuffle(keys)
    n = len(keys)
    validation_count = max(1, round(n * fractions[1]))
    test_count = max(1, round(n * fractions[2]))
    if validation_count + test_count >= n:
        validation_count = test_count = 1
    train_count = n - validation_count - test_count
    assignments = dict(zip(keys, ["train"] * train_count + ["validation"] * validation_count + ["test"] * test_count))
    return manifest.model_copy(update={
        "entries": [item.model_copy(update={"split": assignments[getattr(item, group_by)]}) for item in manifest.entries]
    })


def audit_dataset(manifest: DatasetManifest, group_by: GroupBy | None = None) -> dict:
    by_hash: dict[str, list[str]] = defaultdict(list)
    by_hash_splits: dict[str, set[str]] = defaultdict(set)
    groups: dict[str, set[str]] = defaultdict(set)
    missing = []
    for item in manifest.entries:
        by_hash[item.sha256].append(item.image_id)
        if item.split:
            by_hash_splits[item.sha256].add(item.split)
        if group_by:
            key = getattr(item, group_by)
            if not key:
                missing.append(item.image_id)
            elif item.split:
                groups[key].add(item.split)
    duplicate_hashes = sorted(key for key, ids in by_hash.items() if len(ids) > 1)
    return {
        "dataset_version": manifest.dataset_version,
        "image_count": len(manifest.entries),
        "profile_counts": dict(sorted(Counter(item.component_profile for item in manifest.entries).items())),
        "label_counts": dict(sorted(Counter(label for item in manifest.entries for label in item.defect_labels).items())),
        "split_counts": dict(sorted(Counter(item.split or "unassigned" for item in manifest.entries).items())),
        "review_counts": dict(sorted(Counter(item.review_status for item in manifest.entries).items())),
        "duplicate_groups": [sorted(by_hash[key]) for key in duplicate_hashes],
        "cross_split_duplicate_groups": [sorted(by_hash[key]) for key in duplicate_hashes if len(by_hash_splits[key]) > 1],
        "group_by": group_by,
        "grouping_complete": group_by is not None and not missing,
        "missing_group_ids": sorted(missing),
        "cross_split_groups": sorted(key for key, splits in groups.items() if len(splits) > 1),
    }
