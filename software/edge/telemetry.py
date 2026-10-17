"""SoC temperature reader. Real: Linux sysfs thermal zone. Mock: plausible random value."""
import logging
import random
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

SYSFS_THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")  # millidegrees C
UNAVAILABLE_C = -1.0


def make_temp_reader(mock: bool, seed: int = 0) -> Callable[[], float]:
    if mock:
        rng = random.Random(seed)
        return lambda: round(rng.uniform(49.0, 56.5), 1)

    warned = False

    def read() -> float:
        nonlocal warned
        try:
            return round(int(SYSFS_THERMAL.read_text().strip()) / 1000.0, 1)
        except (OSError, ValueError):
            if not warned:
                log.warning("SoC temperature unavailable (%s); reporting %.1f", SYSFS_THERMAL, UNAVAILABLE_C)
                warned = True
            return UNAVAILABLE_C

    return read
