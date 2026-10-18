import json
import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from software.ml.training.config import TrainingConfig
from software.ml.training.preflight import preflight
from software.dataset.manifest import DatasetManifest
from software.dataset.audit import split_manifest
from software.profiles.registry import ProfileRegistry


def config_data():
    return {
        "config_version":"1.0.0", "component_profile":"metal-plate-v1@1.0.0",
        "dataset_version":"1.0.0", "dataset_manifest":"dataset/manifest.json",
        "architecture":"yolo11n", "input_width":1280, "input_height":800,
        "classes":["burr"], "epochs":10, "batch_size":2, "learning_rate":0.001,
        "random_seed":42, "device":"cpu", "augmentation":{"enabled":False},
        "group_by":"physical_part_id", "export_target":"onnx",
        "fail_confidence":0.8, "recheck_confidence":0.5,
        "output_directory":"data/training-runs/run1",
    }


def test_training_config_rejects_missing_and_invalid_values():
    data = config_data()
    assert TrainingConfig.model_validate(data).architecture == "yolo11n"
    data["epochs"] = 0
    with pytest.raises(ValueError):
        TrainingConfig.model_validate(data)
    data = config_data()
    data["classes"] = ["burr", "burr"]
    with pytest.raises(ValueError):
        TrainingConfig.model_validate(data)


def test_preflight_reports_missing_dataset_without_creating_output(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config_data()))
    report = preflight(path)
    assert not report["ready"]
    assert any("manifest" in issue for issue in report["issues"])
    assert not (tmp_path / "data").exists()


def test_template_is_explicitly_not_executable():
    template = Path(__file__).resolve().parents[1] / "training" / "training-config.template.json"
    with pytest.raises(ValueError):
        TrainingConfig.model_validate_json(template.read_text())


def test_structural_preflight_accepts_reviewed_synthetic_fixture_without_training(tmp_path):
    # This proves the gate mechanics only. It is not a real manufacturing dataset.
    profile_data = json.loads((Path(__file__).resolve().parents[2] / "profiles" / "catalog" / "metal-plate-v1.json").read_text())
    profile_data["detector"].update(backend="onnx", artifact_path="plate.onnx", artifact_sha256="a" * 64)
    profile_data["preprocessing"].update(model_width=640, model_height=640)
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "plate.json").write_text(json.dumps(profile_data))
    registry = ProfileRegistry(catalog)
    root = tmp_path / "dataset"
    (root / "images").mkdir(parents=True)
    (root / "annotations").mkdir()
    ok, encoded = cv2.imencode(".png", np.zeros((800, 1280, 3), dtype=np.uint8))
    assert ok
    entries = []
    for index in range(3):
        image = np.zeros((800, 1280, 3), dtype=np.uint8)
        image[0, 0] = index
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        raw = encoded.tobytes()
        path = root / "images" / f"{index}.png"
        path.write_bytes(raw)
        (root / "annotations" / f"{index}.json").write_text(json.dumps({"boxes":[{"label":"burr", "xywh_normalized":[0.1,0.1,0.2,0.2]}]}))
        entries.append({"image_id":f"synthetic-{index}", "source":"synthetic-test", "source_license":"test-only",
                        "component_profile":"metal-plate-v1@1.0.0", "capture_session":f"s{index}",
                        "physical_part_id":f"p{index}", "batch_id":None,
                        "image_path":f"images/{index}.png", "sha256":hashlib.sha256(raw).hexdigest(),
                        "width":1280, "height":800, "annotation_path":f"annotations/{index}.json",
                        "annotation_format":"bbox_json_v1", "defect_labels":["burr"],
                        "review_status":"reviewed", "split":None})
    manifest = split_manifest(DatasetManifest.model_validate({"dataset_version":"1.0.0", "entries":entries}), "physical_part_id")
    (root / "manifest.json").write_text(manifest.model_dump_json())
    data = config_data()
    data.update(input_width=640, input_height=640)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    report = preflight(path, registry)
    assert report["ready"], report["issues"]
    assert not (tmp_path / "data").exists()
