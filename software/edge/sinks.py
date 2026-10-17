"""Where finished results/alerts go. JSONL lines use the WebSocket envelope shape."""
import json
import sys
from pathlib import Path
from typing import Protocol

from software.common.schemas import InspectionResult, WatchdogAlert


class ResultSink(Protocol):
    def publish_result(self, result: InspectionResult) -> None: ...
    def publish_alert(self, alert: WatchdogAlert) -> None: ...


class ConsoleSink:
    def publish_result(self, r: InspectionResult) -> None:
        lat = r.per_stage_latency_ms
        print(
            f"{r.result.value:<7} {r.defect_type.value:<17} conf={r.confidence:.3f} "
            f"total={lat.total_ms:6.2f} ms (cap {lat.capture_ms:.1f} | pk {lat.poka_yoke_ms:.1f} | "
            f"npu {lat.npu_inference_ms:.1f} | dec {lat.decision_ms:.1f}) soc={r.soc_temp_c:.1f}C",
            file=sys.stdout,
        )

    def publish_alert(self, a: WatchdogAlert) -> None:
        print(f"ALERT {a.severity.value.upper()} {a.alert_type.value}: {a.message}", file=sys.stdout)


class JsonLinesSink:
    """Appends {"event": ..., "data": ...} lines. The backend can tail and rebroadcast."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event: str, model) -> None:
        line = json.dumps({"event": event, "data": model.model_dump(mode="json")})
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def publish_result(self, result: InspectionResult) -> None:
        self._write("inspection_result", result)

    def publish_alert(self, alert: WatchdogAlert) -> None:
        self._write("watchdog_alert", alert)
