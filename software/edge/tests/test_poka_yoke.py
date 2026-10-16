import pytest

from software.edge.acquisition.synthetic import make_synthetic_part
from software.edge.poka_yoke.rules import check_poka_yoke


def status(**kw):
    return check_poka_yoke(make_synthetic_part(**kw)).status


def test_good_part_passes_all_checks():
    s = status()
    assert s.all_ok, s


def test_small_pose_jitter_is_tolerated():
    assert status(center=(655, 392), angle_deg=2.0).all_ok


def test_empty_belt_means_no_part():
    s = status(part_present=False)
    assert not s.part_present and not s.all_ok


def test_blank_frame_means_no_part():
    import numpy as np

    s = check_poka_yoke(np.full((800, 1280), 120, dtype=np.uint8)).status
    assert not s.part_present


def test_missing_hole_detected():
    s = status(hole=False)
    assert s.part_present and not s.hole_present and s.size_in_range and s.position_valid


def test_shifted_part_is_misaligned():
    s = status(center=(760, 480))
    assert not s.position_valid and s.hole_present


def test_tilted_part_is_misaligned():
    assert not status(angle_deg=12.0).position_valid


def test_oversize_part_fails_size():
    s = status(size=(460.0, 290.0))
    assert not s.size_in_range and s.position_valid


def test_undersize_part_fails_size():
    assert not status(size=(340.0, 210.0)).size_in_range


def test_oversize_hole_is_not_a_valid_hole():
    assert not status(hole_radius=60.0).hole_present


def test_part_clipped_by_frame_edge_is_misaligned():
    assert not status(center=(1090, 400)).position_valid
