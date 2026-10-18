"""Generate a deterministic ONNX graph for adapter tests, never defect claims."""
from __future__ import annotations

import argparse
from pathlib import Path


def write_fixture_model(destination: str | Path, output_format: str = "yolo11_raw_v1") -> None:
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    if output_format != "yolo11_raw_v1":
        raise ValueError("unsupported adapter fixture format")
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    # One xywh detection at 0.9 confidence in a 64x64 letterboxed image.
    prediction = np.array([[[32.0], [32.0], [20.0], [10.0], [0.9]]], dtype=np.float32)
    graph = helper.make_graph([
        helper.make_node("ReduceMean", ["images"], ["mean"], axes=[0, 1, 2, 3], keepdims=0),
        helper.make_node("Mul", ["mean", "zero"], ["ignored_input"]),
        helper.make_node("Add", ["ignored_input", "constant_prediction"], ["predictions"]),
    ], "forgesight-adapter-test-only", [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 64, 64])],
       [helper.make_tensor_value_info("predictions", TensorProto.FLOAT, [1, 5, 1])],
       [numpy_helper.from_array(np.array(0, dtype=np.float32), name="zero"),
        numpy_helper.from_array(prediction, name="constant_prediction")])
    model = helper.make_model(graph, opset_imports=[helper.make_operatorsetid("", 13)],
                              producer_name="forgesight-adapter-test-only")
    model.ir_version = 9
    onnx.checker.check_model(model)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(model.SerializeToString())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a test-only ONNX graph")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_fixture_model(args.output)
