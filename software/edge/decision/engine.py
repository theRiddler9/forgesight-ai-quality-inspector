"""Decision engine: single source of truth for PASS / FAIL / RECHECK.

Rules are documented in software/CONTRACT.md section 2. Pure function: no I/O.
"""
from dataclasses import dataclass
from typing import Sequence

from software.common.schemas import (
    DEFECT_CLASS_NAMES,
    DefectType,
    DetectionBox,
    InspectionDecision,
    PokaYokeStatus,
)
from software.edge.config import DecisionThresholds

NO_DETECTION_PASS_CONFIDENCE = 0.99


@dataclass(frozen=True)
class Decision:
    result: InspectionDecision
    defect_type: DefectType
    confidence: float
    reason: str


def _geometry_defect(status: PokaYokeStatus) -> DefectType:
    # Position first: if the part is misplaced, size/hole measurements are less trustworthy.
    if not status.position_valid:
        return DefectType.PART_MISALIGNED
    if not status.size_in_range:
        return DefectType.DIMENSIONAL_ERROR
    return DefectType.MISSING_HOLE


def decide(
    status: PokaYokeStatus,
    detections: Sequence[DetectionBox],
    thresholds: DecisionThresholds = DecisionThresholds(),
) -> Decision:
    if not status.part_present:
        return Decision(InspectionDecision.RECHECK, DefectType.NONE, 0.0, "no part detected")

    if not status.all_ok:
        defect = _geometry_defect(status)
        return Decision(InspectionDecision.FAIL, defect, 1.0, f"poka-yoke: {defect.value}")

    top = max(detections, key=lambda d: d.confidence, default=None)
    if top is None:
        return Decision(InspectionDecision.PASS, DefectType.NONE, NO_DETECTION_PASS_CONFIDENCE, "clean")

    if top.class_name not in DEFECT_CLASS_NAMES:
        return Decision(
            InspectionDecision.RECHECK, DefectType.NONE, top.confidence, f"unknown class {top.class_name!r}"
        )

    if top.confidence < thresholds.recheck_confidence:
        return Decision(
            InspectionDecision.PASS, DefectType.NONE, round(1.0 - top.confidence, 3), "weak detection ignored"
        )

    defect = DefectType(top.class_name)
    if top.confidence >= thresholds.fail_confidence:
        return Decision(InspectionDecision.FAIL, defect, top.confidence, f"{defect.value} detected")
    return Decision(InspectionDecision.RECHECK, defect, top.confidence, f"possible {defect.value}")
