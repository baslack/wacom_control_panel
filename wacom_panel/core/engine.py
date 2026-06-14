"""Turn a :class:`MappingConfig` into concrete xsetwacom commands and apply them.

This is the single source of truth shared by the GUI, the headless ``--apply`` CLI, and the
generated apply-script — so what you preview is exactly what gets persisted and reapplied.
"""

from __future__ import annotations

import re

from ..backend import xsetwacom
from ..backend.devices import Tablet
from ..backend.displays import Output, desktop_bounds
from .mapping import Area, forced_area
from .profile import MappingConfig, PadConfig, PenConfig, Profile, TouchConfig

# Fallback if the device can't be probed (no stylus / xsetwacom unavailable).
_DEFAULT_TABLET_AREA = (44704, 27940)

# Per-device cache of the true native size, so we probe at most once per process.
_NATIVE_CACHE: dict[str, tuple[int, int]] = {}


def _parse_area(raw: str) -> tuple[int, int, int, int] | None:
    parts = raw.split()
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (int(p) for p in parts)
    except ValueError:
        return None
    return x1, y1, x2, y2


def tablet_native_area(tablet: Tablet) -> tuple[int, int]:
    """Native (full) tablet dimensions in device units.

    The current ``Area`` may already be cropped (by us, or by a reapplied profile), so reading
    it would shrink the tablet cumulatively on each apply. Instead we probe the true extent via
    ``ResetArea``, then restore the previous Area, and cache the result for the process.
    """
    stylus = tablet.stylus
    if stylus is None:
        return _DEFAULT_TABLET_AREA
    if stylus.name in _NATIVE_CACHE:
        return _NATIVE_CACHE[stylus.name]
    try:
        previous = _parse_area(xsetwacom.get(stylus.name, "Area"))
        xsetwacom.reset_area(stylus.name, dry=False)
        native = _parse_area(xsetwacom.get(stylus.name, "Area"))
        if previous is not None:  # restore the user's current area (non-destructive probe)
            xsetwacom.set_param(stylus.name, "Area", *previous, dry=False)
    except xsetwacom.XsetwacomError:
        return _DEFAULT_TABLET_AREA
    if native is None:
        return _DEFAULT_TABLET_AREA
    w, h = native[2] - native[0], native[3] - native[1]
    if w <= 0 or h <= 0:
        return _DEFAULT_TABLET_AREA
    _NATIVE_CACHE[stylus.name] = (w, h)
    return (w, h)


def resolve_maptooutput(mapping: MappingConfig, outputs: list[Output]) -> str:
    """The MapToOutput argument: a connector name, or the whole-desktop geometry string."""
    if mapping.output:
        for o in outputs:
            if o.name == mapping.output:
                return o.name
        return mapping.output  # stale connector; pass through and let xsetwacom complain
    x, y, w, h = desktop_bounds(outputs)
    return f"{w}x{h}+{x}+{y}"


def target_size(mapping: MappingConfig, outputs: list[Output]) -> tuple[int, int] | None:
    """Pixel size of the mapping target: the chosen output, or the whole-desktop bounds."""
    if mapping.output:
        target = next((o for o in outputs if o.name == mapping.output), None)
        return (target.width, target.height) if target is not None else None
    _x, _y, w, h = desktop_bounds(outputs)
    return (w, h) if w > 0 and h > 0 else None


def resolve_area(mapping: MappingConfig, tablet: Tablet, outputs: list[Output]) -> Area | None:
    """The Area to apply: recomputed from proportions, or the stored explicit area."""
    if mapping.force_proportions:
        size = target_size(mapping, outputs)
        if size is not None:
            tw, th = tablet_native_area(tablet)
            return forced_area(
                tw, th, size[0], size[1],
                anchor=mapping.anchor, zoom=mapping.zoom, rotate=mapping.rotate,
            )
    return mapping.area_obj


def mapping_commands(
    mapping: MappingConfig,
    tablet: Tablet,
    outputs: list[Output],
) -> list[list[str]]:
    """Build the full list of xsetwacom argv commands for this mapping (no execution).

    Mapping is applied to every pen tool (stylus/eraser/cursor); touch is included only when
    ``apply_to_touch`` is set.
    """
    area = resolve_area(mapping, tablet, outputs)
    maptooutput = resolve_maptooutput(mapping, outputs)

    targets = list(tablet.pen_tools)
    if mapping.apply_to_touch and tablet.touch is not None:
        targets.append(tablet.touch)

    commands: list[list[str]] = []
    for dev in targets:
        commands.append(xsetwacom.build_set_command(dev.name, "Mode", mapping.mode))
        commands.append(xsetwacom.build_set_command(dev.name, "Rotate", mapping.rotate))
        if area is not None:
            commands.append(xsetwacom.build_set_command(dev.name, "Area", *area.as_list()))
        else:
            commands.append([xsetwacom.BINARY, "--set", dev.name, "ResetArea"])
        commands.append(
            xsetwacom.build_set_command(dev.name, "MapToOutput", maptooutput)
        )
    return commands


def pen_commands(pen: PenConfig, tablet: Tablet) -> list[list[str]]:
    """Pressure curve, tip threshold and button mapping (stylus + eraser)."""
    commands: list[list[str]] = []
    feel_targets = tablet.by_type("STYLUS", "ERASER")
    for dev in feel_targets:
        commands.append(
            xsetwacom.build_set_command(dev.name, "PressureCurve", *pen.pressure_curve)
        )
        commands.append(xsetwacom.build_set_command(dev.name, "Threshold", pen.threshold))
    stylus = tablet.stylus
    if stylus is not None:
        for num, action in ((1, pen.button1), (2, pen.button2), (3, pen.button3)):
            commands.append(
                xsetwacom.build_set_command(stylus.name, "Button", num, action.to_xsetwacom())
            )
    return commands


def touch_commands(touch: TouchConfig, tablet: Tablet) -> list[list[str]]:
    """Touch on/off, gestures and scroll/zoom/tap tuning (touch device)."""
    dev = tablet.touch
    if dev is None:
        return []
    return [
        xsetwacom.build_set_command(dev.name, "Touch", "on" if touch.enabled else "off"),
        xsetwacom.build_set_command(dev.name, "Gesture", "on" if touch.gestures else "off"),
        xsetwacom.build_set_command(dev.name, "ScrollDistance", touch.scroll_distance),
        xsetwacom.build_set_command(dev.name, "ZoomDistance", touch.zoom_distance),
        xsetwacom.build_set_command(dev.name, "TapTime", touch.tap_time),
    ]


_PAD_BUTTON_RE = re.compile(r'"Button"\s+"(\d+)"')


def parse_pad_buttons(shell_all: str) -> list[int]:
    """Pad button numbers present in a ``-s --get <pad> all`` dump, in order."""
    seen: list[int] = []
    for match in _PAD_BUTTON_RE.finditer(shell_all):
        num = int(match.group(1))
        if num not in seen:
            seen.append(num)
    return seen


def detect_pad_buttons(tablet: Tablet) -> list[int]:
    """Query the pad device for its available ExpressKey button numbers ([] if none)."""
    pad = tablet.pad
    if pad is None:
        return []
    try:
        return parse_pad_buttons(xsetwacom.get_shell_all(pad.name))
    except xsetwacom.XsetwacomError:
        return []


# Wheel params silenced when the evdev ring daemon owns the ring (so the X driver does not
# also emit the keystroke fallback — that would double up with the daemon's REL_WHEEL).
_DEFAULT_RING_PARAMS = ("AbsWheelUp", "AbsWheelDown")


def pad_commands(pad: PadConfig, tablet: Tablet) -> list[list[str]]:
    """ExpressKey + touch-ring mapping (pad device).

    Express keys are always bound via xsetwacom. The touch ring is bound to its keystroke
    fallback *unless* ``pad.ring_daemon`` is set, in which case the ring params are disabled
    (``"0"``) and the evdev ring daemon drives the ring as real ``REL_WHEEL`` instead.
    """
    dev = tablet.pad
    if dev is None:
        return []
    commands: list[list[str]] = []
    for num, action in sorted(pad.buttons.items(), key=lambda kv: int(kv[0])):
        commands.append(
            xsetwacom.build_set_command(dev.name, "Button", num, action.to_xsetwacom())
        )
    if pad.ring_daemon:
        # Disable every configured wheel param (and the standard pair as a floor), so the
        # driver stays silent and only the daemon scrolls.
        params = sorted(set(pad.wheels) | set(_DEFAULT_RING_PARAMS))
        for param in params:
            commands.append(xsetwacom.build_set_command(dev.name, param, "0"))
    else:
        for param, action in sorted(pad.wheels.items()):
            commands.append(
                xsetwacom.build_set_command(dev.name, param, action.to_xsetwacom(momentary=True))
            )
    return commands


def _run_commands(commands: list[list[str]], *, dry_run: bool) -> list[list[str]]:
    if not dry_run:
        for cmd in commands:
            xsetwacom.set_param(cmd[2], cmd[3], *cmd[4:], dry=False)
    return commands


def apply_mapping(
    mapping: MappingConfig,
    tablet: Tablet,
    outputs: list[Output],
    *,
    dry_run: bool = False,
) -> list[list[str]]:
    """Apply (or, if ``dry_run``, just return) the mapping commands."""
    return _run_commands(mapping_commands(mapping, tablet, outputs), dry_run=dry_run)


def profile_commands(
    profile: Profile, tablet: Tablet, outputs: list[Output]
) -> list[list[str]]:
    """All xsetwacom commands for a full profile: mapping + pen + touch + pad."""
    return (
        mapping_commands(profile.mapping, tablet, outputs)
        + pen_commands(profile.pen, tablet)
        + touch_commands(profile.touch, tablet)
        + pad_commands(profile.pad, tablet)
    )


def apply_profile(
    profile: Profile, tablet: Tablet, outputs: list[Output], *, dry_run: bool = False
) -> list[list[str]]:
    """Apply (or return) every setting in a profile."""
    return _run_commands(profile_commands(profile, tablet, outputs), dry_run=dry_run)
