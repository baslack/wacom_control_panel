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
class Profile:
    """A named collection of tablet settings."""

    name: str
    mapping: MappingConfig = field(default_factory=MappingConfig)

    # ---- serialisation ----------------------------------------------------
    def to_dict(self) -> dict:
        return {"name": self.name, "mapping": asdict(self.mapping)}

    @classmethod
    def from_dict(cls, data: dict) -> Profile:
        mapping = MappingConfig(**(data.get("mapping") or {}))
        return cls(name=data["name"], mapping=mapping)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> Profile:
        return cls.from_dict(json.loads(Path(path).read_text()))
