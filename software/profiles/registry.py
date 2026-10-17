"""Read-only profile catalog with explicit in-process selection."""
from __future__ import annotations

import json
from pathlib import Path

from software.profiles.models import ComponentProfile


class UnknownProfile(LookupError):
    pass


class ProfileRegistry:
    def __init__(self, catalog_dir: str | Path, default_id: str = "metal-plate-v1", default_version: str = "1.0.0"):
        directory = Path(catalog_dir)
        self._profiles: dict[tuple[str, str], ComponentProfile] = {}
        for path in sorted(directory.glob("*.json")):
            profile = ComponentProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
            key = (profile.profile_id, profile.version)
            if key in self._profiles:
                raise ValueError(f"duplicate component profile: {key}")
            self._profiles[key] = profile
        self._active = self.get(default_id, default_version)

    @property
    def active(self) -> ComponentProfile:
        return self._active

    def get(self, profile_id: str, version: str) -> ComponentProfile:
        try:
            return self._profiles[(profile_id, version)]
        except KeyError as exc:
            raise UnknownProfile(f"unknown component profile {profile_id}@{version}") from exc

    def select(self, profile_id: str, version: str) -> ComponentProfile:
        selected = self.get(profile_id, version)
        self._active = selected
        return selected

    def list_profiles(self) -> list[ComponentProfile]:
        return [self._profiles[key] for key in sorted(self._profiles)]
