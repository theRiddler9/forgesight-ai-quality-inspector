"""Tunable edge-runtime settings. Pixel values assume the OV9281 native 1280x800 frame."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class DecisionThresholds:
    """Placeholders until Riya picks them from the precision-recall curve."""

    fail_confidence: float = 0.80
    recheck_confidence: float = 0.50

    def __post_init__(self) -> None:
        if not (0.0 <= self.recheck_confidence < self.fail_confidence <= 1.0):
            raise ValueError("need 0 <= recheck_confidence < fail_confidence <= 1")


@dataclass(frozen=True)
class PokaYokeConfig:
    min_part_area_px: float = 5000.0
    max_part_area_ratio: float = 0.80  # larger than this share of the frame = blank/bad exposure
    min_contrast_std: float = 8.0  # flat frame (no part, lens covered) -> part not present
    expected_center_px: Tuple[float, float] = (640.0, 400.0)
    center_tolerance_px: float = 40.0
    max_tilt_deg: float = 5.0
    border_margin_px: int = 5  # part touching the frame edge is clipped -> misaligned
    expected_size_px: Tuple[float, float] = (400.0, 250.0)  # (long side, short side)
    size_tolerance_ratio: float = 0.05
    expect_hole: bool = True
    hole_area_px: Tuple[float, float] = (1500.0, 4000.0)


@dataclass(frozen=True)
class EdgeConfig:
    thresholds: DecisionThresholds = field(default_factory=DecisionThresholds)
    poka_yoke: PokaYokeConfig = field(default_factory=PokaYokeConfig)
    contrast_clip_limit: float = 2.0
    latency_budget_ms: float = 100.0
    frame_dir: Optional[Path] = None  # where non-PASS frames are saved (None = don't save)
