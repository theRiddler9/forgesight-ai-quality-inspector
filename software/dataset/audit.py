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

from software.dataset.manifest import DatasetManifest, ImageRecord, SplitPolicy


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


def decoded_cross_split_duplicates(manifest: DatasetManifest, root: str | Path) -> list[list[str]]:
    """Detect byte-different files that decode to identical pixels."""
    root = Path(root).resolve()
    by_pixels: dict[str, list[ImageRecord]] = defaultdict(list)
    for item in manifest.entries:
        raw = _inside(root, item.image_path).read_bytes()
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError(f"cannot decode image {item.image_id}")
        digest = hashlib.sha256(str(image.shape).encode() + image.tobytes()).hexdigest()
        by_pixels[digest].append(item)
    return [sorted(item.image_id for item in group) for group in by_pixels.values()
            if len(group) > 1 and len({item.split for item in group}) > 1]


def split_manifest(
    manifest: DatasetManifest,
    group_by: GroupBy,
    seed: int = 42,
    fractions: tuple[float, float, float] = (0.7, 0.15, 0.15),
) -> DatasetManifest:
    """Allocate whole groups. Refuse missing keys rather than imply leakage protection."""
    if len(fractions) != 3 or any(not 0 < x < 1 for x in fractions) or abs(sum(fractions) - 1) > 1e-9:
        raise ValueError("train/validation/test fractions must be positive and sum to one")
    if manifest.split_policy or any(item.split is not None for item in manifest.entries):
        raise ValueError("splits already assigned; create a new dataset version to resplit")
    # Connected identities prevent part, session, and exact-image leakage even
    # when the requested primary grouping key is different.
    parent = list(range(len(manifest.entries)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        parent[find(right)] = find(left)

    identity_owner: dict[tuple[str, str], int] = {}
    for index, item in enumerate(manifest.entries):
        for field in {group_by, "physical_part_id", "capture_session", "sha256"}:
            key = getattr(item, field)
            if field == group_by and not key:
                raise ValueError(f"missing grouping key {group_by} for {item.image_id}")
            if key:
                identity = (field, key)
                if identity in identity_owner:
                    union(index, identity_owner[identity])
                else:
                    identity_owner[identity] = index
    groups: dict[int, list[ImageRecord]] = defaultdict(list)
    for index, item in enumerate(manifest.entries):
        groups[find(index)].append(item)
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
    updated = [item.model_copy(update={"split": assignments[find(index)]}) for index, item in enumerate(manifest.entries)]
    policy = SplitPolicy(group_by=group_by, seed=seed, fractions=fractions,
                         input_sha256=hashlib.sha256(manifest.model_dump_json().encode()).hexdigest())
    return manifest.model_copy(update={"entries": updated, "split_policy": policy})


def audit_dataset(manifest: DatasetManifest, group_by: GroupBy | None = None) -> dict:
    by_hash: dict[str, list[str]] = defaultdict(list)
    by_hash_splits: dict[str, set[str]] = defaultdict(set)
    groups: dict[str, set[str]] = defaultdict(set)
    part_splits: dict[str, set[str]] = defaultdict(set)
    session_splits: dict[str, set[str]] = defaultdict(set)
    missing = []
    for item in manifest.entries:
        by_hash[item.sha256].append(item.image_id)
        if item.split:
            by_hash_splits[item.sha256].add(item.split)
            if item.physical_part_id:
                part_splits[item.physical_part_id].add(item.split)
            if item.capture_session:
                session_splits[item.capture_session].add(item.split)
        if group_by:
            key = getattr(item, group_by)
            if not key:
                missing.append(item.image_id)
            elif item.split:
                groups[key].add(item.split)
    duplicate_hashes = sorted(key for key, ids in by_hash.items() if len(ids) > 1)
    cross_duplicates = [sorted(by_hash[key]) for key in duplicate_hashes if len(by_hash_splits[key]) > 1]
    cross_groups = sorted(key for key, splits in groups.items() if len(splits) > 1)
    cross_parts = sorted(key for key, splits in part_splits.items() if len(splits) > 1)
    cross_sessions = sorted(key for key, splits in session_splits.items() if len(splits) > 1)
    unreviewed_eval = sorted(item.image_id for item in manifest.entries if item.split in {"validation", "test"} and item.review_status != "reviewed")
    unassigned = sorted(item.image_id for item in manifest.entries if item.split is None)
    missing_parts = sorted(item.image_id for item in manifest.entries if not item.physical_part_id)
    missing_sessions = sorted(item.image_id for item in manifest.entries if not item.capture_session)
    split_failures = bool(cross_duplicates or cross_groups or cross_parts or cross_sessions or unreviewed_eval or missing or unassigned or missing_parts or missing_sessions or manifest.split_policy is None)
    return {
        "dataset_version": manifest.dataset_version,
        "image_count": len(manifest.entries),
        "profile_counts": dict(sorted(Counter(item.component_profile for item in manifest.entries).items())),
        "label_counts": dict(sorted(Counter(label for item in manifest.entries for label in item.defect_labels).items())),
        "split_counts": dict(sorted(Counter(item.split or "unassigned" for item in manifest.entries).items())),
        "review_counts": dict(sorted(Counter(item.review_status for item in manifest.entries).items())),
        "duplicate_groups": [sorted(by_hash[key]) for key in duplicate_hashes],
        "cross_split_duplicate_groups": cross_duplicates,
        "group_by": group_by,
        "grouping_complete": group_by is not None and not missing,
        "missing_group_ids": sorted(missing),
        "cross_split_groups": cross_groups,
        "split_audit": {
            "passed": not split_failures,
            "cross_split_duplicates": cross_duplicates,
            "cross_split_parts": cross_parts,
            "cross_split_sessions": cross_sessions,
            "cross_split_selected_groups": cross_groups,
            "unreviewed_evaluation_images": unreviewed_eval,
            "unassigned_images": unassigned,
            "missing_selected_group_ids": sorted(missing),
            "missing_part_ids": missing_parts,
            "missing_session_ids": missing_sessions,
            "missing_split_policy": manifest.split_policy is None,
            "policy": manifest.split_policy.model_dump() if manifest.split_policy else None,
        },
    }
