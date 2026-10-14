"""Inference engine interface. The RKNN engine and the stub both implement it."""
from typing import List, Protocol

import numpy as np

from software.common.schemas import DetectionBox


class InferenceEngine(Protocol):
    name: str

    def infer(self, frame: np.ndarray) -> List[DetectionBox]:
        """Return surface-defect detections for a preprocessed grayscale frame."""
        ...
