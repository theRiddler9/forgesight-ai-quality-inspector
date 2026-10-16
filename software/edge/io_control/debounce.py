import time
from typing import Callable


class Debouncer:
    """Lock-out debounce for the conveyor trigger (AGENTS.md: 10-20 ms).

    The first edge is accepted; any edge within `window_ms` of the last accepted one is
    treated as contact chatter and ignored.
    """

    def __init__(self, window_ms: float = 15.0, clock: Callable[[], float] = time.monotonic):
        self.window_s = window_ms / 1000.0
        self._clock = clock
        self._last = None

    def accept(self) -> bool:
        now = self._clock()
        if self._last is not None and (now - self._last) < self.window_s:
            return False
        self._last = now
        return True
