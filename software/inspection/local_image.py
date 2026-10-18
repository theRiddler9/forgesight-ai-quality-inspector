"""One bounded local/uploaded BGR image through the existing grayscale geometry pipeline."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import cv2
import numpy as np

from software.edge.acquisition.camera import FrameSource
from software.inspection.replay import FramePacket, ReplayError
from software.profiles.models import ImageSpec

MAX_IMAGE_BYTES = 8 * 1024 * 1024


class LocalImageFrameSource(FrameSource):
    def __init__(self, raw: bytes, expected: ImageSpec, source_name: str = "local-image"):
        self.raw, self.expected, self.source_name = raw, expected, source_name
        self.last_packet: FramePacket | None = None
        self.inference_frame: np.ndarray | None = None

    def open(self) -> None:
        self.last_packet = None
        self.inference_frame = None

    def release(self) -> None:
        self.inference_frame = None

    def read(self) -> np.ndarray:
        if not self.raw or len(self.raw) > MAX_IMAGE_BYTES:
            raise ReplayError("INVALID_FRAME", "image is empty or exceeds the 8 MiB limit")
        image = cv2.imdecode(np.frombuffer(self.raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.ndim != 3 or image.shape[2] != 3:
            raise ReplayError("INVALID_FRAME", "cannot decode BGR image")
        height, width = image.shape[:2]
        if (width, height, self.expected.pixel_format) != (self.expected.width, self.expected.height, "BGR8"):
            raise ReplayError("FRAME_FORMAT_MISMATCH", "image dimensions or format differ from profile")
        digest = hashlib.sha256(self.raw).hexdigest()
        self.inference_frame = image
        self.last_packet = FramePacket(str(uuid4()), datetime.now(timezone.utc), self.source_name, 0,
                                       width, height, "BGR8", image, f"local-image:sha256:{digest}", digest)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
