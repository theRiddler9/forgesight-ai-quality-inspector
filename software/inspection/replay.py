"""Versioned synthetic scenarios and a BGR8 replay source.

The legacy edge pipeline calls ``read()`` for grayscale frames. New consumers can
use ``capture()`` for the complete camera contract without changing that pipeline.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from software.edge.acquisition.camera import FrameSource
from software.profiles.models import ImageSpec


class ReplayError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class Scenario:
    name: str
    image_name: str | None
    detection_class: str | None
    detection_confidence: float | None


@dataclass(frozen=True)
class FramePacket:
    frame_id: str
    captured_at: datetime
    source_id: str
    sequence_number: int
    width: int
    height: int
    pixel_format: str
    image: np.ndarray
    source_uri: str
    sha256: str


class ScenarioCatalog:
    def __init__(self, fixture_dir: str | Path):
        self.fixture_dir = Path(fixture_dir).resolve()
        data = json.loads((self.fixture_dir / "scenarios.json").read_text(encoding="utf-8"))
        self._scenarios: dict[str, Scenario] = {}
        for name, item in data.items():
            if not name.isidentifier():
                raise ValueError(f"invalid scenario name: {name}")
            image = item["image"]
            if image is not None and (Path(image).name != image or Path(image).suffix.lower() != ".png"):
                raise ValueError(f"unsafe scenario image: {image}")
            detection = item.get("detection")
            confidence = detection["confidence"] if detection else None
            if confidence is not None and not 0 <= confidence <= 1:
                raise ValueError(f"invalid simulated confidence: {name}")
            self._scenarios[name] = Scenario(
                name, image, detection["class_name"] if detection else None, confidence
            )

    def get(self, name: str) -> Scenario:
        if name not in self._scenarios:
            raise ReplayError("UNKNOWN_SCENARIO", f"unknown replay scenario: {name}")
        return self._scenarios[name]

    def names(self) -> list[str]:
        return sorted(self._scenarios)


class ReplayFrameSource(FrameSource):
    def __init__(self, image_dir: str | Path, scenario: Scenario, expected_image: ImageSpec | None = None):
        self.image_dir = Path(image_dir).resolve()
        self.scenario = scenario
        self.expected_image = expected_image
        self.sequence_number = 0
        self.last_packet: FramePacket | None = None
        self.last_error: ReplayError | None = None

    def open(self) -> None:
        self.sequence_number = 0
        self.last_packet = None
        self.last_error = None

    def release(self) -> None:
        pass

    def capture(self) -> FramePacket:
        if self.scenario.image_name is None:
            raise ReplayError("CAMERA_UNAVAILABLE", "scenario simulates a capture fault")
        path = (self.image_dir / self.scenario.image_name).resolve()
        if not path.is_relative_to(self.image_dir):
            raise ReplayError("INVALID_FRAME", "image path leaves fixture directory")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ReplayError("MISSING_FRAME", f"cannot read fixture {path.name}") from exc
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.ndim != 3 or image.shape[2] != 3:
            raise ReplayError("INVALID_FRAME", f"cannot decode fixture {path.name}")
        height, width = image.shape[:2]
        if width < 32 or height < 32:
            raise ReplayError("FRAME_FORMAT_MISMATCH", f"fixture {path.name} is too small")
        if self.expected_image and (width != self.expected_image.width or height != self.expected_image.height or self.expected_image.pixel_format != "BGR8"):
            raise ReplayError("FRAME_FORMAT_MISMATCH", f"fixture {path.name} does not match component profile")
        packet = FramePacket(
            frame_id=str(uuid4()),
            captured_at=datetime.now(timezone.utc),
            source_id="synthetic-recorded-v1",
            sequence_number=self.sequence_number,
            width=width,
            height=height,
            pixel_format="BGR8",
            image=image,
            source_uri=f"fixtures/images/{path.name}",
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        self.sequence_number += 1
        self.last_packet = packet
        return packet

    def read(self) -> np.ndarray | None:
        try:
            return cv2.cvtColor(self.capture().image, cv2.COLOR_BGR2GRAY)
        except ReplayError as exc:
            self.last_error = exc
            return None
