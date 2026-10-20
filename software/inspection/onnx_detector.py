"""CPU ONNX adapter for one explicit Ultralytics raw detection output contract."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from software.common.schemas import DetectionBox
from software.inspection.detectors import DetectorOutput, DetectorUnavailable
from software.ml.model_manifest import ModelManifest, verify_model_artifact
from software.ml.preprocessing import preprocess_image
from software.profiles.models import ComponentProfile


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return overlap / (area_a + area_b - overlap) if overlap else 0.0


class OnnxDetector:
    def __init__(self, profile: ComponentProfile, manifest: ModelManifest, model_root: str | Path):
        if manifest.backend != "onnx" or manifest.output_format != "yolo11_raw_v1":
            raise DetectorUnavailable("unsupported ONNX output contract")
        try:
            verify_model_artifact(profile, manifest, model_root)
            import onnxruntime as ort
            artifact = (Path(model_root).resolve() / manifest.artifact_path).resolve()
            self.session = ort.InferenceSession(str(artifact), providers=["CPUExecutionProvider"])
        except Exception as exc:  # ONNX Runtime raises provider-specific Exception subclasses.
            raise DetectorUnavailable(f"ONNX model unavailable: {exc}") from exc
        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        expected_shape = [1, 3, manifest.input_height, manifest.input_width]
        if len(inputs) != 1 or inputs[0].type != "tensor(float)" or inputs[0].shape != expected_shape:
            raise DetectorUnavailable("ONNX input shape or type incompatible with manifest")
        if len(outputs) != 1 or outputs[0].type != "tensor(float)":
            raise DetectorUnavailable("ONNX output count or type unsupported")
        self.input_name = inputs[0].name
        self.output_name = outputs[0].name
        self.profile = profile
        self.manifest = manifest
        self.class_names = [name for name, _ in sorted(manifest.class_map.items(), key=lambda pair: pair[1])]

    def detect(self, frame: np.ndarray) -> DetectorOutput:
        started = time.perf_counter()
        try:
            prepared = preprocess_image(frame, self.profile.image, self.profile.roi, self.profile.preprocessing)
            tensor = np.ascontiguousarray(prepared.tensor.transpose(2, 0, 1)[None], dtype=np.float32)
            raw = self.session.run([self.output_name], {self.input_name: tensor})[0]
            if (not isinstance(raw, np.ndarray) or raw.dtype != np.float32 or raw.ndim != 3
                    or raw.shape[0] != 1 or raw.shape[1] != 4 + len(self.class_names)
                    or not 1 <= raw.shape[2] <= 10000 or not np.isfinite(raw).all()):
                raise DetectorUnavailable("unsupported or invalid ONNX prediction shape")
            candidates = []
            for column in raw[0].T:
                cx, cy, width, height = map(float, column[:4])
                scores = column[4:]
                if np.any(scores < 0) or np.any(scores > 1):
                    raise DetectorUnavailable("ONNX class scores outside [0, 1]")
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id])
                if confidence < self.profile.thresholds.recheck_confidence:
                    continue
                if width <= 0 or height <= 0:
                    raise DetectorUnavailable("ONNX box has invalid dimensions")
                xywh = prepared.box_to_original((cx - width / 2, cy - height / 2,
                                                  cx + width / 2, cy + height / 2))
                x, y, w, h = xywh
                box = (x * frame.shape[1], y * frame.shape[0], (x + w) * frame.shape[1], (y + h) * frame.shape[0])
                candidates.append((confidence, class_id, box))
            detections = []
            for confidence, class_id, box in sorted(candidates, key=lambda item: item[0], reverse=True):
                if any(existing.class_name == self.class_names[class_id] and _iou(box, tuple(existing.bbox)) > 0.5
                       for existing in detections):
                    continue
                detections.append(DetectionBox(class_name=self.class_names[class_id],
                                               confidence=confidence, bbox=list(box)))
            return DetectorOutput(tuple(detections), "onnx", self.manifest.model_id,
                                  self.manifest.model_version, round((time.perf_counter() - started) * 1000, 3),
                                  uncertain=bool(detections and detections[0].confidence < self.profile.thresholds.fail_confidence),
                                  simulated=False)
        except Exception as exc:  # Runtime/provider failures must never reach PASS.
            raise DetectorUnavailable(f"ONNX inference failed: {exc}") from exc

    def infer(self, frame: np.ndarray) -> list[DetectionBox]:
        return list(self.detect(frame).detections)
