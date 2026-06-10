"""Enumerate connected display outputs (connector name + pixel geometry).

We parse ``xrandr --listmonitors`` because it yields the XRandR connector name (``DP-4``,
``HDMI-1``, …) that ``xsetwacom``'s ``MapToOutput`` expects, and it works headlessly without
a running QApplication. (X11 only — which is the only place xsetwacom is valid anyway.)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

# " 0: +*DP-4 1920/510x1080/287+0+0  DP-4"
_MONITOR_RE = re.compile(
    r"^\s*\d+:\s*\+?\*?(?P<name>\S+)\s+"
    r"(?P<w>\d+)/\d+x(?P<h>\d+)/\d+(?P<x>[+-]\d+)(?P<y>[+-]\d+)"
)


@dataclass(frozen=True)
class Output:
    """A connected display output in the X screen."""

    name: str  # XRandR connector, e.g. "DP-4"
    width: int
    height: int
    x: int
    y: int
    primary: bool = False

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def geometry_str(self) -> str:
        """``WxH+X+Y`` — the alternate form MapToOutput also accepts."""
        return f"{self.width}x{self.height}+{self.x}+{self.y}"


def parse_listmonitors(text: str) -> list[Output]:
    """Parse ``xrandr --listmonitors`` output into :class:`Output` objects."""
    outputs: list[Output] = []
    for line in text.splitlines():
        if ":" not in line or line.lstrip().startswith("Monitors:"):
            continue
        m = _MONITOR_RE.match(line)
        if not m:
            continue
        primary = "*" in line.split(":", 1)[1].split()[0]
        outputs.append(
            Output(
                name=m["name"],
                width=int(m["w"]),
                height=int(m["h"]),
                x=int(m["x"]),
                y=int(m["y"]),
                primary=primary,
            )
        )
    return outputs


def list_outputs() -> list[Output]:
    """Query xrandr live for connected outputs. Returns [] if xrandr is unavailable."""
    if shutil.which("xrandr") is None:
        return []
    try:
        proc = subprocess.run(
            ["xrandr", "--listmonitors"], capture_output=True, text=True, check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return parse_listmonitors(proc.stdout)


def desktop_bounds(outputs: list[Output]) -> tuple[int, int, int, int]:
    """Bounding box (x, y, width, height) spanning all outputs."""
    if not outputs:
        return (0, 0, 0, 0)
    min_x = min(o.x for o in outputs)
    min_y = min(o.y for o in outputs)
    max_x = max(o.x + o.width for o in outputs)
    max_y = max(o.y + o.height for o in outputs)
    return (min_x, min_y, max_x - min_x, max_y - min_y)
