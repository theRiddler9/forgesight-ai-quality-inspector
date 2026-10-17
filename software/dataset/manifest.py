"""Strict, versioned records for future real-image datasets."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or value.startswith("/"):
        raise ValueError("dataset paths must be safe relative POSIX paths")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImageRecord(StrictModel):
    image_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_license: str = Field(min_length=1)
    component_profile: str = Field(pattern=r"^[a-z][a-z0-9-]*@[0-9]+\.[0-9]+\.[0-9]+$")
    capture_session: str | None
    physical_part_id: str | None
    batch_id: str | None
    image_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    annotation_path: str | None
    annotation_format: Literal["bbox_json_v1"] | None
    defect_labels: list[str]
    review_status: Literal["unreviewed", "reviewed", "disputed"]
    split: Literal["train", "validation", "test"] | None

    @model_validator(mode="after")
    def paths_and_annotations(self):
        _safe_relative(self.image_path)
        if self.annotation_path is not None:
            _safe_relative(self.annotation_path)
        if (self.annotation_path is None) != (self.annotation_format is None):
            raise ValueError("annotation path and format must be supplied together")
        if len(set(self.defect_labels)) != len(self.defect_labels) or any(not label for label in self.defect_labels):
            raise ValueError("defect labels must be unique and nonempty")
        return self


class DatasetManifest(StrictModel):
    dataset_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    entries: list[ImageRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.image_id for item in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("image IDs must be unique")
        return self
