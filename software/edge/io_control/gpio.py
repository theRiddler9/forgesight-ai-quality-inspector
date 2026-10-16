"""Indicator outputs (tower light, buzzer, LED ring PWM).

Only the mock controller exists for now. The real Orange Pi 5 driver is blocked on the
KiCad pin allocation (electrical/pinout/) and must drive every pin through the PC817
opto-isolation bank. Signalling table: software/CONTRACT.md section 4 (confirm with Kartikay).
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import List

from software.common.schemas import InspectionDecision

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutputState:
    green: bool = False
    red: bool = False
    amber: bool = False
    buzzer: bool = False
    ring_pwm_pct: float = 100.0


SIGNALS = {
    InspectionDecision.PASS: dict(green=True),
    InspectionDecision.FAIL: dict(red=True, buzzer=True),
    InspectionDecision.RECHECK: dict(amber=True),
}
FAULT_SIGNAL = dict(amber=True, buzzer=True)


class GPIOController(ABC):
    @abstractmethod
    def _apply(self, state: OutputState) -> None: ...

    def __init__(self) -> None:
        self.state = OutputState()

    def show_result(self, result: InspectionDecision) -> OutputState:
        return self._set(**SIGNALS[result])

    def show_fault(self) -> OutputState:
        return self._set(**FAULT_SIGNAL)

    def all_off(self) -> OutputState:
        return self._set()

    def set_ring_brightness(self, pct: float) -> OutputState:
        """Brightness persists across result changes; clamped to 0-100."""
        self.state = replace(self.state, ring_pwm_pct=max(0.0, min(100.0, float(pct))))
        self._apply(self.state)
        return self.state

    def _set(self, **lights) -> OutputState:
        # Exactly one result is shown at a time: previous lights/buzzer are cleared.
        self.state = OutputState(ring_pwm_pct=self.state.ring_pwm_pct, **lights)
        self._apply(self.state)
        return self.state

    def close(self) -> None:
        self.all_off()


class MockGPIOController(GPIOController):
    """--mock-hardware: logs pin states and keeps a history for tests."""

    def __init__(self) -> None:
        super().__init__()
        self.history: List[OutputState] = []

    def _apply(self, state: OutputState) -> None:
        self.history.append(state)
        log.info(
            "GPIO G=%d R=%d A=%d BUZ=%d RING=%.0f%%",
            state.green, state.red, state.amber, state.buzzer, state.ring_pwm_pct,
        )
