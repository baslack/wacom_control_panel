"""Live capture of pad button presses for the setup wizard.

The wizard learns a tablet's layout by asking the user to press each key and watching what fires.
Two independent signals are captured per physical press:

* the **xsetwacom button number** — read from ``xinput test-xi2 --root`` ``RawButtonPress`` events.
  *Raw* (root) events are required: per-device ``xinput test-xi2 <id>`` does not deliver pad
  button events, and raw events report the button regardless of how it is bound. Because raw
  button events only fire when the key is *button*-emitting (not bound to a keystroke), the wizard
  resets the pad to button-emitting before capturing (see ``reset_buttons_command``).
* the **evdev ``BTN_*`` code** — read from the pad's evdev node (for the ``pad_daemon`` feature).
  Best-effort: needs the ``input`` group, which the GUI process often lacks.

This module is pure parsing + small helpers; the Qt event-loop wiring (``QProcess`` for xinput,
``QSocketNotifier`` for the evdev fd) lives in :class:`wacom_panel.ui.viewmodels.TabletSetupVM`.
"""

from __future__ import annotations

import re

# RawButtonPress block lines (see tests for a real captured sample):
#     EVENT type 15 (RawButtonPress)
#         device: 2 (19)        <- the (19) is the *source* (slave) device id
#         detail: 2             <- the xsetwacom button number
_EVENT_RE = re.compile(r"EVENT type \d+ \((\w+)\)")
_DEVICE_RE = re.compile(r"device:\s+\d+\s+\((\d+)\)")
_DETAIL_RE = re.compile(r"detail:\s+(\d+)")


class Xi2ButtonParser:
    """Feed ``xinput test-xi2 --root`` lines; yields the xsetwacom button number per press.

    Stateful across the few lines of a ``RawButtonPress`` block. Only presses from the target pad
    device id are reported; everything else (motion, other devices, releases) is ignored.
    """

    def __init__(self, device_id: int) -> None:
        self._device_id = device_id
        self._in_press = False
        self._dev_matches = False

    def feed(self, line: str) -> int | None:
        event = _EVENT_RE.search(line)
        if event is not None:
            # A new event block starts; we only care about RawButtonPress.
            self._in_press = event.group(1) == "RawButtonPress"
            self._dev_matches = False
            return None
        if not self._in_press:
            return None
        device = _DEVICE_RE.search(line)
        if device is not None:
            self._dev_matches = int(device.group(1)) == self._device_id
            return None
        detail = _DETAIL_RE.search(line)
        if detail is not None and self._dev_matches:
            self._in_press = False  # block consumed
            return int(detail.group(1))
        return None


def xinput_capture_command() -> list[str]:
    """argv for the raw-event capture the wizard runs via ``QProcess``."""
    return ["xinput", "test-xi2", "--root"]


def reset_buttons_command(device_name: str, numbers: list[int]) -> list[list[str]]:
    """xsetwacom argv to make each pad button emit its own button event (so raw capture sees it).

    Called before capture so a previously key-bound pad still reports button numbers. Transient —
    the user's real bindings return on the next Apply.
    """
    return [
        ["xsetwacom", "--set", device_name, "Button", str(n), "button", str(n)]
        for n in numbers
    ]
