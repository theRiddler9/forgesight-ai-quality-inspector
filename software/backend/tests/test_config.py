import pytest

from software.backend.config import BackendSettings


def test_backend_settings_apply_local_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGESIGHT_DB_PATH", str(tmp_path / "demo.sqlite3"))
    monkeypatch.setenv("FORGESIGHT_FIXTURE_DIR", str(tmp_path / "fixtures"))
    monkeypatch.setenv("FORGESIGHT_API_HOST", "127.0.0.1")
    monkeypatch.setenv("FORGESIGHT_API_PORT", "8123")
    settings = BackendSettings.from_environment()
    assert settings.db_path == tmp_path / "demo.sqlite3"
    assert settings.fixture_dir == tmp_path / "fixtures"
    assert (settings.host, settings.port) == ("127.0.0.1", 8123)


def test_backend_settings_reject_invalid_port(monkeypatch):
    monkeypatch.setenv("FORGESIGHT_API_PORT", "0")
    with pytest.raises(ValueError, match="FORGESIGHT_API_PORT"):
        BackendSettings.from_environment()


def test_backend_launcher_uses_validated_binding(monkeypatch):
    from software.backend import __main__ as launcher

    observed = {}
    monkeypatch.setenv("FORGESIGHT_API_HOST", "127.0.0.1")
    monkeypatch.setenv("FORGESIGHT_API_PORT", "8123")
    monkeypatch.setattr(launcher.uvicorn, "run", lambda app, **kwargs: observed.update(app=app, **kwargs))
    launcher.main()
    assert observed == {"app": "software.backend.app:app", "host": "127.0.0.1", "port": 8123}
