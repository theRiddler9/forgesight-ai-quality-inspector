"""Validated configuration for an explicit, reproducible training run."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Augmentation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    rotation_degrees: float = Field(default=0, ge=0, le=180)
    horizontal_flip: bool = False
    lighting: bool = False


class TrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_version: Literal["1.0.0"]
    component_profile: str = Field(pattern=r"^[a-z][a-z0-9-]*@[0-9]+\.[0-9]+\.[0-9]+$")
    dataset_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    dataset_manifest: str = Field(min_length=1)
    architecture: Literal["yolo11n"]
    input_width: int = Field(ge=32)
    input_height: int = Field(ge=32)
    classes: list[str] = Field(min_length=1)
    epochs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    learning_rate: float = Field(gt=0)
    random_seed: int = Field(ge=0)
    device: Literal["cpu", "cuda", "auto"]
    augmentation: Augmentation
    group_by: Literal["physical_part_id", "capture_session", "batch_id", "source"]
    export_target: Literal["onnx"]
    fail_confidence: float = Field(ge=0, le=1)
    recheck_confidence: float = Field(ge=0, le=1)
    output_directory: str = Field(min_length=1)

    @model_validator(mode="after")
    def consistency(self):
        if len(self.classes) != len(set(self.classes)) or any(not name for name in self.classes):
            raise ValueError("training classes must be unique and nonempty")
        if self.recheck_confidence >= self.fail_confidence:
            raise ValueError("recheck threshold must be below fail threshold")
        return self
