"""Tests for pen/touch/pad config: serialisation + xsetwacom command building."""

from wacom_panel.backend.devices import group_tablets, parse_devices
from wacom_panel.core.engine import (
    pad_commands,
    parse_pad_buttons,
    pen_commands,
    profile_commands,
    touch_commands,
)
from wacom_panel.core.profile import (
    ButtonAction,
    PadConfig,
    PenConfig,
    Profile,
    TouchConfig,
)

LIST_DEVICES = """\
Wacom Intuos Pro M Pen stylus   \tid: 18\ttype: STYLUS
Wacom Intuos Pro M Pad pad      \tid: 19\ttype: PAD
Wacom Intuos Pro M Finger touch \tid: 20\ttype: TOUCH
Wacom Intuos Pro M Pen eraser   \tid: 24\ttype: ERASER
Wacom Intuos Pro M Pen cursor   \tid: 25\ttype: CURSOR
"""


def _tablet():
    return group_tablets(parse_devices(LIST_DEVICES))[0]


def test_button_action_to_xsetwacom():
    # Mouse buttons must use the held "+N" form so click-and-drag works (a bare "N"
    # expands to "+N -N", an instant click that cannot hold).
    assert ButtonAction("button", "3").to_xsetwacom() == "button +3"
    assert ButtonAction("button", "1").to_xsetwacom() == "button +1"
    assert ButtonAction("key", "ctrl z").to_xsetwacom() == "key ctrl z"
    # Held-modifier form: "+mod" presses on button-down, auto-released on button-up.
    assert ButtonAction("key", "+ctrl +shift").to_xsetwacom() == "key +ctrl +shift"
    assert ButtonAction("disabled", "").to_xsetwacom() == "0"
    assert ButtonAction("button", "").to_xsetwacom() == "0"  # empty -> disabled
    assert ButtonAction("doubleclick", "").to_xsetwacom() == "button +1 -1 +1 -1"


def test_profile_roundtrip_with_all_sections(tmp_path):
    p = Profile(
        name="Art",
        pen=PenConfig(pressure_curve=[10, 0, 90, 100], threshold=40,
                      button3=ButtonAction("key", "ctrl z")),
        touch=TouchConfig(enabled=False, scroll_distance=33),
        pad=PadConfig(buttons={"8": ButtonAction("key", "ctrl shift z"),
                               "9": ButtonAction("button", "2")}),
    )
    path = tmp_path / "p.json"
    p.save(path)
    loaded = Profile.load(path)
    assert loaded.pen.pressure_curve == [10, 0, 90, 100]
    assert loaded.pen.threshold == 40
    assert loaded.pen.button3 == ButtonAction("key", "ctrl z")
    assert loaded.touch.enabled is False
    assert loaded.touch.scroll_distance == 33
    assert loaded.pad.buttons["8"] == ButtonAction("key", "ctrl shift z")
    assert loaded.pad.buttons["9"] == ButtonAction("button", "2")


def test_pen_commands_target_stylus_and_eraser():
    cmds = pen_commands(PenConfig(pressure_curve=[0, 0, 100, 100], threshold=27), _tablet())
    devs = {c[2] for c in cmds}
    assert "Wacom Intuos Pro M Pen stylus" in devs
    assert "Wacom Intuos Pro M Pen eraser" in devs
    # PressureCurve carries the 4 control points.
    curve = next(c for c in cmds if c[3] == "PressureCurve")
    assert curve[4:] == ["0", "0", "100", "100"]
    # Buttons only on the stylus.
    btn_cmds = [c for c in cmds if c[3] == "Button"]
    assert all(c[2] == "Wacom Intuos Pro M Pen stylus" for c in btn_cmds)
    assert len(btn_cmds) == 3


def test_touch_commands():
    cmds = touch_commands(TouchConfig(enabled=False, gestures=True, scroll_distance=20,
                                      zoom_distance=50, tap_time=250), _tablet())
    params = {c[3]: c[4] for c in cmds}
    assert params["Touch"] == "off"
    assert params["Gesture"] == "on"
    assert params["ScrollDistance"] == "20"
    assert all(c[2] == "Wacom Intuos Pro M Finger touch" for c in cmds)


def test_pad_commands_sorted_by_button_number():
    pad = PadConfig(buttons={"13": ButtonAction("button", "13"),
                             "8": ButtonAction("key", "ctrl z")})
    cmds = pad_commands(pad, _tablet())
    nums = [c[4] for c in cmds]  # the button number argument
    assert nums == ["8", "13"]
    assert cmds[0][2] == "Wacom Intuos Pro M Pad pad"
    assert cmds[0][5] == "key ctrl z"


PAD_SHELL_ALL = '''\
xsetwacom set "Wacom Intuos Pro M Pad pad" "Button" "1" "button +1 "
xsetwacom set "Wacom Intuos Pro M Pad pad" "Button" "3" "button +3 "
xsetwacom set "Wacom Intuos Pro M Pad pad" "Button" "8" "key +Control_L +z -z "
xsetwacom set "Wacom Intuos Pro M Pad pad" "Button" "13" "button +13 "
xsetwacom set "Wacom Intuos Pro M Pad pad" "AbsWheelUp" "3" "button +4 -4 "
'''


def test_parse_pad_buttons():
    # Button numbers in order; the AbsWheel line is not a Button and is ignored.
    assert parse_pad_buttons(PAD_SHELL_ALL) == [1, 3, 8, 13]


def test_pad_commands_include_wheel_params():
    pad = PadConfig(
        buttons={"1": ButtonAction("button", "1")},
        wheels={"AbsWheelUp": ButtonAction("button", "4"),
                "AbsWheelDown": ButtonAction("key", "ctrl plus")},
    )
    cmds = pad_commands(pad, _tablet())
    # Wheel commands have the form [bin, --set, dev, Param, action] (no button-number arg).
    wheels = {c[3]: c[4] for c in cmds if c[3] in ("AbsWheelUp", "AbsWheelDown")}
    # Ring ticks are momentary: a full "+N -N" click, not a never-released hold.
    assert wheels["AbsWheelUp"] == "button +4 -4"
    assert wheels["AbsWheelDown"] == "key ctrl plus"
    assert all(c[2] == "Wacom Intuos Pro M Pad pad" for c in cmds)


def test_pad_wheels_roundtrip(tmp_path):
    p = Profile(
        name="Ring",
        pad=PadConfig(wheels={"AbsWheelUp": ButtonAction("key", "ctrl plus")}),
    )
    path = tmp_path / "p.json"
    p.save(path)
    loaded = Profile.load(path)
    assert loaded.pad.wheels["AbsWheelUp"] == ButtonAction("key", "ctrl plus")


def test_profile_commands_combines_all_sections():
    from wacom_panel.backend.displays import parse_listmonitors

    outs = parse_listmonitors(" 0: +*DP-4 1920/510x1080/287+0+0  DP-4\n")
    profile = Profile(name="X", pad=PadConfig(buttons={"8": ButtonAction("button", "1")}))
    cmds = profile_commands(profile, _tablet(), outs)
    params = {c[3] for c in cmds}
    assert {"MapToOutput", "PressureCurve", "Touch", "Button"} <= params
