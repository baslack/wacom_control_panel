"""Tests for parsing and command-building in the backend + engine (no real subprocess)."""

import pytest

from wacom_panel.backend import xsetwacom
from wacom_panel.backend.devices import (
    group_tablets,
    parse_devices,
    tablet_base_name,
)
from wacom_panel.backend.displays import desktop_bounds, parse_listmonitors
from wacom_panel.core.engine import mapping_commands, resolve_area, resolve_maptooutput
from wacom_panel.core.profile import MappingConfig

LIST_DEVICES = """\
Wacom Intuos Pro M Pen stylus   \tid: 18\ttype: STYLUS
Wacom Intuos Pro M Pad pad      \tid: 19\ttype: PAD
Wacom Intuos Pro M Finger touch \tid: 20\ttype: TOUCH
Wacom Intuos Pro M Pen eraser   \tid: 24\ttype: ERASER
Wacom Intuos Pro M Pen cursor   \tid: 25\ttype: CURSOR
"""

LIST_MONITORS = """\
Monitors: 2
 0: +*DP-4 1920/510x1080/287+0+0  DP-4
 1: +DP-2 1920/510x1080/287+1920+0  DP-2
"""


def test_parse_devices():
    devs = parse_devices(LIST_DEVICES)
    assert len(devs) == 5
    stylus = devs[0]
    assert stylus.name == "Wacom Intuos Pro M Pen stylus"
    assert stylus.id == 18
    assert stylus.type == "STYLUS"


def test_tablet_base_name():
    assert tablet_base_name("Wacom Intuos Pro M Pen stylus") == "Wacom Intuos Pro M"
    assert tablet_base_name("Wacom Intuos Pro M Finger touch") == "Wacom Intuos Pro M"
    assert tablet_base_name("Wacom Intuos Pro M Pad pad") == "Wacom Intuos Pro M"


def test_group_tablets():
    tablets = group_tablets(parse_devices(LIST_DEVICES))
    assert len(tablets) == 1
    tab = tablets[0]
    assert tab.name == "Wacom Intuos Pro M"
    assert len(tab.pen_tools) == 3
    assert {d.type for d in tab.pen_tools} == {"STYLUS", "ERASER", "CURSOR"}
    assert tab.pad is not None and tab.pad.type == "PAD"
    assert tab.touch is not None and tab.touch.type == "TOUCH"


def test_parse_listmonitors():
    outs = parse_listmonitors(LIST_MONITORS)
    assert [o.name for o in outs] == ["DP-4", "DP-2"]
    assert outs[0].primary is True
    assert outs[1].primary is False
    assert outs[0].width == 1920 and outs[0].height == 1080
    assert outs[1].x == 1920 and outs[1].y == 0


def test_desktop_bounds():
    outs = parse_listmonitors(LIST_MONITORS)
    assert desktop_bounds(outs) == (0, 0, 3840, 1080)


def test_build_set_command_quotes_nothing():
    cmd = xsetwacom.build_set_command(
        "Wacom Intuos Pro M Pen stylus", "Area", 0, 1397, 44704, 26543
    )
    assert cmd == [
        "xsetwacom", "--set", "Wacom Intuos Pro M Pen stylus",
        "Area", "0", "1397", "44704", "26543",
    ]


def test_resolve_maptooutput_named_and_desktop():
    outs = parse_listmonitors(LIST_MONITORS)
    assert resolve_maptooutput(MappingConfig(output="DP-4"), outs) == "DP-4"
    # Whole-desktop -> bounding-box geometry string.
    assert resolve_maptooutput(MappingConfig(output=None), outs) == "3840x1080+0+0"


def test_mapping_commands_cover_pen_tools_only_by_default():
    tablet = group_tablets(parse_devices(LIST_DEVICES))[0]
    outs = parse_listmonitors(LIST_MONITORS)
    mapping = MappingConfig(output="DP-4", force_proportions=False,
                            area=[0, 1397, 44704, 26543])
    cmds = mapping_commands(mapping, tablet, outs)
    targeted_devices = {c[2] for c in cmds}
    assert "Wacom Intuos Pro M Finger touch" not in targeted_devices  # touch off by default
    assert "Wacom Intuos Pro M Pen stylus" in targeted_devices
    # Each pen tool gets Mode, Rotate, Area, MapToOutput.
    params = [c[3] for c in cmds if c[2] == "Wacom Intuos Pro M Pen stylus"]
    assert params == ["Mode", "Rotate", "Area", "MapToOutput"]


def test_force_proportions_whole_desktop_uses_combined_aspect():
    tablet = group_tablets(parse_devices(LIST_DEVICES))[0]
    outs = parse_listmonitors(LIST_MONITORS)  # 3840x1080 combined -> aspect 3.556
    mapping = MappingConfig(output=None, force_proportions=True)
    area = resolve_area(mapping, tablet, outs)
    assert area is not None
    # Letterboxed to the dual-monitor aspect: full width, thin height.
    assert area.aspect == pytest.approx(3840 / 1080, rel=1e-3)
    assert area.x1 == 0 and area.x2 == 44704


def test_force_proportions_single_output():
    tablet = group_tablets(parse_devices(LIST_DEVICES))[0]
    outs = parse_listmonitors(LIST_MONITORS)
    area = resolve_area(MappingConfig(output="DP-4", force_proportions=True), tablet, outs)
    assert area is not None and area.aspect == pytest.approx(1920 / 1080, rel=1e-3)


def test_mapping_commands_include_touch_when_requested():
    tablet = group_tablets(parse_devices(LIST_DEVICES))[0]
    outs = parse_listmonitors(LIST_MONITORS)
    mapping = MappingConfig(output="DP-4", force_proportions=False,
                            area=[0, 0, 44704, 27940], apply_to_touch=True)
    cmds = mapping_commands(mapping, tablet, outs)
    assert "Wacom Intuos Pro M Finger touch" in {c[2] for c in cmds}
