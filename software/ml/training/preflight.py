"""Read-only training readiness checks; no framework import or output creation."""
from __future__ import annotations

import hashlib
from pathlib import Path

from software.dataset.annotations import validate_annotation_set
from software.dataset.audit import audit_dataset, decoded_cross_split_duplicates
from software.dataset.manifest import DatasetManifest
from software.ml.training.config import TrainingConfig
from software.profiles.registry import ProfileRegistry, UnknownProfile


def preflight(config_path: str | Path, registry: ProfileRegistry | None = None) -> dict:
    config_path = Path(config_path).resolve()
    raw = config_path.read_bytes()
    config = TrainingConfig.model_validate_json(raw)
    registry = registry or ProfileRegistry(Path(__file__).resolve().parents[2] / "profiles" / "catalog")
    issues = []
    identifier, version = config.component_profile.rsplit("@", 1)
    try:
        profile = registry.get(identifier, version)
    except UnknownProfile:
        profile = None
        issues.append("component profile not found")
    if profile:
        if profile.detector.backend == "scenario_simulation":
            issues.append("profile detector remains scenario simulation; create a versioned real-model profile")
        if config.classes != profile.detector.defect_classes:
            issues.append("class mapping differs from profile detector classes")
        if (config.input_width, config.input_height) != (profile.preprocessing.model_width or profile.image.width,
                                                         profile.preprocessing.model_height or profile.image.height):
            issues.append("model input dimensions differ from profile preprocessing")
        if (config.fail_confidence, config.recheck_confidence) != (profile.thresholds.fail_confidence, profile.thresholds.recheck_confidence):
            issues.append("decision thresholds differ from profile")
    if config.input_width != config.input_height:
        issues.append("YOLO training entry point currently requires a square model input")
    manifest_path = (config_path.parent / config.dataset_manifest).resolve()
    manifest = None
    if not manifest_path.is_file():
        issues.append("dataset manifest missing")
    else:
        try:
            manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            issues.append(f"dataset manifest invalid: {exc}")
    dataset_report = None
    if manifest:
        if manifest.dataset_version != config.dataset_version:
            issues.append("dataset version mismatch")
        if any(item.component_profile != config.component_profile for item in manifest.entries):
            issues.append("dataset contains an incompatible component profile")
        if any(item.source_license.strip().lower() in {"unknown", "unspecified", "none"} for item in manifest.entries):
            issues.append("dataset contains unknown source license claims")
        dataset_report = audit_dataset(manifest, config.group_by)
        if not dataset_report["split_audit"]["passed"]:
            issues.append("split audit failed; inspect report for leakage, reviews, or missing policy")
        if manifest.split_policy and manifest.split_policy.group_by != config.group_by:
            issues.append("split policy grouping differs from training configuration")
        annotation_errors = validate_annotation_set(manifest, manifest_path.parent,
                                                    {name: index for index, name in enumerate(config.classes)})
        issues.extend(annotation_errors)
        if not annotation_errors:
            decoded_duplicates = decoded_cross_split_duplicates(manifest, manifest_path.parent)
            if decoded_duplicates:
                issues.append(f"decoded pixel duplicates cross splits: {decoded_duplicates}")
        for label in config.classes:
            if not any(label in item.defect_labels and item.split == "train" for item in manifest.entries):
                issues.append(f"training split has no reviewed examples of {label}")
            if not any(label in item.defect_labels and item.split == "validation" for item in manifest.entries):
                issues.append(f"validation split has no reviewed examples of {label}")
            if not any(label in item.defect_labels and item.split == "test" for item in manifest.entries):
                issues.append(f"held-out test split has no reviewed examples of {label}")
    output = (config_path.parent / config.output_directory).resolve()
    if output.exists():
        issues.append("training output directory already exists")
    return {"ready": not issues, "issues": issues,
            "config_sha256": hashlib.sha256(raw).hexdigest(),
            "component_profile": config.component_profile,
            "profile_fingerprint": profile.fingerprint if profile else None,
            "dataset_report": dataset_report,
            "output_directory": str(output)}
