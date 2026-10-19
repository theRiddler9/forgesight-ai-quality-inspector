from pathlib import Path

import numpy as np
import pytest

from software.inspection.replay import ReplayError, ReplayFrameSource, ScenarioCatalog


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_recorded_frame_has_bgr8_metadata_and_repeatable_pixels():
    catalog = ScenarioCatalog(FIXTURES)
    scenario = catalog.get("clean_part")
    with ReplayFrameSource(FIXTURES / "images", scenario) as source:
        first = source.capture()
        second = source.capture()
    assert first.image.dtype == np.uint8
    assert first.image.ndim == 3 and first.image.shape[2] == 3
    assert first.pixel_format == "BGR8"
    assert first.sequence_number == 0 and second.sequence_number == 1
    assert first.frame_id != second.frame_id
    assert np.array_equal(first.image, second.image)
    assert first.captured_at.tzinfo is not None
    assert first.sha256 == second.sha256


def test_missing_and_invalid_scenarios_are_rejected(tmp_path):
    catalog = ScenarioCatalog(FIXTURES)
    with pytest.raises(ReplayError, match="UNKNOWN_SCENARIO"):
        catalog.get("../clean_part")
    with pytest.raises(ReplayError, match="MISSING_FRAME"):
        with ReplayFrameSource(tmp_path, catalog.get("clean_part")) as source:
            source.capture()
    (tmp_path / "clean.png").write_bytes(b"not an image")
    with pytest.raises(ReplayError, match="INVALID_FRAME"):
        with ReplayFrameSource(tmp_path, catalog.get("clean_part")) as source:
            source.capture()


def test_no_part_is_a_valid_recorded_frame_and_capture_fault_is_typed():
    catalog = ScenarioCatalog(FIXTURES)
    with ReplayFrameSource(FIXTURES / "images", catalog.get("no_part")) as source:
        assert source.capture().image.shape == (800, 1280, 3)
    with pytest.raises(ReplayError, match="CAMERA_UNAVAILABLE"):
        with ReplayFrameSource(FIXTURES / "images", catalog.get("capture_fault")) as source:
            source.capture()
