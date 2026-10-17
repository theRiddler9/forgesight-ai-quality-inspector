"""Deterministic OpenCV geometry checks: presence, position, hole, size.

Runs before the NPU so simple defects never consume NPU time. Pure function of
(frame, config): easy to test with synthetic images.
"""
from dataclasses import dataclass, field
from typing import Dict

import cv2
import numpy as np

from software.common.schemas import PokaYokeStatus
from software.edge.config import PokaYokeConfig


@dataclass
class PokaYokeReport:
    status: PokaYokeStatus
    measurements: Dict[str, float] = field(default_factory=dict)


def _not_present(measurements: Dict[str, float]) -> PokaYokeReport:
    # Checks that cannot be verified without a part are reported as failed.
    status = PokaYokeStatus(
        part_present=False, position_valid=False, hole_present=False, size_in_range=False
    )
    return PokaYokeReport(status, measurements)


def check_poka_yoke(gray: np.ndarray, cfg: PokaYokeConfig = PokaYokeConfig()) -> PokaYokeReport:
    h, w = gray.shape[:2]
    m: Dict[str, float] = {"contrast_std": float(gray.std())}
    if m["contrast_std"] < cfg.min_contrast_std:
        return _not_present(m)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return _not_present(m)
    outer = [i for i, hh in enumerate(hierarchy[0]) if hh[3] == -1]
    part_idx = max(outer, key=lambda i: cv2.contourArea(contours[i]))
    part = contours[part_idx]
    area = float(cv2.contourArea(part))
    m["part_area_px"] = area
    if area < cfg.min_part_area_px or area / float(w * h) > cfg.max_part_area_ratio:
        return _not_present(m)

    # --- position: centroid offset, tilt, and not clipped by the frame edge
    mom = cv2.moments(part)
    cx, cy = mom["m10"] / mom["m00"], mom["m01"] / mom["m00"]
    offset = float(np.hypot(cx - cfg.expected_center_px[0], cy - cfg.expected_center_px[1]))
    (_, _), (rw, rh), angle = cv2.minAreaRect(part)
    tilt = abs(angle) % 90.0
    tilt = min(tilt, 90.0 - tilt)
    x, y, bw, bh = cv2.boundingRect(part)
    mg = cfg.border_margin_px
    clipped = x <= mg or y <= mg or x + bw >= w - mg or y + bh >= h - mg
    m.update(center_offset_px=offset, tilt_deg=float(tilt), clipped=float(clipped))
    position_valid = offset <= cfg.center_tolerance_px and tilt <= cfg.max_tilt_deg and not clipped

    # --- size: min-area-rect sides vs expected (rotation independent)
    long_side, short_side = max(rw, rh), min(rw, rh)
    m.update(long_side_px=float(long_side), short_side_px=float(short_side))
    tol = cfg.size_tolerance_ratio
    size_in_range = (
        abs(long_side - cfg.expected_size_px[0]) <= tol * cfg.expected_size_px[0]
        and abs(short_side - cfg.expected_size_px[1]) <= tol * cfg.expected_size_px[1]
    )

    # --- hole: inner contours of the part whose area is in range
    hole_areas = [
        float(cv2.contourArea(contours[i]))
        for i, hh in enumerate(hierarchy[0])
        if hh[3] == part_idx
    ]
    lo, hi = cfg.hole_area_px
    holes_ok = [a for a in hole_areas if lo <= a <= hi]
    m["holes_found"] = float(len(holes_ok))
    hole_present = (len(holes_ok) >= 1) if cfg.expect_hole else True

    return PokaYokeReport(
        PokaYokeStatus(
            part_present=True,
            position_valid=position_valid,
            hole_present=hole_present,
            size_in_range=size_in_range,
        ),
        m,
    )
