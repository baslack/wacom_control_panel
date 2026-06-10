"""Named pressure-curve presets, persisted under the XDG config directory.

A preset is a name mapped to four Bézier control values ``[x1, y1, x2, y2]`` (0–100, the
xsetwacom ``PressureCurve`` format). A few built-ins are always present and cannot be deleted;
user presets live in ``pressure_presets.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .store import config_dir

#: Always-available presets (cannot be deleted or overwritten on disk).
BUILTINS: dict[str, list[int]] = {
    "Soft": [0, 30, 70, 100],
    "Linear": [0, 0, 100, 100],
    "Firm": [30, 0, 100, 70],
}


class PressurePresetStore:
    """Loads/saves named pressure-curve presets (built-ins + user presets)."""

    def __init__(self, root: Path | None = None) -> None:
        self.path = (root or config_dir()) / "pressure_presets.json"

    # ---- user presets on disk --------------------------------------------
    def _user(self) -> dict[str, list[int]]:
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        out: dict[str, list[int]] = {}
        for name, pts in data.items():
            if isinstance(pts, list) and len(pts) == 4:
                out[str(name)] = [int(p) for p in pts]
        return out

    def _write_user(self, presets: dict[str, list[int]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(presets, indent=2) + "\n")

    # ---- combined view ---------------------------------------------------
    def names(self) -> list[str]:
        """Built-in names first, then user presets (excluding any name shadowing a built-in)."""
        user = [n for n in self._user() if n not in BUILTINS]
        return list(BUILTINS) + sorted(user)

    def get(self, name: str) -> list[int] | None:
        if name in BUILTINS:
            return list(BUILTINS[name])
        return self._user().get(name)

    def is_builtin(self, name: str) -> bool:
        return name in BUILTINS

    def save(self, name: str, points: list[int]) -> bool:
        """Save a user preset. Returns False for an empty name or a built-in name."""
        name = name.strip()
        if not name or name in BUILTINS or len(points) != 4:
            return False
        presets = self._user()
        presets[name] = [int(p) for p in points]
        self._write_user(presets)
        return True

    def delete(self, name: str) -> None:
        if name in BUILTINS:
            return
        presets = self._user()
        if presets.pop(name, None) is not None:
            self._write_user(presets)
