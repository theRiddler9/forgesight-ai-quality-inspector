"""Run the edge pipeline.

  python -m software.edge.main --mock-hardware --mock-camera --use-stub-engine --count 20

The real GPIO driver and RKNN engine are not implemented yet, so those three flags are
required for now. `--mock-camera` is optional (without it a real USB camera is used).
"""
import argparse
import logging
import statistics
import time
from pathlib import Path
from typing import List, Optional

from software.edge.acquisition.camera import create_camera
from software.edge.config import EdgeConfig
from software.edge.inference.stub_inference import StubInferenceEngine
from software.edge.io_control.gpio import MockGPIOController
from software.edge.pipeline import InspectionPipeline
from software.edge.sinks import ConsoleSink, JsonLinesSink
from software.edge.telemetry import make_temp_reader
from software.edge.watchdog.monitor import Watchdog


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ForgeSight edge inspection runtime")
    p.add_argument("--mock-hardware", action="store_true", help="mock GPIO + SoC temperature")
    p.add_argument("--mock-camera", action="store_true", help="synthetic / folder / webcam / video source")
    p.add_argument("--use-stub-engine", action="store_true", help="fake NPU detections")
    p.add_argument("--camera-source", default=None, help="folder, webcam index or video file")
    p.add_argument("--count", type=int, default=10, help="inspections to run (0 = forever)")
    p.add_argument("--interval-ms", type=float, default=200.0, help="simulated time between triggers")
    p.add_argument("--defect-rate", type=float, default=0.15, help="stub engine defect rate")
    p.add_argument("--geometry-fault-rate", type=float, default=0.1, help="synthetic camera fault rate")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--jsonl", default=None, help="append events to this JSONL file")
    p.add_argument("--frames-dir", default=None, help="save non-PASS frames here")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = build_parser()
    a = p.parse_args(argv)
    if not a.mock_hardware:
        p.error("real GPIO driver not implemented yet (needs KiCad pinout): use --mock-hardware")
    if not a.use_stub_engine:
        p.error("RKNN engine not implemented yet: use --use-stub-engine")
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    synthetic = {"seed": a.seed, "geometry_fault_rate": a.geometry_fault_rate} if (a.mock_camera and not a.camera_source) else {}
    camera = create_camera(a.mock_camera, a.camera_source, **synthetic)
    sinks = [ConsoleSink()] + ([JsonLinesSink(a.jsonl)] if a.jsonl else [])
    config = EdgeConfig(frame_dir=Path(a.frames_dir) if a.frames_dir else None)
    watchdog = Watchdog()
    gpio = MockGPIOController()
    pipeline = InspectionPipeline(
        camera, StubInferenceEngine(a.defect_rate, a.seed), gpio, watchdog,
        make_temp_reader(True, a.seed), sinks, config,
    )

    totals: List[float] = []
    counts = {"PASS": 0, "FAIL": 0, "RECHECK": 0}
    watchdog.start()
    try:
        with camera:
            n = 0
            while a.count == 0 or n < a.count:
                time.sleep(a.interval_ms / 1000.0)
                n += 1
                r = pipeline.run_once()
                if r:
                    totals.append(r.per_stage_latency_ms.total_ms)
                    counts[r.result.value] += 1
    except KeyboardInterrupt:
        pass
    finally:
        watchdog.stop()
        gpio.close()

    if totals:
        over = sum(t > config.latency_budget_ms for t in totals)
        print(
            f"\n{len(totals)} inspections {counts} | latency mean {statistics.mean(totals):.2f} ms, "
            f"max {max(totals):.2f} ms, over {config.latency_budget_ms:.0f} ms budget: {over}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
