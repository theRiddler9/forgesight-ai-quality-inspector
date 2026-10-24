"""Synthetic records exercise comparison logic, never real ONNX/RKNN parity."""

import json
import os

import pytest

from software.ml.parity import compare_captures, main


def capture(backend="onnx", *, confidence=0.8, decision="FAIL", image_hash="a" * 64):
    return {
        "schema_version": "1.0.0", "backend": backend,
        "model_artifact_sha256": ("b" if backend == "onnx" else "c") * 64,
        "profile_fingerprint": "d" * 64, "preprocessing_fingerprint": "e" * 64,
        "comparison_set_id": "synthetic-test-only", "class_map": {"heavy_burr": 0},
        "decoder_contract": "yolo11_raw_v1", "output_shape": [1, 5, 1],
        "frames": [{"image_id": "frame-1", "image_sha256": image_hash,
                    "image_width": 128, "image_height": 80,
                    "decision": decision, "detections": [
                        {"class_name": "heavy_burr", "confidence": confidence,
                         "bbox": [10, 20, 30, 40]},
                    ]}],
    }


def tolerances():
    return {"confidence_abs_max": 0.05, "bbox_abs_px_max": 2.0, "min_iou": 0.8}


def test_matching_outputs_are_numeric_only_not_hardware_approval():
    """A matching fixture record can pass numeric checks without approval claims."""
    result = compare_captures(capture(), capture("rknn", confidence=0.78), tolerances())
    assert result["passed"] is True
    assert result["hardware_verified"] is False
    assert result["approval_assessed"] is False
    assert result["frames"][0]["matched_detections"] == 1


@pytest.mark.parametrize("change", [
    lambda value: value["frames"][0].update(decision="PASS"),
    lambda value: value["frames"][0]["detections"][0].update(confidence=0.6),
    lambda value: value["frames"][0]["detections"][0].update(bbox=[50, 20, 70, 40]),
    lambda value: value["frames"][0].update(detections=[]),
    lambda value: value.update(output_shape=[1, 5, 2]),
])
def test_decision_detection_and_output_mismatches_fail(change):
    """A mismatch in the final decision, box, confidence, count, or shape fails."""
    other = capture("rknn")
    change(other)
    result = compare_captures(capture(), other, tolerances())
    assert result["passed"] is False
    assert result["frames"][0]["reasons"] or result["reasons"]


@pytest.mark.parametrize("change", [
    lambda value: value["frames"][0].update(image_sha256="f" * 64),
    lambda value: value.update(profile_fingerprint="f" * 64),
    lambda value: value.update(preprocessing_fingerprint="f" * 64),
    lambda value: (value.update(class_map={"scratch": 0}),
                   value["frames"][0]["detections"][0].update(class_name="scratch")),
    lambda value: value.update(comparison_set_id="other-set"),
    lambda value: value["frames"][0].update(image_width=256),
])
def test_incompatible_input_identity_is_rejected(change):
    """Comparison cannot proceed with different frames or processing contracts."""
    other = capture("rknn")
    change(other)
    with pytest.raises(ValueError, match="mismatch"):
        compare_captures(capture(), other, tolerances())


@pytest.mark.parametrize("bad", [None, {}, {"confidence_abs_max": -1, "bbox_abs_px_max": 2, "min_iou": 0.8}])
def test_explicit_valid_tolerances_are_required(bad):
    """No parity threshold is silently supplied by the tool."""
    with pytest.raises(ValueError):
        compare_captures(capture(), capture("rknn"), bad)


def test_invalid_output_contract_and_out_of_frame_box_are_rejected():
    """A comparison cannot validate unsupported tensor or pixel coordinates."""
    wrong_shape = capture()
    wrong_shape["output_shape"] = [1, 4, 1]
    with pytest.raises(ValueError, match="output shape"):
        compare_captures(wrong_shape, capture("rknn"), tolerances())
    wrong_box = capture()
    wrong_box["frames"][0]["detections"][0]["bbox"] = [10, 20, 200, 40]
    with pytest.raises(ValueError, match="image bounds"):
        compare_captures(wrong_box, capture("rknn"), tolerances())


@pytest.mark.parametrize("change", [
    lambda value: value["frames"][0].update(image_width=0),
    lambda value: value["frames"][0].update(image_height=-1),
    lambda value: value["frames"][0]["detections"][0].update(confidence=float("nan")),
    lambda value: value["frames"][0]["detections"].extend(
        [value["frames"][0]["detections"][0]] * 256),
    lambda value: value.update(output_shape=[1, 5, 10001]),
])
def test_invalid_or_unbounded_capture_is_rejected(change):
    """Malformed or overly large saved outputs cannot enter the comparison."""
    bad = capture()
    change(bad)
    with pytest.raises(ValueError):
        compare_captures(bad, capture("rknn"), tolerances())


def test_duplicate_image_ids_are_rejected():
    """One capture cannot count the same comparison image twice."""
    bad = capture()
    bad["frames"].append(bad["frames"][0])
    with pytest.raises(ValueError, match="duplicate comparison image ID"):
        compare_captures(bad, capture("rknn"), tolerances())


def test_cli_writes_passed_synthetic_comparison_with_input_hashes(tmp_path):
    """The CLI records the exact saved inputs, without claiming hardware parity."""
    onnx = tmp_path / "onnx.json"
    rknn = tmp_path / "rknn.json"
    limits = tmp_path / "limits.json"
    output = tmp_path / "report.json"
    for path, data in ((onnx, capture()), (rknn, capture("rknn")),
                       (limits, tolerances())):
        path.write_text(json.dumps(data), encoding="utf-8")
    assert main(["--onnx", str(onnx), "--rknn", str(rknn),
                 "--tolerances", str(limits), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["comparison_scope"] == "captured_outputs_only"
    assert report["hardware_verified"] is False
    assert set(report["input_file_sha256"]) == {"onnx", "rknn", "tolerances"}


def test_cli_writes_failed_comparison_and_returns_nonzero(tmp_path):
    """A decision mismatch remains reviewable but makes the CLI fail."""
    onnx = tmp_path / "onnx.json"
    rknn = tmp_path / "rknn.json"
    limits = tmp_path / "limits.json"
    output = tmp_path / "report.json"
    onnx.write_text(json.dumps(capture()), encoding="utf-8")
    rknn.write_text(json.dumps(capture("rknn", decision="PASS")), encoding="utf-8")
    limits.write_text(json.dumps(tolerances()), encoding="utf-8")
    assert main(["--onnx", str(onnx), "--rknn", str(rknn),
                 "--tolerances", str(limits), "--output", str(output)]) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is False


@pytest.mark.parametrize("source_name", ["onnx", "rknn", "tolerances"])
@pytest.mark.parametrize("alias_kind", ["direct", "normalized", "symlink", "hardlink"])
def test_cli_rejects_output_alias_of_any_input_without_writing(
    tmp_path, capsys, source_name, alias_kind,
):
    """Path and existing-file aliases cannot replace captured evidence."""
    sources = {
        "onnx": tmp_path / "onnx.json",
        "rknn": tmp_path / "rknn.json",
        "tolerances": tmp_path / "tolerances.json",
    }
    for name, data in (("onnx", capture()), ("rknn", capture("rknn")),
                       ("tolerances", tolerances())):
        sources[name].write_text(json.dumps(data), encoding="utf-8")
    before = {name: path.read_bytes() for name, path in sources.items()}
    selected = sources[source_name]
    if alias_kind == "direct":
        output = selected
    elif alias_kind == "normalized":
        intermediate = tmp_path / "intermediate"
        intermediate.mkdir()
        output = intermediate / ".." / "." / selected.name
    elif alias_kind == "symlink":
        output = tmp_path / "report-alias.json"
        try:
            output.symlink_to(selected)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation unavailable on this host")
    else:
        output = tmp_path / "report-hardlink.json"
        try:
            os.link(selected, output)
        except (OSError, NotImplementedError):
            pytest.skip("hardlink creation unavailable on this host")

    with pytest.raises(SystemExit) as exc:
        main(["--onnx", str(sources["onnx"]), "--rknn", str(sources["rknn"]),
              "--tolerances", str(sources["tolerances"]), "--output", str(output)])
    assert exc.value.code == 2
    assert "--output must not overwrite a parity input" in capsys.readouterr().err
    assert {name: path.read_bytes() for name, path in sources.items()} == before
