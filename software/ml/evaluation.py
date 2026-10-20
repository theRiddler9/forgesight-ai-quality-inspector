"""Framework-independent metrics. Callers supply reviewed real or synthetic data."""
from __future__ import annotations

import math
import argparse
import json
from pathlib import Path
import statistics
from collections import Counter, defaultdict


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return max(0, center - radius), min(1, center + radius)


def classification_metrics(samples: list[dict], positive_class: str = "heavy_burr") -> dict:
    matrix: dict[str, Counter] = defaultdict(Counter)
    for item in samples:
        if item["decision"] not in {"PASS", "FAIL", "RECHECK"}:
            raise ValueError("decision must be PASS, FAIL, or RECHECK")
        matrix[item["truth"]][item["decision"]] += 1
    positives = sum(item["truth"] == positive_class for item in samples)
    tp = sum(item["truth"] == positive_class and item["decision"] == "FAIL" and item.get("predicted_class") == positive_class for item in samples)
    predicted_positive = sum(item["decision"] == "FAIL" and item.get("predicted_class") == positive_class for item in samples)
    clean = sum(item["truth"] == "clean" for item in samples)
    false_accept = sum(item["truth"] == positive_class and item["decision"] == "PASS" for item in samples)
    false_reject = sum(item["truth"] == "clean" and item["decision"] == "FAIL" for item in samples)
    recheck = sum(item["decision"] == "RECHECK" for item in samples)
    return {
        "sample_count": len(samples), "positive_class": positive_class,
        "true_positive": tp, "positive_count": positives,
        "precision": _rate(tp, predicted_positive),
        "recall": _rate(tp, positives),
        "heavy_burr_false_negative_rate": _rate(positives - tp, positives),
        "false_accept_rate": _rate(false_accept, positives),
        "false_reject_rate": _rate(false_reject, clean),
        "recheck_rate": _rate(recheck, len(samples)),
        "recall_ci_95": wilson_interval(tp, positives),
        "confusion_matrix": {truth: {decision: count for decision, count in sorted(row.items())}
                             for truth, row in sorted(matrix.items())},
    }


def per_class_metrics(samples: list[dict]) -> dict[str, dict]:
    return {label: classification_metrics(samples, label) for label in sorted({item["truth"] for item in samples if item["truth"] != "clean"})}


def threshold_sweep(observations: list[dict], thresholds: list[float], split: str,
                    positive_class: str = "heavy_burr") -> list[dict]:
    if split != "validation":
        raise ValueError("threshold selection may use validation data only")
    if any(not 0 <= threshold <= 1 for threshold in thresholds):
        raise ValueError("thresholds must be between zero and one")
    if any(not 0 <= item["confidence"] <= 1 for item in observations):
        raise ValueError("confidence must be between zero and one")
    return [{"threshold": threshold, **classification_metrics([
        {"truth": item["truth"], "decision": "FAIL" if item["confidence"] >= threshold else "PASS",
         "predicted_class": positive_class if item["confidence"] >= threshold else None}
        for item in observations], positive_class)} for threshold in thresholds]


def box_iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    for x1, y1, x2, y2 in (left, right):
        if x1 >= x2 or y1 >= y2:
            raise ValueError("boxes must have positive area")
    intersection = max(0, min(left[2], right[2]) - max(left[0], right[0])) * max(0, min(left[3], right[3]) - max(left[1], right[1]))
    area_left = (left[2] - left[0]) * (left[3] - left[1])
    area_right = (right[2] - right[0]) * (right[3] - right[1])
    return intersection / (area_left + area_right - intersection)


def defect_metrics(images: list[dict], positive_class: str, iou_threshold: float = 0.5) -> dict:
    if not 0 < iou_threshold <= 1:
        raise ValueError("IoU threshold must be in (0, 1]")
    true_count = prediction_count = matched = 0
    for image in images:
        truth = [box for label, box in image["truth_boxes"] if label == positive_class]
        predictions = [box for label, box in image["predicted_boxes"] if label == positive_class]
        true_count += len(truth)
        prediction_count += len(predictions)
        candidates = sorted(((box_iou(t, p), ti, pi) for ti, t in enumerate(truth)
                             for pi, p in enumerate(predictions)), reverse=True)
        used_truth, used_predictions = set(), set()
        for overlap, ti, pi in candidates:
            if overlap >= iou_threshold and ti not in used_truth and pi not in used_predictions:
                used_truth.add(ti)
                used_predictions.add(pi)
                matched += 1
    return {"class": positive_class, "truth_count": true_count, "prediction_count": prediction_count,
            "matched": matched, "recall": _rate(matched, true_count),
            "precision": _rate(matched, prediction_count), "iou_threshold": iou_threshold}


def latency_summary(values_ms: list[float]) -> dict:
    if any(value < 0 or not math.isfinite(value) for value in values_ms):
        raise ValueError("latency must be finite and nonnegative")
    if not values_ms:
        return {"count": 0, "median_ms": None, "p95_ms": None, "max_ms": None}
    values = sorted(values_ms)
    location = 0.95 * (len(values) - 1)
    low = math.floor(location)
    high = math.ceil(location)
    p95 = values[low] + (values[high] - values[low]) * (location - low)
    return {"count": len(values), "median_ms": statistics.median(values), "p95_ms": p95, "max_ms": values[-1]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute metrics from reviewed prediction records; never runs a model")
    parser.add_argument("predictions", type=Path, help="JSON list of truth, decision, predicted_class, and optional latency_ms")
    parser.add_argument("--positive-class", default="heavy_burr")
    parser.add_argument("--split", choices=["validation", "test"], required=True)
    parser.add_argument("--thresholds", nargs="*", type=float, help="confidence sweep, validation split only")
    args = parser.parse_args()
    records = json.loads(args.predictions.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        parser.error("predictions must be a JSON list")
    if any(item.get("split") != args.split or item.get("review_status") != "reviewed" for item in records):
        parser.error("every prediction must be reviewed and belong to the selected split")
    result = {"split": args.split,
              "metrics": classification_metrics(records, args.positive_class),
              "per_class": per_class_metrics(records),
              "latency": latency_summary([item["latency_ms"] for item in records if "latency_ms" in item])}
    if args.thresholds is not None:
        result["threshold_sweep"] = threshold_sweep(records, args.thresholds, args.split, args.positive_class)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
