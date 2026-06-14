"""Assemble a pad-layout JSON from what the setup wizard captured — pure, no Qt/evdev.

The wizard collects, for each physical key the user pressed, a ``Capture`` of its xsetwacom button
number and (best-effort) its evdev ``BTN_*`` name. This turns those ordered captures into the same
layout-JSON shape that :mod:`wacom_panel.core.pad_layout` loads and the Pad page renders — ready to
hand to :func:`wacom_panel.core.pad_layout.save_user_layout`.
"""

from __future__ import annotations

from dataclasses import dataclass

# The verified standard mapping (PTH-660): clockwise scrolls down. Used as the default ring
# direction — the daemon reads the ring's raw ABS_WHEEL anyway and can invert per unit if needed.
_RING_CW = "AbsWheelDown"
_RING_CCW = "AbsWheelUp"


@dataclass(frozen=True)
class Capture:
    """One captured key: its xsetwacom button number and, if read, its evdev ``BTN_*`` name."""

    xnum: int
    evdev: str | None = None


def _keys(captures: list[Capture], start: int) -> tuple[list[dict], int]:
    """Layout key dicts for a group, labelled ``Key <n>`` continuing from ``start``."""
    out = []
    n = start
    for cap in captures:
        out.append({"button": cap.xnum, "label": f"Key {n}"})
        n += 1
    return out, n


def build_layout(
    *,
    display_name: str,
    model: str = "",
    has_ring: bool = False,
    ring_modes: int = 1,
    top: list[Capture],
    bottom: list[Capture] | None = None,
    center: Capture | None = None,
) -> dict:
    """Build the layout JSON dict from captured keys (press order = top→bottom)."""
    bottom = bottom or []

    top_keys, n = _keys(top, 1)
    bottom_keys, _ = _keys(bottom, n)

    # Match substrings the loader tests against the xsetwacom device name (which carries a tool
    # suffix like " Pad pad"); lowercase name + model so either can hit.
    match = [display_name.lower()]
    if model:
        match.append(model.lower())

    layout: dict = {
        "match": match,
        "display_name": display_name,
        "top_keys": top_keys,
        "bottom_keys": bottom_keys,
    }

    if has_ring:
        layout["ring"] = {
            "center": center.xnum if center is not None else None,
            "center_label": "Mode",
            "modes": max(1, ring_modes),
            "cw": _RING_CW,
            "ccw": _RING_CCW,
        }

    # evdev_buttons: only the keys whose BTN_* code we actually captured (best-effort).
    evdev: dict[str, int] = {}
    for cap in (*top, *bottom, *( [center] if center is not None else [] )):
        if cap.evdev:
            evdev[cap.evdev] = cap.xnum
    if evdev:
        layout["evdev_buttons"] = evdev

    return layout
