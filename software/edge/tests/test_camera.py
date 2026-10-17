import cv2
import pytest

from software.edge.acquisition.camera import DirectoryCamera, SyntheticCamera, create_camera
from software.edge.acquisition.preprocess import adjust_contrast
from software.edge.acquisition.synthetic import make_synthetic_part
from software.edge.poka_yoke.rules import check_poka_yoke


def test_synthetic_camera_is_deterministic_per_seed():
    a = SyntheticCamera(seed=5, geometry_fault_rate=0.5)
    b = SyntheticCamera(seed=5, geometry_fault_rate=0.5)
    assert (a.read() == b.read()).all()


def test_synthetic_camera_disconnect():
    cam = SyntheticCamera(disconnect_after=2)
    assert cam.read() is not None and cam.read() is not None
    assert cam.read() is None


def test_injected_faults_are_caught_by_poka_yoke():
    cam = SyntheticCamera(seed=1, geometry_fault_rate=1.0)
    for _ in range(25):
        status = check_poka_yoke(cam.read()).status
        assert not status.all_ok, cam.last_fault


def test_directory_camera_cycles_images(tmp_path):
    for i in range(2):
        cv2.imwrite(str(tmp_path / f"p{i}.png"), make_synthetic_part(seed=i))
    cam = create_camera(True, str(tmp_path))
    with cam:
        frames = [cam.read() for _ in range(3)]
    assert all(f is not None and f.ndim == 2 for f in frames)


def test_directory_camera_empty_folder_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        DirectoryCamera(str(tmp_path)).open()


def test_contrast_adjustment_keeps_shape_and_dtype():
    img = make_synthetic_part()
    out = adjust_contrast(img)
    assert out.shape == img.shape and out.dtype == img.dtype
