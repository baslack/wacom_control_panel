"""Physical pad layouts: which xsetwacom button maps to which key, and the ring.

Layouts are JSON files under ``wacom_panel/layouts/`` so other tablet models can be added
without code changes. A layout is matched to a tablet by substring against its name. If no
layout matches, a generic one is synthesised that simply lists every detected button.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_LAYOUT_DIR = Path(__file__).resolve().parent.parent / "layouts"


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

    @property
    def all_buttons(self) -> list[int]:
        keys = [k.button for k in (*self.top_keys, *self.bottom_keys)]
        if self.ring and self.ring.center is not None:
            keys.append(self.ring.center)
        return keys


def _load_json_layouts() -> list[dict]:
    layouts: list[dict] = []
    if not _LAYOUT_DIR.is_dir():
        return layouts
    for path in sorted(_LAYOUT_DIR.glob("*.json")):
        try:
            layouts.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return layouts


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
            )
    return _generic_layout(detected_buttons)
