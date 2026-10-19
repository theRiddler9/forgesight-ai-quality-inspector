"""Configuration schema; validation is distinct from operational approval."""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from software.edge.config import DecisionThresholds, EdgeConfig, PokaYokeConfig


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ImageSpec(StrictModel):
    width: int = Field(ge=32)
    height: int = Field(ge=32)
    pixel_format: Literal["BGR8"]


class RegionOfInterest(StrictModel):
    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("ROI must fit within normalized image bounds")
        return self


class Calibration(StrictModel):
    required: bool
    reference: str | None
    units: Literal["px", "mm"]
    pixels_per_mm: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_reference(self):
        if self.required and (not self.reference or self.pixels_per_mm is None):
            raise ValueError("required calibration needs a reference and pixels_per_mm")
        if self.units == "mm" and not self.required:
            raise ValueError("millimeter rules require calibration")
        return self


GeometryRule = Literal["part_presence", "position_alignment", "orientation", "size_range", "hole_presence"]


class GeometrySpec(StrictModel):
    adapter: Literal["rectangular_plate_v1", "annular_v1"]
    rules: list[GeometryRule] = Field(min_length=1)
    expected_orientation_deg: float = Field(ge=-90, le=90)
    min_part_area_px: float = Field(gt=0)
    max_part_area_ratio: float = Field(gt=0, lt=1)
    min_contrast_std: float = Field(ge=0)
    expected_center_px: tuple[float, float]
    center_tolerance_px: float = Field(ge=0)
    max_tilt_deg: float = Field(ge=0, le=45)
    border_margin_px: int = Field(ge=0)
    expected_size_px: tuple[float, float]
    size_tolerance_ratio: float = Field(ge=0, lt=1)
    required_hole_count: int = Field(ge=0)
    hole_area_px: tuple[float, float]
    expected_hole_centers_px: list[tuple[float, float]]
    hole_center_tolerance_px: float | None = Field(default=None, ge=0)
    physical_dimensions_mm: tuple[float, float] | None = None
    physical_tolerance_mm: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def supported_rules(self):
        if len(self.rules) != len(set(self.rules)):
            raise ValueError("geometry rules must be unique")
        if min(*self.expected_center_px, *self.expected_size_px, *self.hole_area_px) < 0:
            raise ValueError("geometry pixel dimensions must be nonnegative")
        if min(self.expected_size_px) <= 0 or self.hole_area_px[0] >= self.hole_area_px[1]:
            raise ValueError("invalid expected size or hole area range")
        if self.adapter == "rectangular_plate_v1":
            if self.expected_orientation_deg != 0 or self.required_hole_count > 1 or self.expected_hole_centers_px:
                raise ValueError("rectangular_plate_v1 cannot enforce this orientation or hole layout")
            if set(self.rules) != {"part_presence", "position_alignment", "orientation", "size_range", "hole_presence"}:
                raise ValueError("rectangular_plate_v1 requires all implemented geometry rules")
        if self.physical_dimensions_mm is not None and min(self.physical_dimensions_mm) <= 0:
            raise ValueError("physical dimensions must be positive")
        return self

    def edge_config(self) -> PokaYokeConfig:
        if self.adapter != "rectangular_plate_v1":
            raise ValueError(f"geometry adapter {self.adapter} is not implemented")
        return PokaYokeConfig(
            min_part_area_px=self.min_part_area_px,
            max_part_area_ratio=self.max_part_area_ratio,
            min_contrast_std=self.min_contrast_std,
            expected_center_px=self.expected_center_px,
            center_tolerance_px=self.center_tolerance_px,
            max_tilt_deg=self.max_tilt_deg,
            border_margin_px=self.border_margin_px,
            expected_size_px=self.expected_size_px,
            size_tolerance_ratio=self.size_tolerance_ratio,
            expect_hole=self.required_hole_count > 0,
            hole_area_px=self.hole_area_px,
        )


class PreprocessingSpec(StrictModel):
    contrast_clip_limit: float = Field(gt=0)
    rotation_deg: Literal[0, 90, 180, 270] = 0
    model_width: int | None = Field(default=None, ge=32)
    model_height: int | None = Field(default=None, ge=32)
    normalization: Literal["zero_one", "none"] = "zero_one"

    @model_validator(mode="after")
    def paired_model_size(self):
        if (self.model_width is None) != (self.model_height is None):
            raise ValueError("model width and height must be supplied together")
        return self


class DetectorSpec(StrictModel):
    backend: Literal["scenario_simulation", "onnx", "rknn"]
    model_id: str = Field(min_length=1)
    model_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    artifact_path: str | None
    artifact_sha256: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    compatible_profiles: list[str] = Field(min_length=1)
    defect_classes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def check_artifact(self):
        if self.backend == "scenario_simulation":
            if self.artifact_path or self.artifact_sha256:
                raise ValueError("simulated detector cannot claim a model artifact")
        else:
            if not self.artifact_path or not self.artifact_sha256:
                raise ValueError("real detector needs artifact path and SHA-256 metadata")
            path = PurePosixPath(self.artifact_path)
            if path.is_absolute() or ".." in path.parts or "\\" in self.artifact_path:
                raise ValueError("model artifact path must be relative and remain inside model storage")
        if len(set(self.defect_classes)) != len(self.defect_classes):
            raise ValueError("defect classes must be unique")
        return self


class ThresholdSpec(StrictModel):
    fail_confidence: float = Field(ge=0, le=1)
    recheck_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.recheck_confidence >= self.fail_confidence:
            raise ValueError("recheck threshold must be below fail threshold")
        return self


class ComponentProfile(StrictModel):
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    display_name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    validation_status: Literal["provisional", "replay_validated", "real_approved"]
    image: ImageSpec
    roi: RegionOfInterest
    geometry: GeometrySpec
    calibration: Calibration
    preprocessing: PreprocessingSpec
    detector: DetectorSpec
    thresholds: ThresholdSpec

    @model_validator(mode="after")
    def compatible(self):
        if f"{self.profile_id}@{self.version}" not in self.detector.compatible_profiles:
            raise ValueError("detector model is incompatible with this profile version")
        if self.geometry.physical_dimensions_mm is not None and not self.calibration.required:
            raise ValueError("physical dimensions require calibration")
        if self.validation_status == "real_approved" and (not self.calibration.required or self.detector.backend == "scenario_simulation"):
            raise ValueError("real approval requires calibration and a real detector")
        if not (0 <= self.geometry.expected_center_px[0] < self.image.width and 0 <= self.geometry.expected_center_px[1] < self.image.height):
            raise ValueError("expected center must lie inside the image")
        if self.geometry.min_part_area_px >= self.image.width * self.image.height:
            raise ValueError("minimum part area exceeds image area")
        if any(not (0 <= x < self.image.width and 0 <= y < self.image.height) for x, y in self.geometry.expected_hole_centers_px):
            raise ValueError("expected hole center must lie inside the image")
        if self.geometry.adapter == "rectangular_plate_v1" and (self.roi.x, self.roi.y, self.roi.width, self.roi.height) != (0, 0, 1, 1):
            raise ValueError("rectangular_plate_v1 currently requires a full-frame ROI")
        return self

    @property
    def fingerprint(self) -> str:
        # Exclude newly introduced defaults so existing profile fingerprints
        # keep their historical meaning until those settings are explicit.
        canonical = json.dumps(self.model_dump(mode="json", exclude_unset=True), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def preprocessing_fingerprint(self) -> str:
        canonical = json.dumps({"image": self.image.model_dump(mode="json"),
                                "roi": self.roi.model_dump(mode="json"),
                                "preprocessing": self.preprocessing.model_dump(mode="json")},
                               sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def replay_suitable(self) -> bool:
        return (self.geometry.adapter == "rectangular_plate_v1"
                and self.detector.backend == "scenario_simulation"
                and self.preprocessing.rotation_deg == 0
                and self.preprocessing.model_width is None
                and self.preprocessing.model_height is None
                and self.preprocessing.normalization == "zero_one")

    @property
    def real_inspection_ready(self) -> bool:
        # No ONNX/RKNN runtime or physical calibration has been validated in this phase.
        return False

    def edge_config(self) -> EdgeConfig:
        return EdgeConfig(
            thresholds=DecisionThresholds(
                fail_confidence=self.thresholds.fail_confidence,
                recheck_confidence=self.thresholds.recheck_confidence,
            ),
            poka_yoke=self.geometry.edge_config(),
            contrast_clip_limit=self.preprocessing.contrast_clip_limit,
        )
