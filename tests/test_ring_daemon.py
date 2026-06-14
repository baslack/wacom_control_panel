"""Daemon I/O tests that need evdev — skipped when the optional 'daemon' extra is absent."""

import pytest

pytest.importorskip("evdev")

from evdev import ecodes  # noqa: E402

from wacom_panel.core.pad_layout import PadLayout, PadRing  # noqa: E402
from wacom_panel.core.profile import ButtonAction, PadConfig  # noqa: E402
from wacom_panel.daemon.ring_daemon import RingDaemon  # noqa: E402
from wacom_panel.daemon.ring_translator import Emit  # noqa: E402


class _FakeUInput:
    def __init__(self):
        self.writes = []
        self.syns = 0

    def write(self, etype, code, value):
        self.writes.append((etype, code, value))

    def syn(self):
        self.syns += 1


def _daemon_with_fake_ui():
    d = RingDaemon()
    d._ui = _FakeUInput()
    return d


def test_inject_key_taps_press_then_release():
    d = _daemon_with_fake_ui()
    d._inject([Emit("key", "Next")])
    assert d._ui.writes == [
        (ecodes.EV_KEY, ecodes.KEY_PAGEDOWN, 1),
        (ecodes.EV_KEY, ecodes.KEY_PAGEDOWN, 0),
    ]
    assert d._ui.syns == 2  # one after presses, one for the releases


def test_inject_key_chord_releases_in_reverse():
    d = _daemon_with_fake_ui()
    d._inject([Emit("key", "ctrl z")])
    codes = [(c, v) for _t, c, v in d._ui.writes]
    assert codes == [
        (ecodes.KEY_LEFTCTRL, 1),
        (ecodes.KEY_Z, 1),
        (ecodes.KEY_Z, 0),
        (ecodes.KEY_LEFTCTRL, 0),
    ]


def test_inject_unknown_key_writes_nothing():
    d = _daemon_with_fake_ui()
    d._inject([Emit("key", "bogus")])
    assert d._ui.writes == []
    assert d._ui.syns == 0


def test_inject_wheel_still_works():
    d = _daemon_with_fake_ui()
    d._inject([Emit("wheel_hi", -120), Emit("wheel", -1)])
    assert (ecodes.EV_REL, ecodes.REL_WHEEL_HI_RES, -120) in d._ui.writes
    assert (ecodes.EV_REL, ecodes.REL_WHEEL, -1) in d._ui.writes
    assert d._ui.syns == 1  # a single batch syn


# ---- pad grab: express-key injection (Increment 3) -----------------------

# The verified PTH-660 map: BTN_0(256)=centre/mode → 1; BTN_1(257) → 2; BTN_2(258) → 3.
_LAYOUT = PadLayout(
    display_name="test",
    ring=PadRing(center=1, center_label="Mode", modes=4, cw="AbsWheelDown", ccw="AbsWheelUp"),
    evdev_buttons={"BTN_0": 1, "BTN_1": 2, "BTN_2": 3},
)


def _pad_daemon(buttons):
    d = _daemon_with_fake_ui()
    d._layout = _LAYOUT
    return d, PadConfig(buttons=buttons, pad_daemon=True)


def _codes(d):
    return [(c, v) for _t, c, v in d._ui.writes]


def test_pad_button_mouse_press_and_release():
    d, pad = _pad_daemon({"2": ButtonAction("button", "1")})  # top-left key → left click
    d._on_pad_button(ecodes.BTN_1, 1, pad)
    assert (ecodes.BTN_LEFT, 1) in _codes(d)
    d._ui.writes.clear()
    d._on_pad_button(ecodes.BTN_1, 0, pad)  # release injects the up-stroke we remembered
    assert (ecodes.BTN_LEFT, 0) in _codes(d)


def test_pad_button_key_held_until_release():
    d, pad = _pad_daemon({"2": ButtonAction("key", "ctrl")})  # hold Ctrl while pressed
    d._on_pad_button(ecodes.BTN_1, 1, pad)
    assert _codes(d) == [(ecodes.KEY_LEFTCTRL, 1)]  # down only — stays held
    d._ui.writes.clear()
    d._on_pad_button(ecodes.BTN_1, 0, pad)
    assert _codes(d) == [(ecodes.KEY_LEFTCTRL, 0)]


def test_pad_button_doubleclick():
    d, pad = _pad_daemon({"2": ButtonAction("doubleclick", "")})
    d._on_pad_button(ecodes.BTN_1, 1, pad)
    assert _codes(d) == [
        (ecodes.BTN_LEFT, 1), (ecodes.BTN_LEFT, 0),
        (ecodes.BTN_LEFT, 1), (ecodes.BTN_LEFT, 0),
    ]
    d._ui.writes.clear()
    d._on_pad_button(ecodes.BTN_1, 0, pad)  # nothing held → release is a no-op
    assert _codes(d) == []


def test_pad_button_scroll_tick():
    d, pad = _pad_daemon({"2": ButtonAction("button", "4")})  # xsetwacom 4 == wheel up
    d._on_pad_button(ecodes.BTN_1, 1, pad)
    assert _codes(d) == [(ecodes.REL_WHEEL, 1)]
    d._ui.writes.clear()
    d._on_pad_button(ecodes.BTN_1, 0, pad)  # a tick has no held state to release
    assert _codes(d) == []


def test_pad_button_disabled_injects_nothing():
    d, pad = _pad_daemon({"2": ButtonAction("disabled", "")})
    d._on_pad_button(ecodes.BTN_1, 1, pad)
    assert d._ui.writes == []


def test_pad_centre_button_is_never_injected():
    # Even if the centre (number 1) carries an action, it must stay the hardware mode switch.
    d, pad = _pad_daemon({"1": ButtonAction("button", "1")})
    d._on_pad_button(ecodes.BTN_0, 1, pad)
    assert d._ui.writes == []


def test_pad_autorepeat_ignored():
    d, pad = _pad_daemon({"2": ButtonAction("button", "1")})
    d._on_pad_button(ecodes.BTN_1, 2, pad)  # kernel autorepeat
    assert d._ui.writes == []
