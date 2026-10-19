"""Review-gated canonical annotation validation and lossless YOLO export."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from software.dataset.audit import Annotation, _inside, validate_images
from software.dataset.manifest import DatasetManifest


class AnnotationError(ValueError):
    pass


def _check_class_map(class_map: dict[str, int]) -> None:
    if not class_map or sorted(class_map.values()) != list(range(len(class_map))):
        raise AnnotationError("class IDs must be unique and contiguous from zero")
    if any(not name or not all(char.isalnum() or char in "_-" for char in name) for name in class_map):
        raise AnnotationError("class names must be simple labels")


def validate_annotation_set(manifest: DatasetManifest, root: str | Path, class_map: dict[str, int]) -> list[str]:
    _check_class_map(class_map)
    root = Path(root).resolve()
    errors = validate_images(manifest, root)
    for item in manifest.entries:
        if item.review_status != "reviewed":
            errors.append(f"{item.image_id}: reviewed annotation required")
        if item.annotation_path is None:
            errors.append(f"{item.image_id}: missing annotation (empty JSON boxes required for clean image)")
            continue
        try:
            annotation = Annotation.model_validate_json(_inside(root, item.annotation_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # validate_images already records the malformed annotation
        seen = set()
        for box in annotation.boxes:
            key = (box.label, box.xywh_normalized)
            if key in seen:
                errors.append(f"{item.image_id}: duplicate box")
            seen.add(key)
            if box.label not in class_map:
                errors.append(f"{item.image_id}: unknown class {box.label}")
        if {box.label for box in annotation.boxes} != set(item.defect_labels):
            errors.append(f"{item.image_id}: manifest labels disagree with annotation")
    return errors


def export_yolo(manifest: DatasetManifest, root: str | Path, destination: str | Path, class_map: dict[str, int], dry_run: bool = False) -> dict:
    """Copy reviewed images and derived labels into a new, never-overwritten directory."""
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.exists():
        raise AnnotationError("export destination already exists")
    errors = validate_annotation_set(manifest, root, class_map)
    if any(item.split is None for item in manifest.entries):
        errors.append("all exported images need an assigned split")
    if errors:
        raise AnnotationError("; ".join(errors))
    report = {"image_count": len(manifest.entries), "class_map": class_map,
              "dataset_version": manifest.dataset_version,
              "input_manifest_sha256": hashlib.sha256(manifest.model_dump_json().encode()).hexdigest(),
              "dry_run": dry_run}
    if dry_run:
        return report
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".forgesight-yolo-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        exported = []
        for item in manifest.entries:
            suffix = Path(item.image_path).suffix.lower()
            image_target = stage / "images" / item.split / f"{item.image_id}{suffix}"
            label_target = stage / "labels" / item.split / f"{item.image_id}.txt"
            image_target.parent.mkdir(parents=True, exist_ok=True)
            label_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_inside(root, item.image_path), image_target)
            annotation = Annotation.model_validate_json(_inside(root, item.annotation_path).read_text(encoding="utf-8"))
            lines = []
            for box in annotation.boxes:
                x, y, w, h = box.xywh_normalized
                values = (x + w / 2, y + h / 2, w, h)
                lines.append(" ".join([str(class_map[box.label]), *(f"{value:.10g}" for value in values)]))
            label_target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            exported.append({"image_id": item.image_id, "split": item.split,
                             "source_image_sha256": item.sha256,
                             "source_annotation": item.annotation_path,
                             "review_status": item.review_status,
                             "image": image_target.relative_to(stage).as_posix(),
                             "label": label_target.relative_to(stage).as_posix()})
        (stage / "export-manifest.json").write_text(json.dumps({**report, "items": exported}, indent=2) + "\n", encoding="utf-8")
        names = [name for name, _ in sorted(class_map.items(), key=lambda pair: pair[1])]
        # The staging directory is renamed below; YAML must reference the final location.
        (stage / "dataset.yaml").write_text(
            f"path: {json.dumps(destination.as_posix())}\n"
            "train: images/train\nval: images/validation\ntest: images/test\nnames:\n"
            + "".join(f"  {i}: {name}\n" for i, name in enumerate(names)),
            encoding="utf-8",
        )
        if destination.exists():
            raise AnnotationError("export destination already exists")
        stage.rename(destination)
    return report
