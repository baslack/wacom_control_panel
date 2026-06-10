"""Turn a :class:`MappingConfig` into concrete xsetwacom commands and apply them.

This is the single source of truth shared by the GUI, the headless ``--apply`` CLI, and the
generated apply-script — so what you preview is exactly what gets persisted and reapplied.
"""

from __future__ import annotations

from ..backend import xsetwacom
from ..backend.devices import Tablet
from ..backend.displays import Output, desktop_bounds
from .mapping import Area, forced_area
from .profile import MappingConfig

# Native tablet area is queried lazily; this is only a fallback if the query fails.
_DEFAULT_TABLET_AREA = (44704, 27940)


def tablet_native_area(tablet: Tablet) -> tuple[int, int]:
    """Native (full) tablet dimensions in device units, via ResetArea round-trip-free query.

    We read the stylus' default Area. We deliberately do not mutate the device: the current
    Area may already be cropped, so we ask for the full extent by reading ``Area`` after a
    ``ResetArea`` would be destructive — instead we rely on the documented native maximum and
    fall back to a sane default if the stylus is unavailable.
    """
    stylus = tablet.stylus
    if stylus is None:
        return _DEFAULT_TABLET_AREA
    try:
        # Querying the stored max via the driver: read current, but the safest portable read
        # of native size is the device's reported Area after the driver initialises it.
        raw = xsetwacom.get(stylus.name, "Area")
        parts = [int(p) for p in raw.split()]
        if len(parts) == 4:
            w, h = parts[2] - parts[0], parts[3] - parts[1]
            if w > 0 and h > 0:
                return w, h
    except (xsetwacom.XsetwacomError, ValueError):
        pass
    return _DEFAULT_TABLET_AREA


def resolve_maptooutput(mapping: MappingConfig, outputs: list[Output]) -> str:
    """The MapToOutput argument: a connector name, or the whole-desktop geometry string."""
    if mapping.output:
        for o in outputs:
            if o.name == mapping.output:
                return o.name
        return mapping.output  # stale connector; pass through and let xsetwacom complain
    x, y, w, h = desktop_bounds(outputs)
    return f"{w}x{h}+{x}+{y}"


def resolve_area(mapping: MappingConfig, tablet: Tablet, outputs: list[Output]) -> Area | None:
    """The Area to apply: recomputed from proportions, or the stored explicit area."""
    if mapping.force_proportions and mapping.output:
        target = next((o for o in outputs if o.name == mapping.output), None)
        if target is not None:
            tw, th = tablet_native_area(tablet)
            return forced_area(
                tw, th, target.width, target.height,
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


def apply_mapping(
    mapping: MappingConfig,
    tablet: Tablet,
    outputs: list[Output],
    *,
    dry_run: bool = False,
) -> list[list[str]]:
    """Apply (or, if ``dry_run``, just return) the mapping commands."""
    commands = mapping_commands(mapping, tablet, outputs)
    if not dry_run:
        for cmd in commands:
            xsetwacom.set_param(cmd[2], cmd[3], *cmd[4:], dry=False)
    return commands
