"""Deterministic decode, crop, rotation, letterbox, and box transforms."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from software.profiles.models import ImageSpec, PreprocessingSpec, RegionOfInterest


class PreprocessError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedImage:
    tensor: np.ndarray  # RGB HWC, float32; no detector prediction
    original_size: tuple[int, int]
    crop: tuple[int, int, int, int]
    cropped_size: tuple[int, int]
    rotation_deg: int
    scale: float
    pad_left: int
    pad_top: int
    resized_size: tuple[int, int]

    def _rotate(self, x: float, y: float) -> tuple[float, float]:
        width, height = self.cropped_size
        if self.rotation_deg == 90:
            return height - y, x
        if self.rotation_deg == 180:
            return width - x, height - y
        if self.rotation_deg == 270:
            return y, width - x
        return x, y

    def _unrotate(self, x: float, y: float) -> tuple[float, float]:
        width, height = self.cropped_size
        if self.rotation_deg == 90:
            return y, height - x
        if self.rotation_deg == 180:
            return width - x, height - y
        if self.rotation_deg == 270:
            return width - y, x
        return x, y

    def box_to_model(self, xywh_normalized: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x, y, w, h = xywh_normalized
        width, height = self.original_size
        left, top, right, bottom = self.crop
        if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x + w <= 1 and y + h <= 1):
            raise PreprocessError("invalid original box")
        corners = [(x * width, y * height), ((x + w) * width, (y + h) * height)]
        if corners[0][0] < left or corners[0][1] < top or corners[1][0] > right or corners[1][1] > bottom:
            raise PreprocessError("box extends outside ROI")
        rotated = [self._rotate(px - left, py - top) for px, py in corners]
        xs = [point[0] * self.scale + self.pad_left for point in rotated]
        ys = [point[1] * self.scale + self.pad_top for point in rotated]
        return min(xs), min(ys), max(xs), max(ys)

    def box_to_original(self, xyxy_model: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = xyxy_model
        max_x = self.pad_left + self.resized_size[0]
        max_y = self.pad_top + self.resized_size[1]
        if not (self.pad_left <= x1 < x2 <= max_x and self.pad_top <= y1 < y2 <= max_y):
            raise PreprocessError("model box extends outside image content")
        points = [self._unrotate((x - self.pad_left) / self.scale, (y - self.pad_top) / self.scale)
                  for x, y in ((x1, y1), (x2, y2))]
        left, top, _, _ = self.crop
        width, height = self.original_size
        xs = [(p[0] + left) / width for p in points]
        ys = [(p[1] + top) / height for p in points]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def preprocess_image(image_or_bytes: np.ndarray | bytes, image_spec: ImageSpec, roi: RegionOfInterest,
                     settings: PreprocessingSpec) -> PreparedImage:
    if isinstance(image_or_bytes, bytes):
        image = cv2.imdecode(np.frombuffer(image_or_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    else:
        image = image_or_bytes
    if image is None or image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise PreprocessError("cannot decode BGR8 image")
    height, width = image.shape[:2]
    if (width, height) != (image_spec.width, image_spec.height):
        raise PreprocessError("image dimensions do not match profile")
    left = round(roi.x * width)
    top = round(roi.y * height)
    right = round((roi.x + roi.width) * width)
    bottom = round((roi.y + roi.height) * height)
    if left >= right or top >= bottom:
        raise PreprocessError("ROI has no pixels")
    cropped = image[top:bottom, left:right]
    rotation = settings.rotation_deg
    if rotation == 90:
        cropped = cv2.rotate(cropped, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        cropped = cv2.rotate(cropped, cv2.ROTATE_180)
    elif rotation == 270:
        cropped = cv2.rotate(cropped, cv2.ROTATE_90_COUNTERCLOCKWISE)
    rotated_height, rotated_width = cropped.shape[:2]
    target_width = settings.model_width or image_spec.width
    target_height = settings.model_height or image_spec.height
    scale = min(target_width / rotated_width, target_height / rotated_height)
    resized_width = min(target_width, round(rotated_width * scale))
    resized_height = min(target_height, round(rotated_height * scale))
    pad_left = (target_width - resized_width) // 2
    pad_top = (target_height - resized_height) // 2
    rgb = cv2.cvtColor(cv2.resize(cropped, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
    tensor = np.zeros((target_height, target_width, 3), dtype=np.float32)
    tensor[pad_top:pad_top + resized_height, pad_left:pad_left + resized_width] = rgb.astype(np.float32)
    if settings.normalization == "zero_one":
        tensor /= 255.0
    return PreparedImage(tensor, (width, height), (left, top, right, bottom),
                         (right - left, bottom - top), rotation, scale, pad_left, pad_top,
                         (resized_width, resized_height))
