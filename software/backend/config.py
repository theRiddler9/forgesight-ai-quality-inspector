"""Local backend settings loaded from explicit environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class BackendSettings:
    db_path: Path
    host: str = "127.0.0.1"
    port: int = 8000

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
        return cls(
            db_path=db_path,
            host=os.environ.get("FORGESIGHT_API_HOST", "127.0.0.1"),
            port=int(os.environ.get("FORGESIGHT_API_PORT", "8000")),
        )
