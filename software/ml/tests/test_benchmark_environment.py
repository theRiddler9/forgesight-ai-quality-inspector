"""Tests for best-effort host and thermal provenance collection."""

from software.ml.benchmarks import environment


def test_temperature_sentinel_is_recorded_as_unavailable(monkeypatch):
    """The missing-sensor sentinel is represented as unavailable telemetry."""
    monkeypatch.setattr(environment, "_TEMP_READER", lambda: -1.0)
    assert environment.read_soc_temperature_c() is None


def test_temperature_value_is_preserved(monkeypatch):
    """A readable SoC temperature is preserved without scaling or substitution."""
    monkeypatch.setattr(environment, "_TEMP_READER", lambda: 54.2)
    assert environment.read_soc_temperature_c() == 54.2


def test_static_environment_captures_platform_runtime_and_optional_fields(monkeypatch, tmp_path):
    """Host identity and installed runtime versions are included in provenance."""
    model_file = tmp_path / "model"
    model_file.write_text("Board\u0000\n", encoding="utf-8")
    monkeypatch.setattr(environment, "_DEVICE_MODEL", model_file)
    monkeypatch.setattr(environment.platform, "python_version", lambda: "3.13.0")
    monkeypatch.setattr(environment.platform, "platform", lambda: "test-platform")
    monkeypatch.setattr(environment.platform, "machine", lambda: "test-machine")
    monkeypatch.setattr(environment.platform, "processor", lambda: "")

    def version(distribution):
        """Return controlled package versions for the environment collector."""
        if distribution == "numpy":
            return "2.0.0"
        raise environment.metadata.PackageNotFoundError(distribution)

    monkeypatch.setattr(environment.metadata, "version", version)
    result = environment.collect_static_environment()

    assert result == {
        "python_version": "3.13.0",
        "platform": "test-platform",
        "machine": "test-machine",
        "processor": None,
        "hardware_model": "Board",
        "runtime_packages": {
            "numpy": "2.0.0",
            "opencv-python-headless": None,
            "onnxruntime": None,
            "rknn-toolkit-lite2": None,
            "rknn-toolkit2": None,
        },
    }


def test_static_environment_tolerates_unreadable_device_model(monkeypatch, tmp_path):
    """An absent device-tree model remains null rather than a board claim."""
    monkeypatch.setattr(environment, "_DEVICE_MODEL", tmp_path / "missing")
    result = environment.collect_static_environment()
    assert result["hardware_model"] is None
