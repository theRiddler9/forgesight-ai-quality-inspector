import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from software.dataset.intake import IntakeError, import_dataset


def image_bytes():
    ok, encoded = cv2.imencode(".png", np.zeros((40, 50, 3), dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def test_directory_intake_dry_run_then_immutable_import(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "part.png").write_bytes(image_bytes())
    target = tmp_path / "intake"
    args = dict(source=source, destination=target, dataset_version="1.0.0",
                profile="metal-plate-v1@1.0.0", source_name="team_capture",
                source_license="team-owned", capture_session="session-1")
    preview = import_dataset(**args, dry_run=True)
    assert preview["image_count"] == 1 and not target.exists()
    report = import_dataset(**args)
    assert report["image_count"] == 1
    manifest = json.loads((target / "manifest.json").read_text())
    item = manifest["entries"][0]
    assert item["review_status"] == "unreviewed"
    assert (target / item["image_path"]).is_file()
    with pytest.raises(IntakeError, match="already exists"):
        import_dataset(**args)


def test_intake_rejects_unknown_license_and_bad_images(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "bad.png").write_bytes(b"bad")
    args = dict(source=source, destination=tmp_path / "out", dataset_version="1.0.0",
                profile="metal-plate-v1@1.0.0", source_name="capture",
                source_license="unknown", capture_session="s")
    with pytest.raises(IntakeError, match="license"):
        import_dataset(**args)
    assert not (tmp_path / "out").exists()
    args["source_license"] = "team-owned"
    with pytest.raises(IntakeError, match="decode"):
        import_dataset(**args)


@pytest.mark.parametrize("name", ["../escape.png", "/absolute.png", "folder/../../bad.png"])
def test_archive_rejects_unsafe_paths(tmp_path, name):
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(name, image_bytes())
    with pytest.raises(IntakeError, match="unsafe"):
        import_dataset(archive, tmp_path / "out", "1.0.0", "metal-plate-v1@1.0.0", "external", "CC BY 4.0", "s")
    assert not (tmp_path / "out").exists()


def test_archive_rejects_symlinks_and_duplicates(tmp_path):
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        info = zipfile.ZipInfo("linked.png")
        info.external_attr = (0o120777 << 16)
        stream.writestr(info, image_bytes())
    with pytest.raises(IntakeError, match="symlink"):
        import_dataset(archive, tmp_path / "out", "1.0.0", "metal-plate-v1@1.0.0", "external", "CC BY 4.0", "s")


def test_archive_import_reports_exact_duplicate(tmp_path):
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("a.png", image_bytes())
        stream.writestr("b.png", image_bytes())
    report = import_dataset(archive, tmp_path / "out", "1.0.0", "metal-plate-v1@1.0.0", "external", "CC BY 4.0", "s")
    assert len(report["duplicate_groups"]) == 1
    assert len(list((tmp_path / "out" / "raw").iterdir())) == 1
