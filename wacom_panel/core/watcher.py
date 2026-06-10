"""Reapply the active profile when the Wacom device (re)appears.

Prefers a userspace ``pyudev`` netlink monitor (event-driven, no polling, no root). If
``pyudev`` is unavailable it falls back to polling ``xsetwacom --list devices``. Either way
this runs as a ``systemd --user`` service — see :mod:`wacom_panel.core.persistence`.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ..backend import devices, displays
from ..backend.xsetwacom import XsetwacomError
from .engine import apply_profile
from .store import ProfileStore

# Settle delay: a tablet exposes several sub-devices in quick succession on plug-in.
_DEBOUNCE_S = 1.0
_POLL_INTERVAL_S = 3.0


def apply_active(store: ProfileStore | None = None) -> bool:
    """Apply the active profile's mapping to the first detected tablet. True if applied."""
    store = store or ProfileStore()
    profile = store.active_profile()
    if profile is None:
        return False
    tablets = devices.list_tablets()
    if not tablets:
        return False
    try:
        apply_profile(profile, tablets[0], displays.list_outputs(), dry_run=False)
    except XsetwacomError:
        return False
    return True


def _wacom_present() -> bool:
    try:
        return bool(devices.list_tablets())
    except XsetwacomError:
        return False


def watch(store: ProfileStore | None = None, *, log: Callable[[str], None] = print) -> int:
    """Block forever, reapplying the active profile whenever a Wacom device appears."""
    store = store or ProfileStore()
    if apply_active(store):
        log("Applied active profile on startup.")

    try:
        import pyudev
    except ImportError:
        log("pyudev not available; falling back to polling.")
        return _watch_polling(store, log=log)

    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="input")
    log("Watching for Wacom hotplug via udev.")
    for device in iter(monitor.poll, None):
        if device.action != "add":
            continue
        if not _is_wacom(device):
            continue
        time.sleep(_DEBOUNCE_S)
        if apply_active(store):
            log("Reapplied active profile after hotplug.")
    return 0


def _is_wacom(device) -> bool:
    name = (device.get("NAME", "") or device.sys_name or "").lower()
    return "wacom" in name or device.get("ID_INPUT_TABLET") == "1"


def _watch_polling(store: ProfileStore, *, log: Callable[[str], None]) -> int:
    present = _wacom_present()
    while True:
        time.sleep(_POLL_INTERVAL_S)
        now = _wacom_present()
        if now and not present:  # absent -> present transition
            time.sleep(_DEBOUNCE_S)
            if apply_active(store):
                log("Reapplied active profile after device appeared (polling).")
        present = now
