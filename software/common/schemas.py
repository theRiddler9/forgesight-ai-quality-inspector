"""Shared ForgeSight data models (Pydantic v2).

Single source of truth for every package (edge runtime, backend, HMI).
Do NOT create local copies. Contract changes: see software/CONTRACT.md.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

DEFECT_CLASS_NAMES = ("burr", "flash", "crack", "scratch")


def utc_now() -> datetime:
    """Timezone-aware UTC now (serialises to '...Z' in JSON mode)."""
    return datetime.now(timezone.utc)


class InspectionDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    RECHECK = "RECHECK"


class DefectType(str, Enum):
    NONE = "none"
    BURR = "burr"
    FLASH = "flash"
    CRACK = "crack"
    SCRATCH = "scratch"
    DIMENSIONAL_ERROR = "dimensional_error"
    MISSING_HOLE = "missing_hole"
    PART_MISALIGNED = "part_misaligned"


class PokaYokeStatus(BaseModel):
    part_present: bool = True
    position_valid: bool = True
    hole_present: bool = True
    size_in_range: bool = True

    @property
    def all_ok(self) -> bool:
        return (
            self.part_present
            and self.position_valid
            and self.hole_present
            and self.size_in_range
        )


class LatencyBreakdown(BaseModel):
    capture_ms: float = Field(..., ge=0.0)
    poka_yoke_ms: float = Field(..., ge=0.0)
    npu_inference_ms: float = Field(..., ge=0.0)
    decision_ms: float = Field(..., ge=0.0)
    total_ms: float = Field(..., ge=0.0)

    @classmethod
    def from_stages(
        cls,
        capture_ms: float,
        poka_yoke_ms: float,
        npu_inference_ms: float,
        decision_ms: float,
    ) -> "LatencyBreakdown":
        """Build a breakdown where total_ms is the sum of the four stages."""
        return cls(
            capture_ms=capture_ms,
            poka_yoke_ms=poka_yoke_ms,
            npu_inference_ms=npu_inference_ms,
            decision_ms=decision_ms,
            total_ms=round(capture_ms + poka_yoke_ms + npu_inference_ms + decision_ms, 3),
        )


class DetectionBox(BaseModel):
    class_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: List[float] = Field(..., min_length=4, max_length=4)  # [x_min, y_min, x_max, y_max]


class InspectionResult(BaseModel):
    inspection_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    result: InspectionDecision
    defect_type: DefectType = DefectType.NONE
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_names: List[str] = Field(default_factory=lambda: list(DEFECT_CLASS_NAMES))
    poka_yoke_status: PokaYokeStatus
    per_stage_latency_ms: LatencyBreakdown
    soc_temp_c: float
    detections: List[DetectionBox] = Field(default_factory=list)
    image_path: Optional[str] = None


# --- Additive contract extension: payload of the `watchdog_alert` WebSocket event ---
class AlertType(str, Enum):
    CAMERA_DISCONNECTED = "camera_disconnected"
    PIPELINE_STALL = "pipeline_stall"
    OVERHEATING = "overheating"


class AlertSeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class WatchdogAlert(BaseModel):
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    timestamp: datetime = Field(default_factory=utc_now)
    value: Optional[float] = None  # measured value: stall ms, SoC temp C, missed frames
