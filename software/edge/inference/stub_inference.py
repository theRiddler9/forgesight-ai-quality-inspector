"""Contract-compliant mock inference, so backend/HMI/edge can run without the NPU.

Two entry points:
  * get_stub_inspection_result()  -> full InspectionResult-shaped dict (for backend/HMI dev)
  * StubInferenceEngine.infer()   -> detections only (plugs into the edge pipeline)
"""
import random
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import uuid4

import numpy as np

from software.common.schemas import DEFECT_CLASS_NAMES, DetectionBox


def _roll(rng: random.Random, defect_rate: float) -> Tuple[str, str, float, List[dict]]:
    """Returns (result, defect, confidence, detections) with the blueprint's distribution."""
    roll = rng.random()
    if roll < (1.0 - defect_rate):
        return "PASS", "none", round(rng.uniform(0.96, 0.99), 3), []
    if roll < (1.0 - defect_rate + 0.05):
        defect = rng.choice(["burr", "scratch"])
        conf = round(rng.uniform(0.70, 0.79), 3)
        return "RECHECK", defect, conf, [
            {"class_name": defect, "confidence": conf, "bbox": [120.0, 140.0, 160.0, 185.0]}
        ]
    defect = rng.choice(list(DEFECT_CLASS_NAMES))
    conf = round(rng.uniform(0.85, 0.98), 3)
    return "FAIL", defect, conf, [
        {"class_name": defect, "confidence": conf, "bbox": [200.0, 150.0, 260.0, 210.0]}
    ]


def get_stub_inspection_result(
    simulated_defect_rate: float = 0.15, rng: Optional[random.Random] = None
) -> dict:
    """Realistic mock result. KPIs: total latency <= 100 ms, SoC temperature < 65 C."""
    rng = rng or random.Random()
    capture_ms = round(rng.uniform(6.0, 10.0), 2)
    poka_yoke_ms = round(rng.uniform(10.0, 16.0), 2)
    npu_ms = round(rng.uniform(22.0, 32.0), 2)
    decision_ms = round(rng.uniform(1.5, 3.5), 2)
    total_ms = round(capture_ms + poka_yoke_ms + npu_ms + decision_ms, 2)
    result, defect, conf, detections = _roll(rng, simulated_defect_rate)

    return {
        "inspection_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "result": result,
        "defect_type": defect,
        "confidence": conf,
        "class_names": list(DEFECT_CLASS_NAMES),
        "poka_yoke_status": {
            "part_present": True,
            "position_valid": True,
            "hole_present": True,
            "size_in_range": True,
        },
        "per_stage_latency_ms": {
            "capture_ms": capture_ms,
            "poka_yoke_ms": poka_yoke_ms,
            "npu_inference_ms": npu_ms,
            "decision_ms": decision_ms,
            "total_ms": total_ms,
        },
        "soc_temp_c": round(rng.uniform(49.0, 56.5), 1),
        "detections": detections,
        "image_path": f"/data/frames/mock_frame_{int(time.time())}.jpg",
    }


class StubInferenceEngine:
    """Random detections with the same distribution as get_stub_inspection_result()."""

    name = "stub"

    def __init__(self, simulated_defect_rate: float = 0.15, seed: Optional[int] = None):
        self.simulated_defect_rate = simulated_defect_rate
        self._rng = random.Random(seed)

    def infer(self, frame: np.ndarray) -> List[DetectionBox]:
        _, _, _, detections = _roll(self._rng, self.simulated_defect_rate)
        return [DetectionBox(**d) for d in detections]


if __name__ == "__main__":
    import json

    print(json.dumps(get_stub_inspection_result(), indent=2))
