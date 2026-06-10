"""Profile model: a named, serialisable bundle of tablet settings.

For the MVP a profile carries a single :class:`MappingConfig`. Later phases (pressure curve,
buttons, touch) add sibling fields without changing how mapping is stored.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .mapping import Area


@dataclass
class MappingConfig:
    """How the tablet surface maps onto the desktop.

    ``output`` is an XRandR connector name (e.g. ``"DP-4"``) or ``None`` for the whole
    desktop. ``area`` is the resolved active area in device units; when ``force_proportions``
    is set it is recomputed from the tablet + output aspect, otherwise it is taken as-is.
    """

    output: str | None = None
    force_proportions: bool = True
    rotate: str = "none"  # none | cw | ccw | half
    mode: str = "Absolute"  # Absolute | Relative
    anchor: str = "center"
    zoom: float = 1.0
    area: list[int] | None = None  # [x1, y1, x2, y2]; None == full tablet
    apply_to_touch: bool = False

    @property
    def area_obj(self) -> Area | None:
        return Area(*self.area) if self.area else None

    def set_area(self, area: Area | None) -> None:
        self.area = area.as_list() if area else None


@dataclass
class ButtonAction:
    """An action bound to a pen or pad button.

    ``kind`` is ``"button"`` (mouse button ``value``), ``"key"`` (a keystroke combo such as
    ``"ctrl z"``), or ``"disabled"``. Serialises to the xsetwacom action string.
    """

    kind: str = "button"  # button | doubleclick | key | disabled
    value: str = ""

    def to_xsetwacom(self) -> str:
        if self.kind == "disabled":
            return "0"
        if self.kind == "doubleclick":
            return "button +1 -1 +1 -1"
        value = self.value.strip()
        if not value:
            return "0"
        if self.kind == "key":
            return f"key {value}"
        # "+N" = press-and-hold (the driver releases on physical release), matching the
        # device defaults. A bare "N" expands to "+N -N" (an instant click) and breaks
        # click-and-drag — so always emit the held form.
        return f"button +{value}"


def _action(kind: str, value: str) -> ButtonAction:
    return ButtonAction(kind=kind, value=value)


@dataclass
class PenConfig:
    """Pen feel + button mapping (applied to the stylus / eraser)."""

    pressure_curve: list[int] = field(default_factory=lambda: [0, 0, 100, 100])
    threshold: int = 27  # tip pressure threshold
    button1: ButtonAction = field(default_factory=lambda: _action("button", "1"))
    button2: ButtonAction = field(default_factory=lambda: _action("button", "2"))
    button3: ButtonAction = field(default_factory=lambda: _action("button", "3"))


@dataclass
class TouchConfig:
    """Finger-touch behaviour (applied to the touch device)."""

    enabled: bool = True
    gestures: bool = True
    scroll_distance: int = 20
    zoom_distance: int = 50
    tap_time: int = 250


@dataclass
class PadConfig:
    """ExpressKey button mapping (applied to the pad device).

    ``buttons`` maps an xsetwacom pad button number (as a string key, for JSON friendliness)
    to its :class:`ButtonAction`.
    """

    buttons: dict[str, ButtonAction] = field(default_factory=dict)


def _button_action_from(data: object) -> ButtonAction:
    return ButtonAction(**data) if isinstance(data, dict) else ButtonAction()


@dataclass
class Profile:
    """A named collection of tablet settings."""

    name: str
    mapping: MappingConfig = field(default_factory=MappingConfig)
    pen: PenConfig = field(default_factory=PenConfig)
    touch: TouchConfig = field(default_factory=TouchConfig)
    pad: PadConfig = field(default_factory=PadConfig)

    # ---- serialisation ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mapping": asdict(self.mapping),
            "pen": asdict(self.pen),
            "touch": asdict(self.touch),
            "pad": asdict(self.pad),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Profile:
        mapping = MappingConfig(**(data.get("mapping") or {}))

        pen_data = dict(data.get("pen") or {})
        for key in ("button1", "button2", "button3"):
            if key in pen_data:
                pen_data[key] = _button_action_from(pen_data[key])
        pen = PenConfig(**pen_data)

        touch = TouchConfig(**(data.get("touch") or {}))

        pad_buttons = (data.get("pad") or {}).get("buttons") or {}
        pad = PadConfig(buttons={k: _button_action_from(v) for k, v in pad_buttons.items()})

        return cls(name=data["name"], mapping=mapping, pen=pen, touch=touch, pad=pad)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> Profile:
        return cls.from_dict(json.loads(Path(path).read_text()))
