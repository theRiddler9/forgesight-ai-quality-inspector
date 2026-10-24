"""Validate exported ONNX tensor metadata against a ForgeSight model contract."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any

from software.ml.model_manifest import ModelArtifactError, ModelManifest, verify_model_artifact
from software.profiles.models import ComponentProfile


class ExportValidationError(ValueError):
    """An ONNX artifact cannot satisfy the registered profile contract."""


def _shape(value: Any, label: str) -> list[int]:
    dimensions: list[int] = []
    for dimension in value.type.tensor_type.shape.dim:
        if dimension.dim_value <= 0 or dimension.dim_param:
            raise ExportValidationError(f"{label} must use static positive dimensions")
        dimensions.append(dimension.dim_value)
    return dimensions


def _value_info(value: Any, label: str) -> dict[str, Any]:
    tensor_type = value.type.tensor_type
    return {
        "name": value.name,
        "dtype": tensor_type.elem_type,
        "shape": _shape(value, label),
    }


def _contains_external_tensors(message: Any, onnx: Any) -> bool:
    """Find external TensorProto data, including tensors in nested subgraphs."""
    if isinstance(message, onnx.TensorProto) and (
        message.data_location == onnx.TensorProto.EXTERNAL or message.external_data
    ):
        return True
    for descriptor, value in message.ListFields():
        if descriptor.type != descriptor.TYPE_MESSAGE:
            continue
        children = value if descriptor.is_repeated else (value,)
        if any(_contains_external_tensors(child, onnx) for child in children):
            return True
    return False


def load_embedded_onnx_graph(artifact_path: str | Path) -> Any:
    """Load one ONNX file without reading or accepting untracked sidecar weights."""
    try:
        import onnx
    except ImportError as exc:
        raise ExportValidationError("ONNX inspection requires software/requirements-onnx.txt") from exc
    path = Path(artifact_path)
    if not path.is_file():
        raise ExportValidationError("ONNX artifact does not exist")
    try:
        graph = onnx.load(str(path), load_external_data=False)
    except Exception as exc:
        raise ExportValidationError(f"invalid ONNX graph: {exc}") from exc
    if _contains_external_tensors(graph, onnx):
        raise ExportValidationError(
            "ONNX external tensor data is unsupported: the manifest hashes only the .onnx file"
        )
    return graph


def inspect_onnx_graph(artifact_path: str | Path) -> dict[str, Any]:
    """Return JSON-safe metadata after ONNX full static shape checking."""
    graph = load_embedded_onnx_graph(artifact_path)
    import onnx
    try:
        onnx.checker.check_model(graph, full_check=True)
    except Exception as exc:
        raise ExportValidationError(f"invalid ONNX graph: {exc}") from exc
    if len(graph.graph.input) != 1 or len(graph.graph.output) != 1:
        raise ExportValidationError("graph must contain exactly one input and one output")
    try:
        inputs = [_value_info(graph.graph.input[0], "input")]
        outputs = [_value_info(graph.graph.output[0], "output")]
    except ExportValidationError:
        raise
    except Exception as exc:
        raise ExportValidationError(f"graph tensors must be typed tensors: {exc}") from exc
    return {
        "inputs": inputs,
        "outputs": outputs,
        "ir_version": graph.ir_version,
        "opset_imports": [opset.version for opset in graph.opset_import],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_onnx_artifact(
    profile: ComponentProfile,
    manifest: ModelManifest,
    model_root: str | Path,
) -> dict[str, Any]:
    """Validate identity and static tensor metadata without executing inference."""
    if manifest.backend != "onnx":
        raise ExportValidationError("manifest backend must be onnx")
    try:
        identity = verify_model_artifact(profile, manifest, model_root)
    except ModelArtifactError as exc:
        raise ExportValidationError(str(exc)) from exc
    root = Path(model_root).resolve()
    artifact = (root / manifest.artifact_path).resolve()
    graph = inspect_onnx_graph(artifact)
    input_info = graph["inputs"][0]
    output_info = graph["outputs"][0]
    expected_input = [1, 3, manifest.input_height, manifest.input_width]
    if input_info["dtype"] != 1 or input_info["shape"] != expected_input:
        raise ExportValidationError("ONNX input must be float32 [1,3,input_height,input_width]")
    output_shape = output_info["shape"]
    expected_channels = 4 + len(manifest.class_map)
    if output_info["dtype"] != 1 or len(output_shape) != 3 or output_shape[:2] != [1, expected_channels]:
        raise ExportValidationError("ONNX output must be float32 [1,4+class_count,N]")
    if not 1 <= output_shape[2] <= 10_000:
        raise ExportValidationError("ONNX candidate count must be between 1 and 10000")
    return {
        "validation": "static_contract_valid",
        "runtime_available": importlib.util.find_spec("onnxruntime") is not None,
        "inference_executed": False,
        "hardware_verified": False,
        "artifact": {
            "filename": artifact.name,
            "size_bytes": artifact.stat().st_size,
            "sha256": _sha256(artifact),
        },
        "profile": {
            "id": profile.profile_id,
            "version": profile.version,
            "fingerprint": profile.fingerprint,
        },
        "model": {
            "id": manifest.model_id,
            "version": manifest.model_version,
            "purpose": manifest.model_purpose,
        },
        "graph": graph,
        "identity": identity,
    }
