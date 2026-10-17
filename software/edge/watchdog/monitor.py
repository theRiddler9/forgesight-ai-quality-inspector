"""Watchdog: pipeline stall (> 200 ms), camera loss, SoC over-temperature.

`check()` is pure polling logic driven by an injectable clock (unit-testable).
`start()` runs it on a background thread for the real runtime.
"""
import logging
import threading
import time
from collections import deque
from typing import Callable, Deque, List, Optional

from software.common.schemas import AlertSeverity, AlertType, WatchdogAlert

log = logging.getLogger(__name__)


class Watchdog:
    def __init__(
        self,
        stall_timeout_ms: float = 200.0,
        soc_limit_c: float = 65.0,
        max_missed_frames: int = 3,
        clock: Callable[[], float] = time.monotonic,
        recovery_temp_c: Optional[float] = None,
    ):
        self.stall_timeout_s = stall_timeout_ms / 1000.0
        self.soc_limit_c = soc_limit_c
        self.recovery_temp_c = recovery_temp_c if recovery_temp_c is not None else soc_limit_c - 2.0
        if self.recovery_temp_c >= self.soc_limit_c:
            raise ValueError("recovery_temp_c must be below soc_limit_c")
        self.max_missed_frames = max_missed_frames
        self._clock = clock
        self._lock = threading.Lock()
        self._listeners: List[Callable[[WatchdogAlert], None]] = []
        self.alerts: Deque[WatchdogAlert] = deque(maxlen=100)
        self._started_at: Optional[float] = None
        self._stall_reported = False
        self._missed = 0
        self._camera_reported = False
        self._hot = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def subscribe(self, callback: Callable[[WatchdogAlert], None]) -> None:
        self._listeners.append(callback)

    # --- inputs from the pipeline
    def begin_inspection(self) -> None:
        with self._lock:
            self._started_at = self._clock()
            self._stall_reported = False

    def end_inspection(self) -> None:
        with self._lock:
            self._started_at = None

    def report_frame(self, ok: bool) -> None:
        alert = None
        with self._lock:
            if ok:
                self._missed, self._camera_reported = 0, False
                return
            self._missed += 1
            if self._missed >= self.max_missed_frames and not self._camera_reported:
                self._camera_reported = True
                alert = WatchdogAlert(
                    alert_type=AlertType.CAMERA_DISCONNECTED,
                    severity=AlertSeverity.CRITICAL,
                    message=f"{self._missed} consecutive frames lost",
                    value=float(self._missed),
                )
        if alert:
            self._emit(alert)

    def report_temperature(self, soc_c: float) -> None:
        alert = None
        with self._lock:
            if self._hot and soc_c <= self.recovery_temp_c:
                self._hot = False
            elif not self._hot and soc_c > self.soc_limit_c:
                self._hot = True
                alert = WatchdogAlert(
                    alert_type=AlertType.OVERHEATING,
                    severity=AlertSeverity.WARNING,
                    message=f"SoC {soc_c:.1f} C exceeds {self.soc_limit_c:.0f} C",
                    value=soc_c,
                )
        if alert:
            self._emit(alert)

    # --- polling
    def check(self) -> List[WatchdogAlert]:
        """Detect a stalled inspection. Each stall is reported once."""
        alert = None
        with self._lock:
            if self._started_at is not None and not self._stall_reported:
                elapsed = self._clock() - self._started_at
                if elapsed > self.stall_timeout_s:
                    self._stall_reported = True
                    alert = WatchdogAlert(
                        alert_type=AlertType.PIPELINE_STALL,
                        severity=AlertSeverity.CRITICAL,
                        message=f"inspection running {elapsed * 1000:.0f} ms",
                        value=round(elapsed * 1000, 1),
                    )
        if alert:
            self._emit(alert)
            return [alert]
        return []

    def _emit(self, alert: WatchdogAlert) -> None:
        log.error("WATCHDOG %s: %s", alert.alert_type.value, alert.message)
        self.alerts.append(alert)
        for cb in self._listeners:
            try:
                cb(alert)
            except Exception:
                log.exception("watchdog alert subscriber failed")

    # --- background thread
    def start(self, poll_ms: float = 20.0) -> None:
        self._stop.clear()

        def loop() -> None:
            while not self._stop.wait(poll_ms / 1000.0):
                self.check()

        self._thread = threading.Thread(target=loop, name="watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
