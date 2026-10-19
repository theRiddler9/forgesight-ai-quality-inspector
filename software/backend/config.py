"""Local backend settings loaded from explicit environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = PROJECT_ROOT / "software" / "fixtures"


@dataclass(frozen=True)
class BackendSettings:
    db_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    fixture_dir: Path = DEFAULT_FIXTURES

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("FORGESIGHT_API_PORT must be between 1 and 65535")
        if not self.host:
            raise ValueError("FORGESIGHT_API_HOST must not be empty")

    @classmethod
    def from_environment(cls) -> "BackendSettings":
        configured_path = Path(
            os.environ.get("FORGESIGHT_DB_PATH", "data/audit.sqlite3")
        )
        db_path = (
            configured_path
            if configured_path.is_absolute()
            else PROJECT_ROOT / configured_path
        )
        configured_fixtures = Path(os.environ.get("FORGESIGHT_FIXTURE_DIR", str(DEFAULT_FIXTURES)))
        fixture_dir = configured_fixtures if configured_fixtures.is_absolute() else PROJECT_ROOT / configured_fixtures
        return cls(
            db_path=db_path,
            host=os.environ.get("FORGESIGHT_API_HOST", "127.0.0.1"),
            port=int(os.environ.get("FORGESIGHT_API_PORT", "8000")),
            fixture_dir=fixture_dir,
        )
