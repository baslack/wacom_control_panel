"""On-disk profile storage under the XDG config directory.

Layout::

    ~/.config/wacom-control-panel/
        state.json              # {"active": "<profile name>"}
        profiles/<name>.json    # one Profile per file

Phase 2 (autostart + replug watcher) builds on these same paths.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .profile import Profile

APP_DIR_NAME = "wacom-control-panel"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w.-]+", "_", name.strip()).strip("_")
    return slug or "profile"


class ProfileStore:
    """Loads/saves named profiles and tracks the active one."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or config_dir()
        self.profiles_dir = self.root / "profiles"
        self.state_path = self.root / "state.json"

    # ---- paths ------------------------------------------------------------
    def _path_for(self, name: str) -> Path:
        return self.profiles_dir / f"{_slugify(name)}.json"

    # ---- listing ----------------------------------------------------------
    def list_profiles(self) -> list[Profile]:
        if not self.profiles_dir.is_dir():
            return []
        out: list[Profile] = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                out.append(Profile.load(path))
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return out

    def names(self) -> list[str]:
        return [p.name for p in self.list_profiles()]

    # ---- CRUD -------------------------------------------------------------
    def save(self, profile: Profile) -> None:
        profile.save(self._path_for(profile.name))

    def load(self, name: str) -> Profile | None:
        path = self._path_for(name)
        return Profile.load(path) if path.exists() else None

    def delete(self, name: str) -> None:
        self._path_for(name).unlink(missing_ok=True)
        if self.get_active() == name:
            remaining = self.names()
            self.set_active(remaining[0] if remaining else None)

    def rename(self, old: str, new: str) -> None:
        profile = self.load(old)
        if profile is None:
            return
        profile.name = new
        self.save(profile)
        if old != new:
            self.delete(old)
        if self.get_active() == old:
            self.set_active(new)

    # ---- active selection -------------------------------------------------
    def get_active(self) -> str | None:
        try:
            return json.loads(self.state_path.read_text()).get("active")
        except (json.JSONDecodeError, OSError):
            return None

    def set_active(self, name: str | None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"active": name}, indent=2) + "\n")

    def active_profile(self) -> Profile | None:
        name = self.get_active()
        return self.load(name) if name else None

    # ---- convenience ------------------------------------------------------
    def ensure_default(self) -> Profile:
        """Guarantee at least one profile exists and is active; return the active one."""
        existing = self.active_profile()
        if existing is not None:
            return existing
        profiles = self.list_profiles()
        if profiles:
            self.set_active(profiles[0].name)
            return profiles[0]
        default = Profile(name="Default")
        self.save(default)
        self.set_active(default.name)
        return default
