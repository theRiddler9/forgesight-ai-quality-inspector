"""Synthetic part images for mock-camera mode and Poka-Yoke tests (grayscale uint8)."""
from typing import Optional, Tuple

import cv2
import numpy as np

BACKGROUND = 30
PART = 190


def make_synthetic_part(
    width: int = 1280,
    height: int = 800,
    *,
    part_present: bool = True,
    center: Optional[Tuple[float, float]] = None,
    size: Tuple[float, float] = (400.0, 250.0),
    angle_deg: float = 0.0,
    hole: bool = True,
    hole_radius: float = 30.0,
    scratch: bool = False,
    noise_std: float = 2.0,
    seed: int = 0,
) -> np.ndarray:
    """A light rectangular part with a round hole on a dark belt."""
    rng = np.random.default_rng(seed)
    img = np.full((height, width), BACKGROUND, dtype=np.uint8)
    if part_present:
        cx, cy = center or (width / 2.0, height / 2.0)
        box = cv2.boxPoints(((cx, cy), size, angle_deg)).astype(np.int32)
        cv2.fillPoly(img, [box], PART)
        if hole:
            cv2.circle(img, (int(cx), int(cy)), int(hole_radius), BACKGROUND, -1)
        if scratch:  # cosmetic only: the stub engine ignores pixels
            cv2.line(img, (int(cx) - 120, int(cy) + 70), (int(cx) + 100, int(cy) + 85), 120, 2)
    if noise_std > 0:
        img = np.clip(img + rng.normal(0, noise_std, img.shape), 0, 255).astype(np.uint8)
    return img
