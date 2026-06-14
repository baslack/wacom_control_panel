"""Daemon I/O tests that need evdev — skipped when the optional 'daemon' extra is absent."""

import pytest

pytest.importorskip("evdev")

from evdev import ecodes  # noqa: E402

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
