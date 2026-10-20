"""Generate a deterministic ONNX graph for adapter tests, never defect claims."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def write_fixture_model(destination: str | Path, *, confidence: float = 0.9,
                        output_channels: int = 5, input_height: int = 64,
                        boxes: list[tuple[float, float, float, float, float]] | None = None) -> None:
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    if not 0 <= confidence <= 1 or output_channels < 5 or input_height < 32:
        raise ValueError("invalid adapter fixture parameters")
    boxes = boxes or [(32.0, 32.0, 20.0, 10.0, confidence)]
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    # One xywh detection at 0.9 confidence in a 64x64 letterboxed image.
    prediction = np.array([list(box) + [0.0] * (output_channels - 5) for box in boxes],
                          dtype=np.float32).T[None]
    graph = helper.make_graph([
        helper.make_node("ReduceMean", ["images"], ["mean"], axes=[0, 1, 2, 3], keepdims=0),
        helper.make_node("Mul", ["mean", "zero"], ["ignored_input"]),
        helper.make_node("Add", ["ignored_input", "constant_prediction"], ["predictions"]),
    ], "forgesight-adapter-test-only", [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, input_height, 64])],
       [helper.make_tensor_value_info("predictions", TensorProto.FLOAT, [1, output_channels, len(boxes)])],
       [numpy_helper.from_array(np.array(0, dtype=np.float32), name="zero"),
        numpy_helper.from_array(prediction, name="constant_prediction")])
    model = helper.make_model(graph, opset_imports=[helper.make_operatorsetid("", 13)],
                              producer_name="forgesight-adapter-test-only")
    model.ir_version = 9
    onnx.checker.check_model(model)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(model.SerializeToString())


def write_fixture_bundle(destination: str | Path) -> None:
    """Create an isolated, provisional profile/model bundle for integration tests."""
    from software.ml.model_manifest import ModelManifest
    from software.profiles.models import ComponentProfile
    from software.profiles.registry import ProfileRegistry

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    catalog = destination / "catalog"
    catalog.mkdir()
    model_root = destination / "models"
    model_root.mkdir()
    artifact = model_root / "adapter-test.onnx"
    write_fixture_model(artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    default = ProfileRegistry(Path(__file__).resolve().parents[1] / "profiles" / "catalog").active
    (catalog / "default.json").write_text(default.model_dump_json(indent=2), encoding="utf-8")
    profile_data = default.model_dump(mode="json")
    profile_data["version"] = "9.0.0"
    profile_data["preprocessing"].update(model_width=64, model_height=64)
    profile_data["detector"].update(backend="onnx", model_id="adapter-test-constant", model_version="0.0.1",
                                    artifact_path=artifact.name, artifact_sha256=digest,
                                    compatible_profiles=["metal-plate-v1@9.0.0"])
    profile = ComponentProfile.model_validate(profile_data)
    (catalog / "adapter-test.json").write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    manifest = ModelManifest(
        schema_version="1.0.0", model_id=profile.detector.model_id,
        model_version=profile.detector.model_version, backend="onnx",
        compatible_profile="metal-plate-v1@9.0.0", profile_fingerprint=profile.fingerprint,
        artifact_path=artifact.name, artifact_sha256=digest, input_width=64, input_height=64,
        pixel_format="RGB_FLOAT32", preprocessing_fingerprint=profile.preprocessing_fingerprint,
        class_map={"burr": 0}, fail_confidence=0.8, recheck_confidence=0.5,
        output_format="yolo11_raw_v1", model_purpose="adapter_test_fixture",
    )
    (destination / "model-manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a test-only ONNX graph")
    parser.add_argument("output", type=Path)
    parser.add_argument("--bundle", action="store_true", help="create a complete test-only profile/model bundle")
    args = parser.parse_args()
    if args.bundle:
        write_fixture_bundle(args.output)
    else:
        write_fixture_model(args.output)
