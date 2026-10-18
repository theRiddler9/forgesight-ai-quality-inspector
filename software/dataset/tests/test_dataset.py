import hashlib
import json

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from software.dataset.manifest import DatasetManifest
from software.dataset.audit import audit_dataset, split_manifest, validate_images


def sample_manifest():
    entries = []
    for index, (part, session) in enumerate([("a", "one"), ("a", "one"), ("b", "two"), ("b", "two"), ("c", "three"), ("d", "four")]):
        entries.append({
            "image_id": f"img-{index}", "source": "local_capture", "source_license": "owned_by_team",
            "component_profile": "metal-plate-v1@1.0.0", "capture_session": session,
            "physical_part_id": part, "batch_id": None, "image_path": f"images/{index}.png",
            "sha256": f"{index:064x}", "width": 64, "height": 64,
            "annotation_path": None, "annotation_format": None, "defect_labels": [],
            "review_status": "reviewed", "split": None,
        })
    return {"dataset_version": "1.0.0", "entries": entries}


def test_manifest_validates_paths_labels_and_versions():
    data = sample_manifest()
    manifest = DatasetManifest.model_validate(data)
    assert len(manifest.entries) == 6
    data["entries"][0]["image_path"] = "../escape.png"
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(data)
    data = sample_manifest()
    data["entries"][0]["annotation_format"] = "bbox_json_v1"
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(data)
    data = sample_manifest()
    data["dataset_version"] = "bad"
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(data)


def test_split_policy_rejects_forged_fractions():
    data = sample_manifest()
    data["split_policy"] = {"group_by": "physical_part_id", "seed": 42,
                            "fractions": [0.8, 0.3, 0.1], "input_sha256": "a" * 64}
    with pytest.raises(ValidationError, match="split fractions"):
        DatasetManifest.model_validate(data)


def test_grouped_split_is_deterministic_and_keeps_parts_together():
    manifest = DatasetManifest.model_validate(sample_manifest())
    first = split_manifest(manifest, group_by="physical_part_id", seed=17)
    second = split_manifest(manifest, group_by="physical_part_id", seed=17)
    assert first == second
    by_part = {}
    for item in first.entries:
        by_part.setdefault(item.physical_part_id, set()).add(item.split)
    assert all(len(splits) == 1 for splits in by_part.values())
    assert {item.split for item in first.entries} == {"train", "validation", "test"}


def test_missing_group_does_not_claim_leakage_protection():
    manifest = DatasetManifest.model_validate(sample_manifest())
    with pytest.raises(ValueError, match="missing grouping key"):
        split_manifest(manifest, group_by="batch_id")
    report = audit_dataset(manifest, group_by="batch_id")
    assert not report["grouping_complete"]


def test_exact_duplicates_and_cross_split_leakage_reported():
    data = sample_manifest()
    data["entries"][1]["sha256"] = data["entries"][0]["sha256"]
    data["entries"][0]["split"] = "train"
    data["entries"][1]["split"] = "test"
    report = audit_dataset(DatasetManifest.model_validate(data), group_by="physical_part_id")
    assert report["duplicate_groups"] == [["img-0", "img-1"]]
    assert report["cross_split_duplicate_groups"] == [["img-0", "img-1"]]
    assert "a" in report["cross_split_groups"]


def test_image_and_annotation_validation(tmp_path):
    data = sample_manifest()
    data["entries"] = data["entries"][:1]
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    path = tmp_path / "images" / "0.png"
    path.parent.mkdir()
    assert cv2.imwrite(str(path), image)
    data["entries"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    data["entries"][0]["annotation_path"] = "annotations/0.json"
    data["entries"][0]["annotation_format"] = "bbox_json_v1"
    data["entries"][0]["defect_labels"] = ["heavy_burr"]
    ann = tmp_path / "annotations" / "0.json"
    ann.parent.mkdir()
    ann.write_text(json.dumps({"boxes": [{"label": "heavy_burr", "xywh_normalized": [0.1, 0.2, 0.3, 0.4]}]}))
    manifest = DatasetManifest.model_validate(data)
    assert validate_images(manifest, tmp_path) == []
    ann.write_text(json.dumps({"boxes": [{"label": "heavy_burr", "xywh_normalized": [0.9, 0.2, 0.3, 0.4]}]}))
    assert "annotation" in validate_images(manifest, tmp_path)[0]
    ann.write_text(json.dumps({"boxes": []}))
    assert "labels" in validate_images(manifest, tmp_path)[0]
    path.write_bytes(b"broken")
    assert any("hash" in error for error in validate_images(manifest, tmp_path))
