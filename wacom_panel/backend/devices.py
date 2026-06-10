"""Discover Wacom input devices and group the per-tool devices into tablets.

xsetwacom exposes each *tool* as its own device — a single physical tablet shows up as
separate ``stylus`` / ``eraser`` / ``cursor`` / ``pad`` / ``touch`` entries that share one
surface. Mapping (Area / Rotate / MapToOutput) must be applied to the pen-tool group
together, so we reconstruct the tablet grouping here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import xsetwacom

#: Device ``type`` values that correspond to the pen and share the physical surface.
PEN_TYPES = frozenset({"STYLUS", "ERASER", "CURSOR"})

# "Wacom Intuos Pro M Pen stylus   \tid: 18\ttype: STYLUS"
_DEVICE_RE = re.compile(r"^(?P<name>.+?)\s+id:\s*(?P<id>\d+)\s+type:\s*(?P<type>\S+)")

# Trailing tool descriptor, e.g. " Pen stylus", " Finger touch", " Pad pad".
_TOOL_SUFFIX_RE = re.compile(
    r"\s+(?:Pen|Pad|Finger|Touch)?\s*(?:stylus|eraser|cursor|pad|touch)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Device:
    """A single xsetwacom tool device."""

    name: str
    id: int
    type: str  # STYLUS / ERASER / CURSOR / PAD / TOUCH


@dataclass
class Tablet:
    """A physical tablet — the group of tool devices sharing one base name."""

    name: str
    devices: list[Device] = field(default_factory=list)

    def by_type(self, *types: str) -> list[Device]:
        wanted = {t.upper() for t in types}
        return [d for d in self.devices if d.type.upper() in wanted]

    @property
    def pen_tools(self) -> list[Device]:
        """Stylus/eraser/cursor — the devices a mapping should be applied to together."""
        return [d for d in self.devices if d.type.upper() in PEN_TYPES]

    @property
    def stylus(self) -> Device | None:
        tools = self.by_type("STYLUS")
        return tools[0] if tools else None

    @property
    def pad(self) -> Device | None:
        pads = self.by_type("PAD")
        return pads[0] if pads else None

    @property
    def touch(self) -> Device | None:
        touches = self.by_type("TOUCH")
        return touches[0] if touches else None


def tablet_base_name(device_name: str) -> str:
    """Strip the trailing tool descriptor to get the shared tablet name."""
    return _TOOL_SUFFIX_RE.sub("", device_name).strip()


def parse_devices(text: str) -> list[Device]:
    """Parse the output of ``xsetwacom --list devices`` into :class:`Device` objects."""
    devices: list[Device] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _DEVICE_RE.match(line)
        if m:
            devices.append(
                Device(name=m["name"].strip(), id=int(m["id"]), type=m["type"].strip())
            )
    return devices


def group_tablets(devices: list[Device]) -> list[Tablet]:
    """Group tool devices into tablets by their shared base name (insertion order kept)."""
    tablets: dict[str, Tablet] = {}
    for dev in devices:
        base = tablet_base_name(dev.name) or dev.name
        tablets.setdefault(base, Tablet(name=base)).devices.append(dev)
    return list(tablets.values())


def list_tablets() -> list[Tablet]:
    """Query xsetwacom live and return grouped tablets."""
    return group_tablets(parse_devices(xsetwacom.list_devices_raw()))
