"""Physical pad layouts: which xsetwacom button maps to which key, and the ring.

Layouts are JSON files so other tablet models can be added without code changes. They are read
from two places, **user dir first**: ``~/.config/wacom-control-panel/layouts/`` (written by the
setup wizard) then the bundled ``wacom_panel/layouts/``. A layout is matched to a tablet by
substring against its name; if none matches, a generic flat key list is synthesised.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .store import config_dir

_LAYOUT_DIR = Path(__file__).resolve().parent.parent / "layouts"


def user_layout_dir() -> Path:
    """Where the setup wizard writes per-user layouts (searched before the bundled ones)."""
    return config_dir() / "layouts"


@dataclass(frozen=True)
class PadKey:
    button: int
    label: str


@dataclass(frozen=True)
class PadRing:
    center: int | None
    center_label: str
    modes: int
    cw: str  # xsetwacom parameter for clockwise, e.g. "AbsWheelUp"
    ccw: str  # ... counter-clockwise, e.g. "AbsWheelDown"


@dataclass
class PadLayout:
    display_name: str
    top_keys: list[PadKey] = field(default_factory=list)
    bottom_keys: list[PadKey] = field(default_factory=list)
    ring: PadRing | None = None
    matched: bool = True  # False for the synthesised generic fallback
    # evdev ecode name (e.g. "BTN_1") -> xsetwacom button number. Populated only for models whose
    # raw button codes have been mapped; lets the ring daemon translate a grabbed BTN_* press into
    # the configured pad action. Empty == the pad-grab feature isn't supported for this model.
    evdev_buttons: dict[str, int] = field(default_factory=dict)

    @property
    def all_buttons(self) -> list[int]:
        keys = [k.button for k in (*self.top_keys, *self.bottom_keys)]
        if self.ring and self.ring.center is not None:
            keys.append(self.ring.center)
        return keys


def _load_json_layouts() -> list[dict]:
    """All layout dicts, user dir first so a user file shadows a bundled one of the same name."""
    layouts: list[dict] = []
    for directory in (user_layout_dir(), _LAYOUT_DIR):  # order = precedence
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                layouts.append(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
    return layouts


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w.-]+", "_", (name or "").strip()).strip("_").lower()
    return slug or "tablet"


def save_user_layout(data: dict) -> Path:
    """Write a wizard-built layout into the user dir; returns the path. Slug from display name."""
    directory = user_layout_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_slugify(data.get('display_name', 'tablet'))}.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def _keys_from(data: list, detected: set[int]) -> list[PadKey]:
    out: list[PadKey] = []
    for item in data or []:
        button = int(item["button"])
        if not detected or button in detected:
            out.append(PadKey(button=button, label=str(item.get("label", f"Button {button}"))))
    return out


def _ring_from(data: dict | None, detected: set[int]) -> PadRing | None:
    if not data:
        return None
    center = data.get("center")
    if center is not None and (not detected or int(center) in detected):
        center = int(center)
    else:
        center = None
    return PadRing(
        center=center,
        center_label=str(data.get("center_label", "Mode")),
        modes=int(data.get("modes", 1)),
        cw=str(data.get("cw", "AbsWheelUp")),
        ccw=str(data.get("ccw", "AbsWheelDown")),
    )


def _generic_layout(detected_buttons: list[int]) -> PadLayout:
    keys = [PadKey(button=b, label=f"Button {b}") for b in detected_buttons]
    return PadLayout(display_name="Pad", top_keys=keys, matched=False)


def load_layout(tablet_name: str, detected_buttons: list[int]) -> PadLayout:
    """Best layout for ``tablet_name``; falls back to a flat list of detected buttons."""
    detected = set(detected_buttons)
    name = (tablet_name or "").lower()
    for data in _load_json_layouts():
        if any(token.lower() in name for token in data.get("match", [])):
            return PadLayout(
                display_name=str(data.get("display_name", tablet_name)),
                top_keys=_keys_from(data.get("top_keys"), detected),
                bottom_keys=_keys_from(data.get("bottom_keys"), detected),
                ring=_ring_from(data.get("ring"), detected),
                matched=True,
                evdev_buttons={
                    str(name): int(num)
                    for name, num in (data.get("evdev_buttons") or {}).items()
                },
            )
    return _generic_layout(detected_buttons)
