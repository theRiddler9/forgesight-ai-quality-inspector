import pytest

from software.ml.evaluation import classification_metrics, threshold_sweep, latency_summary, box_iou, defect_metrics


def test_decision_metrics_and_empty_class_are_explicit():
    samples = [
        {"truth":"heavy_burr", "decision":"FAIL", "predicted_class":"heavy_burr"},
        {"truth":"heavy_burr", "decision":"PASS", "predicted_class":None},
        {"truth":"clean", "decision":"FAIL", "predicted_class":"heavy_burr"},
        {"truth":"clean", "decision":"RECHECK", "predicted_class":None},
    ]
    report = classification_metrics(samples, positive_class="heavy_burr")
    assert report["recall"] == 0.5
    assert report["precision"] == 0.5
    assert report["false_accept_rate"] == 0.5
    assert report["false_reject_rate"] == 0.5
    assert report["recheck_rate"] == 0.25
    assert report["confusion_matrix"]["heavy_burr"]["PASS"] == 1
    assert report["recall_ci_95"] is not None
    empty = classification_metrics([{"truth":"clean","decision":"PASS","predicted_class":None}], "heavy_burr")
    assert empty["recall"] is None


def test_threshold_sweep_rejects_test_data():
    observations = [{"truth":"heavy_burr", "confidence":0.7}, {"truth":"clean", "confidence":0.1}]
    with pytest.raises(ValueError, match="validation"):
        threshold_sweep(observations, [0.6], split="test")
    assert threshold_sweep(observations, [0.6], split="validation")[0]["recall"] == 1


def test_defect_iou_and_latency_summary():
    assert box_iou((0,0,1,1), (0,0,1,1)) == 1
    assert box_iou((0,0,1,1), (2,2,3,3)) == 0
    result = defect_metrics([{"truth_boxes":[("heavy_burr", (0,0,1,1))],
                              "predicted_boxes":[("heavy_burr", (0,0,1,1))]}], "heavy_burr")
    assert result["recall"] == 1 and result["precision"] == 1
    assert latency_summary([10, 20, 30])["p95_ms"] == pytest.approx(29)
    assert latency_summary([])["median_ms"] is None
