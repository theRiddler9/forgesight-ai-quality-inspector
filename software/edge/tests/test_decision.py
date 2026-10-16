import pytest

from software.common.schemas import DefectType as D
from software.common.schemas import DetectionBox, InspectionDecision as R, PokaYokeStatus
from software.edge.config import DecisionThresholds
from software.edge.decision.engine import decide

OK = PokaYokeStatus()


def det(name, conf):
    return DetectionBox(class_name=name, confidence=conf, bbox=[0, 0, 10, 10])


def test_clean_part_passes():
    d = decide(OK, [])
    assert (d.result, d.defect_type) == (R.PASS, D.NONE) and d.confidence == 0.99


def test_no_part_is_recheck_not_pass():
    d = decide(PokaYokeStatus(part_present=False), [])
    assert (d.result, d.confidence) == (R.RECHECK, 0.0)


@pytest.mark.parametrize(
    "status,expected",
    [
        (PokaYokeStatus(hole_present=False), D.MISSING_HOLE),
        (PokaYokeStatus(size_in_range=False), D.DIMENSIONAL_ERROR),
        (PokaYokeStatus(position_valid=False), D.PART_MISALIGNED),
        (PokaYokeStatus(position_valid=False, hole_present=False), D.PART_MISALIGNED),
    ],
)
def test_geometry_failures_fail_with_priority(status, expected):
    d = decide(status, [det("crack", 0.99)])  # geometry wins over AI
    assert (d.result, d.defect_type, d.confidence) == (R.FAIL, expected, 1.0)


def test_high_confidence_detection_fails():
    d = decide(OK, [det("crack", 0.9)])
    assert (d.result, d.defect_type) == (R.FAIL, D.CRACK)


def test_mid_confidence_detection_is_recheck():
    d = decide(OK, [det("burr", 0.7)])
    assert (d.result, d.defect_type) == (R.RECHECK, D.BURR)


def test_weak_detection_is_ignored():
    d = decide(OK, [det("scratch", 0.3)])
    assert (d.result, d.confidence) == (R.PASS, 0.7)


def test_highest_confidence_detection_wins():
    d = decide(OK, [det("scratch", 0.55), det("flash", 0.92)])
    assert d.defect_type == D.FLASH


def test_boundaries_are_inclusive():
    t = DecisionThresholds(fail_confidence=0.8, recheck_confidence=0.5)
    assert decide(OK, [det("burr", 0.8)], t).result == R.FAIL
    assert decide(OK, [det("burr", 0.5)], t).result == R.RECHECK


def test_unknown_class_is_never_trusted():
    d = decide(OK, [det("dent", 0.95)])
    assert (d.result, d.defect_type) == (R.RECHECK, D.NONE)


def test_unknown_class_is_rechecked_even_at_low_confidence():
    d = decide(OK, [det("dent", 0.2)])
    assert (d.result, d.defect_type) == (R.RECHECK, D.NONE)


def test_invalid_thresholds_rejected():
    with pytest.raises(ValueError):
        DecisionThresholds(fail_confidence=0.4, recheck_confidence=0.6)
