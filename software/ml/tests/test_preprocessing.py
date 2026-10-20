import cv2
import numpy as np
import pytest

from software.ml.preprocessing import PreprocessError, preprocess_image
from software.profiles.models import ImageSpec, PreprocessingSpec, RegionOfInterest


def config(width=100, height=50, roi=None, rotation=0):
    return (ImageSpec(width=width, height=height, pixel_format="BGR8"),
            roi or RegionOfInterest(x=0, y=0, width=1, height=1),
            PreprocessingSpec(contrast_clip_limit=2, rotation_deg=rotation,
                              model_width=200, model_height=200, normalization="zero_one"))


def test_letterbox_preserves_aspect_and_box_round_trip():
    image = np.zeros((50, 100, 3), dtype=np.uint8)
    image[:, :, 2] = 255
    transform = preprocess_image(image, *config())
    assert transform.tensor.shape == (200, 200, 3)
    assert transform.tensor.dtype == np.float32
    assert transform.tensor[50, 0, 0] == 1  # BGR red -> RGB red
    assert transform.pad_top == 50
    box = (0.1, 0.2, 0.3, 0.4)
    mapped = transform.box_to_model(box)
    assert transform.box_to_original(mapped) == pytest.approx(box)


def test_rotation_roi_and_edge_box_round_trip():
    image = np.zeros((50, 100, 3), dtype=np.uint8)
    roi = RegionOfInterest(x=0.25, y=0, width=0.5, height=1)
    transform = preprocess_image(image, *config(roi=roi, rotation=90))
    assert transform.cropped_size == (50, 50)
    box = (0.25, 0.0, 0.5, 1.0)
    assert transform.box_to_original(transform.box_to_model(box)) == pytest.approx(box)


def test_invalid_pixels_dimensions_and_boxes_fail():
    image_spec, roi, preprocessing = config()
    with pytest.raises(PreprocessError, match="dimensions"):
        preprocess_image(np.zeros((40, 100, 3), dtype=np.uint8), image_spec, roi, preprocessing)
    with pytest.raises(PreprocessError, match="decode"):
        preprocess_image(b"bad", image_spec, roi, preprocessing)
    constrained_roi = RegionOfInterest(x=0.25, y=0, width=0.5, height=1)
    transform = preprocess_image(np.zeros((50, 100, 3), dtype=np.uint8), image_spec, constrained_roi, preprocessing)
    with pytest.raises(PreprocessError, match="ROI"):
        transform.box_to_model((0.0, 0.0, 0.1, 0.1))
