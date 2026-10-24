"""Compare captured ONNX and RKNN detections without claiming runtime authenticity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictInt, model_validator

from software.ml.benchmarks.runner import write_report


class DetectionRecord(BaseModel):
    """One decoded detection in original-image pixel coordinates."""

    model_config = ConfigDict(extra="forbid")
    class_name: str = Field(min_length=1)
    confidence: FiniteFloat = Field(ge=0, le=1)
    bbox: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]

    @model_validator(mode="after")
    def positive_box(self):
        """Reject inverted or negative original-image coordinates."""
        x1, y1, x2, y2 = self.bbox
        if x1 < 0 or y1 < 0 or x1 >= x2 or y1 >= y2:
            raise ValueError("detection box must have positive area and nonnegative origin")
        return self


class FrameRecord(BaseModel):
    """A decision and decoded detections for one hashed comparison frame."""

    model_config = ConfigDict(extra="forbid")
    image_id: str = Field(min_length=1)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_width: StrictInt = Field(gt=0)
    image_height: StrictInt = Field(gt=0)
    decision: Literal["PASS", "FAIL", "RECHECK"]
    detections: list[DetectionRecord] = Field(max_length=256)

    @model_validator(mode="after")
    def boxes_within_image(self):
        """Keep original-coordinate detections within the captured frame."""
        if any(box.bbox[2] > self.image_width or box.bbox[3] > self.image_height
               for box in self.detections):
            raise ValueError("detection box exceeds image bounds")
        return self


class CaptureRecord(BaseModel):
    """Self-declared runtime output whose identity must agree across captures."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0.0"]
    backend: Literal["onnx", "rknn"]
    model_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    preprocessing_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    comparison_set_id: str = Field(min_length=1)
    class_map: dict[str, StrictInt] = Field(min_length=1)
    decoder_contract: Literal["yolo11_raw_v1"]
    output_shape: list[StrictInt] = Field(min_length=1)
    frames: list[FrameRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def internal_consistency(self):
        """Require unique frames, contiguous classes, and positive tensor shape."""
        if sorted(self.class_map.values()) != list(range(len(self.class_map))):
            raise ValueError("class IDs must be contiguous from zero")
        if (len(self.output_shape) != 3 or self.output_shape[0] != 1
                or self.output_shape[1] != 4 + len(self.class_map)
                or not 1 <= self.output_shape[2] <= 10000):
            raise ValueError("unsupported yolo11_raw_v1 output shape")
        if len({frame.image_id for frame in self.frames}) != len(self.frames):
            raise ValueError("duplicate comparison image ID")
        if any(box.class_name not in self.class_map for frame in self.frames for box in frame.detections):
            raise ValueError("detection class missing from class map")
        return self


class ParityTolerances(BaseModel):
    """Explicit numerical limits supplied by the model-validation owner."""

    model_config = ConfigDict(extra="forbid")
    confidence_abs_max: FiniteFloat = Field(ge=0, le=1)
    bbox_abs_px_max: FiniteFloat = Field(ge=0)
    min_iou: FiniteFloat = Field(gt=0, le=1)


def _iou(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Compute intersection over union for two positive-area pixel boxes."""
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    if intersection == 0:
        return 0.0
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    return intersection / (left_area + right_area - intersection)


def _matching_count(left: list[DetectionRecord], right: list[DetectionRecord], limits: ParityTolerances) -> int:
    """Find a maximum one-to-one matching among detections within all limits."""
    neighbors = [
        [index for index, candidate in enumerate(right)
         if box.class_name == candidate.class_name
         and abs(box.confidence - candidate.confidence) <= limits.confidence_abs_max
         and all(abs(a - b) <= limits.bbox_abs_px_max for a, b in zip(box.bbox, candidate.bbox))
         and _iou(box.bbox, candidate.bbox) >= limits.min_iou]
        for box in left
    ]
    assigned: dict[int, int] = {}

    def assign(left_index: int, visited: set[int]) -> bool:
        for right_index in neighbors[left_index]:
            if right_index in visited:
                continue
            visited.add(right_index)
            if right_index not in assigned or assign(assigned[right_index], visited):
                assigned[right_index] = left_index
                return True
        return False

    return sum(assign(index, set()) for index in range(len(left)))


def compare_captures(onnx_data: dict, rknn_data: dict, tolerance_data: dict) -> dict:
    """Compare matched frame outputs and decisions using caller-supplied limits."""
    onnx = CaptureRecord.model_validate(onnx_data)
    rknn = CaptureRecord.model_validate(rknn_data)
    limits = ParityTolerances.model_validate(tolerance_data)
    if onnx.backend != "onnx" or rknn.backend != "rknn":
        raise ValueError("capture backends must be onnx and rknn respectively")
    for field in ("comparison_set_id", "profile_fingerprint", "preprocessing_fingerprint",
                  "class_map", "decoder_contract"):
        if getattr(onnx, field) != getattr(rknn, field):
            raise ValueError(f"{field} mismatch between captures")
    onnx_frames = {frame.image_id: frame for frame in onnx.frames}
    rknn_frames = {frame.image_id: frame for frame in rknn.frames}
    if onnx_frames.keys() != rknn_frames.keys():
        raise ValueError("comparison frame IDs mismatch")
    if any(frame.image_sha256 != rknn_frames[image_id].image_sha256
           for image_id, frame in onnx_frames.items()):
        raise ValueError("comparison frame hashes mismatch")
    if any((frame.image_width, frame.image_height) !=
           (rknn_frames[image_id].image_width, rknn_frames[image_id].image_height)
           for image_id, frame in onnx_frames.items()):
        raise ValueError("comparison frame dimensions mismatch")

    reasons = [] if onnx.output_shape == rknn.output_shape else ["normalized output shape mismatch"]
    frames = []
    for image_id in sorted(onnx_frames):
        left, right = onnx_frames[image_id], rknn_frames[image_id]
        matched = _matching_count(left.detections, right.detections, limits)
        frame_reasons = []
        if left.decision != right.decision:
            frame_reasons.append("inspection decision mismatch")
        if matched != len(left.detections) or matched != len(right.detections):
            frame_reasons.append("detection count, class, confidence, or box mismatch")
        frames.append({"image_id": image_id, "image_sha256": left.image_sha256,
                       "onnx_decision": left.decision, "rknn_decision": right.decision,
                       "matched_detections": matched, "onnx_detection_count": len(left.detections),
                       "rknn_detection_count": len(right.detections),
                       "passed": not frame_reasons, "reasons": frame_reasons})
    return {
        "schema_version": "1.0.0", "comparison_scope": "captured_outputs_only",
        "hardware_verified": False, "approval_assessed": False,
        "comparison_set_id": onnx.comparison_set_id,
        "profile_fingerprint": onnx.profile_fingerprint,
        "preprocessing_fingerprint": onnx.preprocessing_fingerprint,
        "onnx_artifact_sha256": onnx.model_artifact_sha256,
        "rknn_artifact_sha256": rknn.model_artifact_sha256,
        "tolerances": limits.model_dump(), "frame_count": len(frames),
        "passed": not reasons and all(frame["passed"] for frame in frames),
        "reasons": reasons, "frames": frames,
    }


def main(argv: list[str] | None = None) -> int:
    """Compare saved outputs, publish diagnostics, and fail on any mismatch."""
    parser = argparse.ArgumentParser(description="Compare captured ONNX and RKNN outputs")
    parser.add_argument("--onnx", required=True, type=Path)
    parser.add_argument("--rknn", required=True, type=Path)
    parser.add_argument("--tolerances", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        inputs = (args.onnx, args.rknn, args.tolerances)
        output = args.output.resolve()
        if any(output == source.resolve() or
               (args.output.exists() and args.output.samefile(source)) for source in inputs):
            raise ValueError("--output must not overwrite a parity input")
        sources = [path.read_bytes() for path in inputs]
        result = compare_captures(*(json.loads(raw) for raw in sources))
        result["input_file_sha256"] = {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in zip(("onnx", "rknn", "tolerances"), sources)
        }
        write_report(result, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"Comparison {'passed' if result['passed'] else 'failed'}: {args.output}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
