"""Frame sources. All return grayscale uint8 frames, or None when a frame was lost."""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from software.edge.acquisition.synthetic import make_synthetic_part

log = logging.getLogger(__name__)

FAULTS = ("no_part", "no_hole", "shifted", "oversize", "tilted")


class FrameSource(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> Optional[np.ndarray]: ...

    @abstractmethod
    def release(self) -> None: ...

    def __enter__(self) -> "FrameSource":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


class SyntheticCamera(FrameSource):
    """No-hardware camera. Randomly injects geometry faults; can simulate a disconnect."""

    def __init__(
        self,
        seed: int = 0,
        geometry_fault_rate: float = 0.0,
        disconnect_after: Optional[int] = None,
        width: int = 1280,
        height: int = 800,
    ):
        self._rng = np.random.default_rng(seed)
        self.geometry_fault_rate = geometry_fault_rate
        self.disconnect_after = disconnect_after
        self.width, self.height = width, height
        self.frames_read = 0
        self.last_fault: Optional[str] = None

    def open(self) -> None:
        self.frames_read = 0

    def release(self) -> None:
        pass

    def read(self) -> Optional[np.ndarray]:
        if self.disconnect_after is not None and self.frames_read >= self.disconnect_after:
            return None
        self.frames_read += 1
        fault = None
        if self._rng.random() < self.geometry_fault_rate:
            fault = str(self._rng.choice(FAULTS))
        self.last_fault = fault
        kwargs = {"width": self.width, "height": self.height, "seed": self.frames_read}
        if fault == "no_part":
            kwargs["part_present"] = False
        elif fault == "no_hole":
            kwargs["hole"] = False
        elif fault == "shifted":
            kwargs["center"] = (self.width / 2 + 120, self.height / 2 + 80)
        elif fault == "oversize":
            kwargs["size"] = (460.0, 290.0)
        elif fault == "tilted":
            kwargs["angle_deg"] = 12.0
        return make_synthetic_part(**kwargs)


class DirectoryCamera(FrameSource):
    """Cycles through a folder of still images (e.g. saved defect photos)."""

    EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}

    def __init__(self, directory: str):
        self.directory = Path(directory)
        self._files: List[Path] = []
        self._i = 0

    def open(self) -> None:
        self._files = sorted(p for p in self.directory.iterdir() if p.suffix.lower() in self.EXTENSIONS)
        if not self._files:
            raise FileNotFoundError(f"no images found in {self.directory}")
        self._i = 0

    def release(self) -> None:
        pass

    def read(self) -> Optional[np.ndarray]:
        img = cv2.imread(str(self._files[self._i % len(self._files)]), cv2.IMREAD_GRAYSCALE)
        self._i += 1
        return img


class OpenCVCamera(FrameSource):
    """USB/UVC camera (OV9281 / IMX335), webcam, or video file via cv2.VideoCapture."""

    def __init__(self, source=0, lock_exposure: bool = True, exposure: float = 100.0, gain: float = 0.0):
        self.source = source
        self.lock_exposure = lock_exposure
        self.exposure, self.gain = exposure, gain
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open camera source {self.source!r}")
        if self.lock_exposure:
            # V4L2: AUTO_EXPOSURE=1 means manual mode. Drivers may reject props: log, don't crash.
            ok = [
                self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1),
                self._cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure),
                self._cap.set(cv2.CAP_PROP_GAIN, self.gain),
            ]
            if not all(ok):
                log.warning("camera driver rejected some exposure/gain settings: %s", ok)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def read(self) -> Optional[np.ndarray]:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame


def create_camera(mock: bool, source: Optional[str] = None, **synthetic_kwargs) -> FrameSource:
    """--mock-camera: synthetic (no source), image folder, webcam index, or video file."""
    if not mock:
        return OpenCVCamera(int(source) if source and source.isdigit() else (source or 0))
    if source is None:
        return SyntheticCamera(**synthetic_kwargs)
    if Path(source).is_dir():
        return DirectoryCamera(source)
    return OpenCVCamera(int(source) if source.isdigit() else source, lock_exposure=False)
