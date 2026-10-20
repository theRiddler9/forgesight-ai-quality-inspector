import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from software.dataset.annotations import AnnotationError, export_yolo, validate_annotation_set
from software.dataset.manifest import DatasetManifest


def dataset(tmp_path, boxes=None, review="reviewed"):
    root = tmp_path / "input"
    (root / "images").mkdir(parents=True)
    (root / "annotations").mkdir()
    ok, encoded = cv2.imencode(".png", np.zeros((32, 48, 3), dtype=np.uint8))
    assert ok
    raw = encoded.tobytes()
    (root / "images" / "a.png").write_bytes(raw)
    annotation = {"boxes": boxes if boxes is not None else [{"label": "heavy_burr", "xywh_normalized": [0.2, 0.3, 0.4, 0.2]}]}
    (root / "annotations" / "a.json").write_text(json.dumps(annotation))
    entry = {"image_id":"a", "source":"team", "source_license":"team-owned",
             "component_profile":"metal-plate-v1@1.0.0", "capture_session":"s1",
             "physical_part_id":"p1", "batch_id":"b1", "image_path":"images/a.png",
             "sha256": hashlib.sha256(raw).hexdigest(), "width":48, "height":32,
             "annotation_path":"annotations/a.json", "annotation_format":"bbox_json_v1",
             "defect_labels": [box["label"] for box in annotation["boxes"]][:1],
             "review_status":review, "split":"train"}
    return root, DatasetManifest.model_validate({"dataset_version":"1.0.0", "entries":[entry]})


def test_reviewed_export_preserves_original_and_converts_center(tmp_path):
    root, manifest = dataset(tmp_path)
    before = (root / "annotations" / "a.json").read_bytes()
    out = tmp_path / "export"
    report = export_yolo(manifest, root, out, {"heavy_burr": 0})
    assert report["image_count"] == 1
    assert (out / "labels" / "train" / "a.txt").read_text().strip() == "0 0.4 0.4 0.4 0.2"
    assert (out / "images" / "train" / "a.png").is_file()
    assert (root / "annotations" / "a.json").read_bytes() == before
    assert json.loads((out / "export-manifest.json").read_text())["class_map"] == {"heavy_burr": 0}
    with pytest.raises(AnnotationError, match="already exists"):
        export_yolo(manifest, root, out, {"heavy_burr": 0})


def test_exported_dataset_paths_resolve_from_another_working_directory(tmp_path, monkeypatch):
    root, manifest = dataset(tmp_path)
    destination = tmp_path / "exports" / "plate run"
    export_yolo(manifest, root, destination, {"heavy_burr": 0})
    lines = (destination / "dataset.yaml").read_text(encoding="utf-8").splitlines()
    base = Path(json.loads(lines[0].removeprefix("path: ")))
    paths = dict(line.split(": ", 1) for line in lines[1:4])
    monkeypatch.chdir(tmp_path / "input")
    assert base == destination.resolve()
    assert base != Path.cwd()
    assert {key: (base / relative).resolve() for key, relative in paths.items()} == {
        "train": (destination / "images" / "train").resolve(),
        "val": (destination / "images" / "validation").resolve(),
        "test": (destination / "images" / "test").resolve(),
    }
    assert (base / paths["train"] / "a.png").is_file()
    assert ".forgesight-yolo-" not in lines[0]


def test_clean_reviewed_image_has_empty_label_file(tmp_path):
    root, manifest = dataset(tmp_path, boxes=[])
    assert validate_annotation_set(manifest, root, {"heavy_burr": 0}) == []
    export_yolo(manifest, root, tmp_path / "export", {"heavy_burr": 0})
    assert (tmp_path / "export" / "labels" / "train" / "a.txt").read_text() == ""


@pytest.mark.parametrize("boxes,needle", [
    ([{"label":"other", "xywh_normalized":[0.1,0.1,0.2,0.2]}], "unknown class"),
    ([{"label":"heavy_burr", "xywh_normalized":[0.9,0.1,0.2,0.2]}], "annotation"),
    ([{"label":"heavy_burr", "xywh_normalized":[0.1,0.1,0.2,0.2]}] * 2, "duplicate box"),
])
def test_invalid_annotations_are_rejected(tmp_path, boxes, needle):
    root, manifest = dataset(tmp_path, boxes=boxes)
    assert needle in " ".join(validate_annotation_set(manifest, root, {"heavy_burr": 0}))


def test_unreviewed_and_missing_annotations_block_export(tmp_path):
    root, manifest = dataset(tmp_path, review="unreviewed")
    with pytest.raises(AnnotationError, match="reviewed"):
        export_yolo(manifest, root, tmp_path / "export", {"heavy_burr": 0})
    reviewed = manifest.model_copy(update={"entries": [manifest.entries[0].model_copy(update={"review_status":"reviewed", "annotation_path":None, "annotation_format":None})]})
    with pytest.raises(AnnotationError, match="missing annotation"):
        export_yolo(reviewed, root, tmp_path / "export", {"heavy_burr": 0})
