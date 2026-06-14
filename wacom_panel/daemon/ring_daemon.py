"""The touch-ring daemon: read raw ring events, inject real scroll.

Thin I/O around the pure :class:`~wacom_panel.daemon.ring_translator.RingTranslator`. It reads
the pad's ``ABS_WHEEL`` via ``evdev`` (no exclusive grab, so the express keys keep working
through ``xsetwacom``), looks up the current LED mode from sysfs, and injects ``REL_WHEEL`` via
``uinput``. Config comes from the active profile (same source as the hotplug watcher); a
``SIGHUP`` reloads it, ``SIGTERM`` shuts down cleanly, and an unplugged tablet is re-acquired.

``evdev`` is an optional dependency (the ``daemon`` extra). If it is missing the daemon refuses
to start with a clear message rather than crashing — exactly like the optional ``pyudev`` path
in :mod:`wacom_panel.core.watcher`.
"""

from __future__ import annotations

import glob
import selectors
import signal
import sys
import time
from pathlib import Path

from ..core.pad_layout import PadLayout, load_layout
from ..core.profile import ButtonAction, PadConfig
from ..core.store import ProfileStore
from . import keymap
from .ring_translator import Emit, RingTranslator, ScrollSmoother

try:  # optional dependency: the "daemon" extra
    import evdev
    from evdev import ecodes
except ImportError:  # pragma: no cover - exercised via is_available()
    evdev = None
    ecodes = None

# How often the read loop wakes to re-check the reload/stop flags when the ring is idle.
_TICK_S = 0.5
# Fast cadence while paying out queued scroll, so smoothing runs well above the ~33 Hz ring.
_PAYOUT_S = 0.006
# Pause before re-scanning for the pad device when it is absent (unplugged / not yet ready).
_RECONNECT_S = 2.0

_LED_GLOB = "/sys/bus/hid/drivers/wacom/*/wacom_led/status_led0_select"


def is_available() -> bool:
    """True when ``python-evdev`` is importable (the daemon can run)."""
    return evdev is not None


def find_pad_device():
    """The pad's evdev node (has a touch ring), or ``None``. Skips nodes we can't open."""
    if evdev is None:
        return None
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue  # no permission / vanished — keep looking
        name = (dev.name or "").lower()
        abs_codes = [code for code, _ in dev.capabilities().get(ecodes.EV_ABS, [])]
        if "wacom" in name and "pad" in name and ecodes.ABS_WHEEL in abs_codes:
            return dev
        dev.close()
    return None


def find_led_select() -> Path | None:
    """Path of the active-mode sysfs file, discovered by glob (the HID id varies per unit)."""
    matches = sorted(glob.glob(_LED_GLOB))
    return Path(matches[0]) if matches else None


def read_mode(led_path: Path | None) -> int:
    """Current LED/ring mode index (0-based); 0 if unreadable."""
    if led_path is None:
        return 0
    try:
        return int(led_path.read_text().strip())
    except (OSError, ValueError):
        return 0


def _ring_max(dev) -> int:
    for code, info in dev.capabilities().get(ecodes.EV_ABS, []):
        if code == ecodes.ABS_WHEEL:
            return info.max or 71
    return 71


class RingDaemon:
    """Owns the uinput device and the read loop."""

    def __init__(self, store: ProfileStore | None = None) -> None:
        self._store = store or ProfileStore()
        self._ui = None
        self._stop = False
        self._reload = True
        self._translator = RingTranslator()
        self._smoother = ScrollSmoother()
        self._warned: set[str] = set()
        # Pad-grab (Increment 3) state.
        self._layout = PadLayout(display_name="")  # set per bound device
        self._grabbed = False
        # While the daemon owns the pad, each held express key remembers the events to emit on
        # release (so a held button = real click-and-drag / held modifier), keyed by evdev code.
        self._held: dict[int, list[tuple[int, int, int]]] = {}

    # ---- config ----------------------------------------------------------
    def _load_pad(self) -> PadConfig:
        profile = self._store.active_profile()
        pad = profile.pad if profile is not None else PadConfig()
        self._translator.set_modes(pad.ring_modes)
        self._translator.reset()
        return pad

    # ---- injection -------------------------------------------------------
    def _inject(self, emits: list[Emit]) -> None:
        wrote = False
        for e in emits:
            if e.kind == "wheel":
                self._ui.write(ecodes.EV_REL, ecodes.REL_WHEEL, int(e.value))
                wrote = True
            elif e.kind == "wheel_hi":
                self._ui.write(ecodes.EV_REL, ecodes.REL_WHEEL_HI_RES, int(e.value))
                wrote = True
            elif e.kind == "key":
                wrote = self._tap_key(str(e.value)) or wrote
        if wrote:
            self._ui.syn()

    def _tap_key(self, combo: str) -> bool:
        """Press then release a key chord (e.g. ``"Next"``, ``"ctrl z"``). True if anything fired.

        Presses are synced before the releases so the chord registers as a real keystroke rather
        than a single simultaneous press+release report.
        """
        presses, releases = keymap.to_chord(combo)
        if not presses:
            if combo not in self._warned:
                self._warned.add(combo)
                print(f"ring daemon: no evdev keys for ring action {combo!r}; ignoring.",
                      file=sys.stderr)
            return False
        for name in presses:
            self._ui.write(ecodes.EV_KEY, ecodes.ecodes[name], 1)
        self._ui.syn()
        for name in releases:
            self._ui.write(ecodes.EV_KEY, ecodes.ecodes[name], 0)
        return True  # caller syns the releases

    # ---- pad grab (Increment 3) -----------------------------------------
    def _apply_grab(self, dev, want: bool) -> None:
        """Match the exclusive grab to ``want`` — grabbing diverts the express keys to us."""
        if want and not self._grabbed:
            try:
                dev.grab()
            except OSError as exc:
                print(f"ring daemon: could not grab the pad ({exc}); express keys stay on "
                      "xsetwacom.", file=sys.stderr)
                return
            self._grabbed = True
            print("ring daemon: grabbed the pad — the daemon now drives the express keys.")
        elif not want and self._grabbed:
            self._release_all()
            try:
                dev.ungrab()
            except OSError:
                pass
            self._grabbed = False
            print("ring daemon: released the pad — express keys fall back to xsetwacom.")

    def _release_all(self) -> None:
        """Release any express keys still held (on ungrab / shutdown), so nothing sticks down."""
        if not self._held:
            return
        for events in self._held.values():
            for etype, code, value in events:
                self._ui.write(etype, code, value)
        self._held.clear()
        self._ui.syn()

    def _on_pad_button(self, code: int, value: int, pad: PadConfig) -> None:
        """Handle one grabbed express-key event (``value`` 1=down, 0=up, 2=autorepeat)."""
        if value == 2:  # ignore kernel autorepeat; held semantics come from our own press/release
            return
        if value == 0:
            self._release_button(code)
            return
        action = self._action_for(code, pad)
        if action is not None:
            self._press_button(code, action)

    def _action_for(self, code: int, pad: PadConfig) -> ButtonAction | None:
        """The configured action for a raw evdev button code, or ``None`` to inject nothing.

        ``None`` covers: unmapped codes, the centre/mode button (must stay the hardware mode
        switch), and explicitly disabled buttons.
        """
        name = ecodes.BTN.get(code)
        if isinstance(name, (list, tuple)):
            name = next((n for n in name if n in self._layout.evdev_buttons), name[0])
        number = self._layout.evdev_buttons.get(name)
        if number is None:
            return None
        if self._layout.ring is not None and number == self._layout.ring.center:
            return None  # centre button cycles the LED modes in hardware — never re-inject it
        action = pad.buttons.get(str(number))
        if action is None or action.kind == "disabled":
            return None
        return action

    def _press_button(self, code: int, action: ButtonAction) -> None:
        """Inject the down-stroke for an express key and remember what to release on up."""
        kind = action.kind
        if kind == "key":
            presses, releases = keymap.to_chord(action.value)
            if not presses:
                return
            for name in presses:
                self._ui.write(ecodes.EV_KEY, ecodes.ecodes[name], 1)
            self._held[code] = [(ecodes.EV_KEY, ecodes.ecodes[name], 0) for name in releases]
            self._ui.syn()
        elif kind == "doubleclick":
            for v in (1, 0, 1, 0):
                self._ui.write(ecodes.EV_KEY, ecodes.BTN_LEFT, v)
            self._ui.syn()
        elif kind in ("button", "scroll"):
            scroll = self._scroll_delta(action)
            if scroll is not None:
                self._ui.write(ecodes.EV_REL, ecodes.REL_WHEEL, scroll)
                self._ui.syn()
                return
            btn = keymap.resolve_button(int(action.value)) if action.value.isdigit() else None
            if btn is None:
                return
            ecode = ecodes.ecodes[btn]
            self._ui.write(ecodes.EV_KEY, ecode, 1)
            self._held[code] = [(ecodes.EV_KEY, ecode, 0)]
            self._ui.syn()

    @staticmethod
    def _scroll_delta(action: ButtonAction) -> int | None:
        """REL_WHEEL delta for a scroll-ish action, else ``None`` (it's a real button/key)."""
        if action.kind == "scroll":
            return 1 if action.value.strip() == "up" else -1
        if action.kind == "button" and action.value.isdigit():
            return keymap.BUTTON_TO_SCROLL.get(int(action.value))
        return None

    def _release_button(self, code: int) -> None:
        events = self._held.pop(code, None)
        if not events:
            return
        for etype, ecode, value in events:
            self._ui.write(etype, ecode, value)
        self._ui.syn()

    # ---- loop ------------------------------------------------------------
    def run(self) -> int:
        if evdev is None:
            print("python-evdev not installed; cannot run the ring daemon. "
                  "Install the 'daemon' extra: pip install -e '.[daemon]'", file=sys.stderr)
            return 1

        signal.signal(signal.SIGHUP, lambda *_: setattr(self, "_reload", True))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "_stop", True))

        try:
            self._ui = evdev.UInput(
                name="wacom-control-panel-ring",
                events={
                    ecodes.EV_REL: [ecodes.REL_WHEEL, ecodes.REL_WHEEL_HI_RES],
                    # Advertise every key the keymap can emit, so per-mode "key" ring actions
                    # (Page Down/Up, Undo, …) and grabbed express keys inject as real keystrokes,
                    # plus the mouse buttons the pad-grab feature injects (left/right/middle/…).
                    ecodes.EV_KEY: [
                        ecodes.ecodes[n]
                        for n in keymap.supported_evdev_names() | keymap.supported_buttons()
                    ],
                },
            )
        except OSError as exc:
            print(f"ring daemon: cannot open /dev/uinput ({exc}). "
                  "Run 'wacom-panel --install-ring-daemon' to grant access.", file=sys.stderr)
            return 1

        print("ring daemon: started.")
        try:
            while not self._stop:
                dev = find_pad_device()
                if dev is None:
                    time.sleep(_RECONNECT_S)
                    continue
                self._translator = RingTranslator(ring_max=_ring_max(dev))
                self._smoother.reset()
                self._reload = True
                self._grabbed = False  # fresh fd; a prior grab died with the old device
                self._held.clear()
                self._layout = load_layout(dev.name, [])
                print(f"ring daemon: bound to {dev.name}.")
                try:
                    self._serve(dev, find_led_select())
                except OSError:
                    print("ring daemon: pad disconnected; waiting to re-acquire.")
                finally:
                    dev.close()  # closing the fd releases any EVIOCGRAB automatically
        finally:
            self._ui.close()
        print("ring daemon: stopped.")
        return 0

    def _serve(self, dev, led: Path | None) -> None:
        sel = selectors.DefaultSelector()
        sel.register(dev.fileno(), selectors.EVENT_READ)
        pad = self._load_pad()
        self._apply_grab(dev, pad.pad_daemon)
        try:
            while not self._stop:
                if self._reload:
                    pad = self._load_pad()
                    self._apply_grab(dev, pad.pad_daemon)  # honour a pad_daemon change on SIGHUP
                    self._reload = False
                # Drain queued scroll on a fast cadence; idle cheaply when nothing's pending.
                timeout = _PAYOUT_S if self._smoother.busy() else _TICK_S
                if sel.select(timeout=timeout):
                    # Read the LED mode once per batch (it only changes on a centre-button press),
                    # not once per event — a sysfs open/read per wheel tick adds needless latency.
                    mode = read_mode(led) if pad.ring_daemon else 0
                    for event in dev.read():
                        if event.type == ecodes.EV_ABS and event.code == ecodes.ABS_WHEEL:
                            if not pad.ring_daemon:
                                continue  # ring driven by xsetwacom keystrokes; daemon stays out
                            for emit in self._translator.on_value(event.value, mode):
                                if emit.kind == "wheel_hi":
                                    self._smoother.add(int(emit.value))
                                else:
                                    self._inject([emit])  # key actions fire immediately
                        elif event.type == ecodes.EV_KEY and pad.pad_daemon:
                            self._on_pad_button(event.code, event.value, pad)
                # Pay out a smoothed slice of any pending scroll.
                self._inject(self._smoother.tick())
        finally:
            self._apply_grab(dev, False)  # always release the pad when leaving this device


def run(store: ProfileStore | None = None) -> int:
    """Entry point used by ``wacom-panel --ring-daemon``."""
    return RingDaemon(store).run()
