"""Preflight by default; training needs an explicit execution flag."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
from pathlib import Path

from pydantic import ValidationError

from software.dataset.annotations import export_yolo
from software.dataset.manifest import DatasetManifest
from software.ml.training.config import TrainingConfig
from software.ml.training.preflight import preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="ForgeSight optional YOLO training")
    parser.add_argument("action", choices=["preflight", "train"])
    parser.add_argument("config", type=Path)
    parser.add_argument("--execute-training", action="store_true")
    args = parser.parse_args()
    try:
        report = preflight(args.config)
    except (OSError, ValueError, ValidationError) as exc:
        print(json.dumps({"ready": False, "issues": [f"invalid training configuration: {exc}"]}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    if args.action == "preflight":
        return 0 if report["ready"] else 2
    if not args.execute_training:
        parser.error("train requires --execute-training; preflight alone never starts training")
    if not report["ready"]:
        return 2
    try:
        from ultralytics import YOLO  # optional dependency, imported only for explicit training
    except ImportError as exc:
        parser.error(f"optional training dependency unavailable: {exc}")
    config_path = args.config.resolve()
    config = TrainingConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    manifest_path = (config_path.parent / config.dataset_manifest).resolve()
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    output = Path(report["output_directory"])
    output.mkdir(parents=True, exist_ok=False)
    class_map = {name: index for index, name in enumerate(config.classes)}
    export_yolo(manifest, manifest_path.parent, output / "dataset", class_map)
    metadata = {"config_sha256":report["config_sha256"],
        "profile_fingerprint":report["profile_fingerprint"], "dataset_version":config.dataset_version,
        "random_seed":config.random_seed, "architecture":config.architecture,
        "python_version":platform.python_version(),
        "ultralytics_version":importlib.metadata.version("ultralytics"),
        "status":"started", "model_source":"architecture_yaml_no_pretrained_weights"}
    (output / "run-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    model = YOLO("yolo11n.yaml")  # architecture only; no pretrained weights downloaded
    device = None if config.device == "auto" else ("0" if config.device == "cuda" else "cpu")
    augmentation = config.augmentation
    model.train(data=str(output / "dataset" / "dataset.yaml"), epochs=config.epochs,
                batch=config.batch_size, lr0=config.learning_rate, imgsz=config.input_width,
                seed=config.random_seed, deterministic=True, device=device,
                degrees=augmentation.rotation_degrees if augmentation.enabled else 0,
                fliplr=0.5 if augmentation.enabled and augmentation.horizontal_flip else 0,
                hsv_v=0.1 if augmentation.enabled and augmentation.lighting else 0,
                project=str(output / "runs"), name="train", exist_ok=False, pretrained=False)
    metadata["status"] = "completed"
    (output / "run-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
