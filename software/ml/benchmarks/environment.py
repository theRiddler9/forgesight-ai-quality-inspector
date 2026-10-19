"""Host, installed-runtime, and SoC telemetry for benchmark provenance."""

from __future__ import annotations

import platform
from importlib import metadata
from pathlib import Path
from typing import Any

from software.edge.telemetry import UNAVAILABLE_C, make_temp_reader

_DEVICE_MODEL = Path("/proc/device-tree/model")
_RUNTIME_DISTRIBUTIONS = (
    "numpy",
    "opencv-python-headless",
    "onnxruntime",
    "rknn-toolkit-lite2",
    "rknn-toolkit2",
)
_TEMP_READER = make_temp_reader(mock=False)


def read_soc_temperature_c() -> float | None:
    """Read the real Linux SoC thermal zone or return None when unavailable."""
    value = _TEMP_READER()
    return None if value == UNAVAILABLE_C else value


def collect_static_environment() -> dict[str, Any]:
    """Collect host identity and installed optional inference runtime versions."""
    try:
        hardware_model = _DEVICE_MODEL.read_text(encoding="utf-8").strip("\x00\n ") or None
    except OSError:
        hardware_model = None
    packages: dict[str, str | None] = {}
    for distribution in _RUNTIME_DISTRIBUTIONS:
        try:
            packages[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            packages[distribution] = None
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "hardware_model": hardware_model,
        "runtime_packages": packages,
    }
