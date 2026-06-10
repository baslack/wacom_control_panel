"""Aspect-correct tablet-to-display mapping math.

``xsetwacom`` maps the tablet's active **Area** rectangle (in device units) linearly onto a
target output. If the Area aspect ratio does not match the output aspect ratio, the pen feels
stretched. "Force proportions" shrinks the Area to letterbox-match the output, preserving the
maximum usable tablet surface.

Everything here is pure integer/float math — no Qt, no subprocess — so it is trivially
unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

Rotate = str  # "none" | "half" | "cw" | "ccw"
Anchor = str  # "center" | "top-left" | "top-right" | "bottom-left" | "bottom-right"

ROTATIONS = ("none", "cw", "ccw", "half")
ANCHORS = ("center", "top-left", "top-right", "bottom-left", "bottom-right")


@dataclass(frozen=True)
class Area:
    """A tablet active-area rectangle in device units (xsetwacom ``Area`` order)."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    def as_list(self) -> list[int]:
        return [self.x1, self.y1, self.x2, self.y2]


def target_area_aspect(output_aspect: float, rotate: Rotate = "none") -> float:
    """Desired Area aspect (w/h, in native device coords) for a given output and rotation.

    Under ``cw``/``ccw`` the tablet axes are swapped, so the *native* Area must have the
    reciprocal aspect for the *displayed* mapping to come out proportional.
    """
    if rotate in ("cw", "ccw"):
        return 1.0 / output_aspect if output_aspect else 0.0
    return output_aspect


def fit_rect(outer_w: int, outer_h: int, aspect: float) -> tuple[int, int]:
    """Largest (w, h) of the given ``aspect`` (w/h) that fits inside outer_w × outer_h."""
    if aspect <= 0:
        return outer_w, outer_h
    outer_aspect = outer_w / outer_h
    if aspect >= outer_aspect:
        # Wider than the container -> width-limited.
        return outer_w, round(outer_w / aspect)
    # Taller than the container -> height-limited.
    return round(outer_h * aspect), outer_h


def place_rect(
    outer_w: int, outer_h: int, w: int, h: int, anchor: Anchor = "center"
) -> tuple[int, int]:
    """Top-left (x, y) placing a w×h rect inside outer_w×outer_h per ``anchor``."""
    if "left" in anchor:
        x = 0
    elif "right" in anchor:
        x = outer_w - w
    else:
        x = (outer_w - w) // 2
    if "top" in anchor:
        y = 0
    elif "bottom" in anchor:
        y = outer_h - h
    else:
        y = (outer_h - h) // 2
    return max(0, x), max(0, y)


def forced_area(
    tablet_w: int,
    tablet_h: int,
    output_w: int,
    output_h: int,
    *,
    anchor: Anchor = "center",
    zoom: float = 1.0,
    rotate: Rotate = "none",
) -> Area:
    """Compute the aspect-correct tablet Area for mapping onto an output.

    ``zoom`` in (0, 1] uses a smaller, centred-by-anchor portion of the proportional area
    (zoom < 1 == use less of the tablet). The result is clamped within the tablet bounds.
    """
    output_aspect = output_w / output_h if output_h else 0.0
    aspect = target_area_aspect(output_aspect, rotate)
    w, h = fit_rect(tablet_w, tablet_h, aspect)

    zoom = max(0.01, min(1.0, zoom))
    w = max(1, round(w * zoom))
    h = max(1, round(h * zoom))
    w = min(w, tablet_w)
    h = min(h, tablet_h)

    x, y = place_rect(tablet_w, tablet_h, w, h, anchor)
    return Area(x, y, x + w, y + h)
