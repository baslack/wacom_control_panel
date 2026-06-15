"""QObject view-models that expose the (Qt-free) core to QML.

QML binds to :class:`Controller` (set as the ``controller`` context property). The mapping
fields live on :attr:`Controller.mapping` (a :class:`MappingVM`); profile and action methods
live on the controller itself. All UI logic stays here; ``core`` stays pure.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Property, QObject, QProcess, QSocketNotifier, QTimer, Signal, Slot

from ..backend import devices, displays, xsetwacom
from ..core import libwacom_db, pad_capture, tablet_setup
from ..core.engine import (
    apply_profile,
    detect_pad_buttons,
    resolve_area,
    tablet_native_area,
)
from ..core.mapping import ANCHORS, ROTATIONS, Area
from ..core.pad_layout import PadLayout, load_layout, save_user_layout
from ..core.persistence import Persistence
from ..core.pressure_presets import PressurePresetStore
from ..core.profile import (
    ButtonAction,
    MappingConfig,
    PadConfig,
    PenConfig,
    Profile,
    RingMode,
    TouchConfig,
)
from ..core.ring_setup import RingSetup
from ..core.store import ProfileStore
from ..daemon import ring_daemon

_WHOLE_DESKTOP = "Whole desktop"


class MappingVM(QObject):
    """Editable view of a :class:`MappingConfig`, bound to the mapping controls + canvases."""

    changed = Signal()  # NOTIFY for all scalar properties
    areaChanged = Signal()  # emitted specifically when the active area changes

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._m = MappingConfig()
        self._tablet = None
        self._outputs: list[displays.Output] = []
        self._tablet_size = (44704, 27940)
        self._suppress = False

    # ---- context / load --------------------------------------------------
    def set_context(self, tablet, outputs: list[displays.Output]) -> None:
        self._tablet = tablet
        self._outputs = outputs
        if tablet is not None:
            self._tablet_size = tablet_native_area(tablet)
        self.changed.emit()
        self.areaChanged.emit()

    def load(self, mapping: MappingConfig) -> None:
        self._m = mapping
        self._recompute()
        self.changed.emit()
        self.areaChanged.emit()

    def to_mapping(self) -> MappingConfig:
        return self._m

    # ---- recompute -------------------------------------------------------
    def _recompute(self) -> None:
        if not self._m.force_proportions:
            return
        area = resolve_area(self._m, self._tablet, self._outputs)
        if area is not None:
            self._suppress = True
            self._m.set_area(area)
            self._suppress = False
            self.areaChanged.emit()

    # ---- output selection ------------------------------------------------
    def _get_output_names(self) -> list[str]:
        return [_WHOLE_DESKTOP] + [f"{o.name} ({o.width}×{o.height})" for o in self._outputs]

    outputNames = Property("QStringList", _get_output_names, notify=changed)

    def _get_output_index(self) -> int:
        if not self._m.output:
            return 0
        for i, o in enumerate(self._outputs):
            if o.name == self._m.output:
                return i + 1
        return 0

    def _set_output_index(self, idx: int) -> None:
        name = None if idx <= 0 else self._outputs[idx - 1].name
        if name != self._m.output:
            self._m.output = name
            self._recompute()
            self.changed.emit()

    outputIndex = Property(int, _get_output_index, _set_output_index, notify=changed)

    @Slot(str)
    def selectOutputByName(self, name: str) -> None:
        for i, o in enumerate(self._outputs):
            if o.name == name:
                self._set_output_index(i + 1)
                return
        self._set_output_index(0)

    def _get_selected_output(self) -> str:
        return self._m.output or ""

    selectedOutput = Property(str, _get_selected_output, notify=changed)

    # ---- canvas geometry (device units) ----------------------------------
    def _get_output_rects(self) -> list:
        sel = self._m.output
        return [
            {
                "name": o.name, "x": o.x, "y": o.y,
                "width": o.width, "height": o.height,
                "primary": o.primary,
                "selected": (sel is None) or (o.name == sel),
            }
            for o in self._outputs
        ]

    outputRects = Property("QVariantList", _get_output_rects, notify=changed)

    def _get_desktop_bounds(self) -> dict:
        x, y, w, h = displays.desktop_bounds(self._outputs)
        return {"x": x, "y": y, "width": w, "height": h}

    desktopBounds = Property("QVariantMap", _get_desktop_bounds, notify=changed)

    tabletWidth = Property(int, lambda self: self._tablet_size[0], notify=changed)
    tabletHeight = Property(int, lambda self: self._tablet_size[1], notify=changed)

    # ---- area ------------------------------------------------------------
    def _area(self) -> Area:
        return self._m.area_obj or Area(0, 0, *self._tablet_size)

    areaX1 = Property(int, lambda self: self._area().x1, notify=areaChanged)
    areaY1 = Property(int, lambda self: self._area().y1, notify=areaChanged)
    areaX2 = Property(int, lambda self: self._area().x2, notify=areaChanged)
    areaY2 = Property(int, lambda self: self._area().y2, notify=areaChanged)

    @Slot(int, int, int, int)
    def setAreaFromCanvas(self, x1: int, y1: int, x2: int, y2: int) -> None:
        # Direct user override (drag/resize): store as-is, no re-fit.
        self._m.set_area(Area(x1, y1, x2, y2))
        if not self._suppress:
            self.areaChanged.emit()

    @Slot(int)
    def setAreaX1(self, v: int) -> None:
        self._set_area_field(0, v)

    @Slot(int)
    def setAreaY1(self, v: int) -> None:
        self._set_area_field(1, v)

    @Slot(int)
    def setAreaX2(self, v: int) -> None:
        self._set_area_field(2, v)

    @Slot(int)
    def setAreaY2(self, v: int) -> None:
        self._set_area_field(3, v)

    def _set_area_field(self, idx: int, v: int) -> None:
        a = self._area().as_list()
        a[idx] = v
        self._m.set_area(Area(*a))
        self.areaChanged.emit()

    # ---- scalar options --------------------------------------------------
    def _get_force(self) -> bool:
        return self._m.force_proportions

    def _set_force(self, v: bool) -> None:
        if v != self._m.force_proportions:
            self._m.force_proportions = v
            self._recompute()
            self.changed.emit()

    forceProportions = Property(bool, _get_force, _set_force, notify=changed)

    def _make_choice_prop(attr, choices, recompute):  # noqa: N805
        def getter(self):
            return getattr(self._m, attr)

        def setter(self, v):
            if v in choices and v != getattr(self._m, attr):
                setattr(self._m, attr, v)
                if recompute:
                    self._recompute()
                self.changed.emit()

        return getter, setter

    _rot_get, _rot_set = _make_choice_prop("rotate", ROTATIONS, True)
    rotate = Property(str, _rot_get, _rot_set, notify=changed)
    _mode_get, _mode_set = _make_choice_prop("mode", ("Absolute", "Relative"), False)
    mode = Property(str, _mode_get, _mode_set, notify=changed)
    _anc_get, _anc_set = _make_choice_prop("anchor", ANCHORS, True)
    anchor = Property(str, _anc_get, _anc_set, notify=changed)

    rotations = Property("QStringList", lambda self: list(ROTATIONS), constant=True)
    anchors = Property("QStringList", lambda self: list(ANCHORS), constant=True)
    modes = Property("QStringList", lambda self: ["Absolute", "Relative"], constant=True)

    def _get_zoom_pct(self) -> int:
        return int(round(self._m.zoom * 100))

    def _set_zoom_pct(self, v: int) -> None:
        z = max(0.1, min(1.0, v / 100.0))
        if abs(z - self._m.zoom) > 1e-6:
            self._m.zoom = z
            self._recompute()
            self.changed.emit()

    zoomPercent = Property(int, _get_zoom_pct, _set_zoom_pct, notify=changed)

    def _get_touch(self) -> bool:
        return self._m.apply_to_touch

    def _set_touch(self, v: bool) -> None:
        if v != self._m.apply_to_touch:
            self._m.apply_to_touch = v
            self.changed.emit()

    applyToTouch = Property(bool, _get_touch, _set_touch, notify=changed)


class PenVM(QObject):
    """Editable view of :class:`PenConfig` (pressure curve, threshold, pen buttons)."""

    changed = Signal()
    presetsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._p = PenConfig()
        self._presets: PressurePresetStore | None = None

    def set_preset_store(self, store: PressurePresetStore) -> None:
        self._presets = store
        self.presetsChanged.emit()

    def load(self, pen: PenConfig) -> None:
        self._p = pen
        self.changed.emit()

    def to_config(self) -> PenConfig:
        return self._p

    # ---- pressure presets ------------------------------------------------
    presetNames = Property(
        "QStringList",
        lambda self: self._presets.names() if self._presets else [],
        notify=presetsChanged,
    )

    @Slot(str)
    def applyPreset(self, name: str) -> None:
        if self._presets is None:
            return
        points = self._presets.get(name)
        if points:
            self._p.pressure_curve = list(points)
            self.changed.emit()

    @Slot(str)
    def savePreset(self, name: str) -> None:
        if self._presets and self._presets.save(name, list(self._p.pressure_curve)):
            self.presetsChanged.emit()

    @Slot(str)
    def deletePreset(self, name: str) -> None:
        if self._presets:
            self._presets.delete(name)
            self.presetsChanged.emit()

    @Slot(str, result=bool)
    def canDeletePreset(self, name: str) -> bool:
        return bool(name) and self._presets is not None and not self._presets.is_builtin(name)

    def _curve_get(idx):  # noqa: N805
        return lambda self: self._p.pressure_curve[idx]

    def _curve_set(idx):  # noqa: N805
        def setter(self, v):
            v = max(0, min(100, int(v)))
            if self._p.pressure_curve[idx] != v:
                self._p.pressure_curve[idx] = v
                self.changed.emit()
        return setter

    p1x = Property(int, _curve_get(0), _curve_set(0), notify=changed)
    p1y = Property(int, _curve_get(1), _curve_set(1), notify=changed)
    p2x = Property(int, _curve_get(2), _curve_set(2), notify=changed)
    p2y = Property(int, _curve_get(3), _curve_set(3), notify=changed)

    def _get_threshold(self) -> int:
        return self._p.threshold

    def _set_threshold(self, v: int) -> None:
        v = max(0, min(2047, int(v)))
        if self._p.threshold != v:
            self._p.threshold = v
            self.changed.emit()

    threshold = Property(int, _get_threshold, _set_threshold, notify=changed)

    def _kind(num):  # noqa: N805
        return lambda self: getattr(self._p, f"button{num}").kind

    def _value(num):  # noqa: N805
        return lambda self: getattr(self._p, f"button{num}").value

    button1Kind = Property(str, _kind(1), notify=changed)
    button1Value = Property(str, _value(1), notify=changed)
    button2Kind = Property(str, _kind(2), notify=changed)
    button2Value = Property(str, _value(2), notify=changed)
    button3Kind = Property(str, _kind(3), notify=changed)
    button3Value = Property(str, _value(3), notify=changed)

    @Slot(int, str, str)
    def setButton(self, num: int, kind: str, value: str) -> None:
        if num in (1, 2, 3):
            setattr(self._p, f"button{num}", ButtonAction(kind=kind, value=value))
            self.changed.emit()


class TouchVM(QObject):
    """Editable view of :class:`TouchConfig`."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._t = TouchConfig()

    def load(self, touch: TouchConfig) -> None:
        self._t = touch
        self.changed.emit()

    def to_config(self) -> TouchConfig:
        return self._t

    def _bool_prop(attr):  # noqa: N805
        def getter(self):
            return getattr(self._t, attr)

        def setter(self, v):
            if getattr(self._t, attr) != bool(v):
                setattr(self._t, attr, bool(v))
                self.changed.emit()

        return getter, setter

    def _int_prop(attr, lo, hi):  # noqa: N805
        def getter(self):
            return getattr(self._t, attr)

        def setter(self, v):
            v = max(lo, min(hi, int(v)))
            if getattr(self._t, attr) != v:
                setattr(self._t, attr, v)
                self.changed.emit()

        return getter, setter

    _en_g, _en_s = _bool_prop("enabled")
    enabled = Property(bool, _en_g, _en_s, notify=changed)
    _ge_g, _ge_s = _bool_prop("gestures")
    gestures = Property(bool, _ge_g, _ge_s, notify=changed)
    _sd_g, _sd_s = _int_prop("scroll_distance", 1, 500)
    scrollDistance = Property(int, _sd_g, _sd_s, notify=changed)
    _zd_g, _zd_s = _int_prop("zoom_distance", 1, 500)
    zoomDistance = Property(int, _zd_g, _zd_s, notify=changed)
    _tt_g, _tt_s = _int_prop("tap_time", 0, 1000)
    tapTime = Property(int, _tt_g, _tt_s, notify=changed)


class PadVM(QObject):
    """Editable view of :class:`PadConfig`, arranged by the tablet's physical pad layout."""

    changed = Signal()
    ringDaemonStatusChanged = Signal()  # the daemon's readiness changed (toggle / refresh)
    ringModeChanged = Signal()  # the tablet's live LED mode changed (polled from sysfs)

    # Default touch-ring actions. Pad buttons only emit keystrokes on X (mouse-button /
    # scroll-wheel actions silently fail), so the ring scrolls via arrow keys — one line per
    # detent. cw (clockwise) scrolls down, ccw scrolls up.
    _WHEEL_DEFAULTS = {"cw": ("key", "Down"), "ccw": ("key", "Up")}

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cfg = PadConfig()
        self._layout: PadLayout = load_layout("", [])
        self._ring_setup = RingSetup()
        self._ring_ready = False
        self._ring_status = ""
        self._active_ring_mode = 0  # the tablet's current LED mode (polled live); the editor
                                    # always edits this mode — selection follows the hardware.
        self._led_path = None       # cached sysfs LED-select path (globbed once)
        self._led_resolved = False

    def set_context(self, tablet) -> None:
        numbers = detect_pad_buttons(tablet) if tablet is not None else []
        name = tablet.name if tablet is not None else ""
        self._layout = load_layout(name, numbers)
        self.changed.emit()

    def load(self, pad: PadConfig) -> None:
        self._cfg = pad
        self.changed.emit()

    def to_config(self) -> PadConfig:
        # Materialise the ring's effective actions so Apply/Save always set the wheel, even
        # if the user never touched it (otherwise the ring keeps whatever stale driver state).
        if self._layout.ring is not None:
            for direction in ("cw", "ccw"):
                param = self._wheel_param(direction)
                if param and param not in self._cfg.wheels:
                    self._cfg.wheels[param] = self._wheel_action(direction)
        # Drop trailing all-default ring modes so an untouched profile stays `ring_modes: []`
        # (the daemon treats a missing/short entry as default scroll anyway).
        while self._cfg.ring_modes and self._cfg.ring_modes[-1] == RingMode():
            self._cfg.ring_modes.pop()
        return self._cfg

    def reload_daemon(self) -> None:
        """Ask the running ring daemon to re-read the saved profile (called after a Save)."""
        if self._cfg.ring_daemon and self._ring_setup.is_active():
            self._ring_setup.reload()

    # ---- helpers ---------------------------------------------------------
    def _button_action(self, num: int) -> ButtonAction:
        # Unset pad keys default to disabled: their hardware mouse-button default does
        # nothing useful on X (pad buttons can only emit keystrokes), so don't pretend.
        return self._cfg.buttons.get(str(num)) or ButtonAction("disabled", "")

    def _key_model(self, keys) -> list:
        out = []
        for key in keys:
            action = self._button_action(key.button)
            out.append({
                "num": key.button, "label": key.label,
                "kind": action.kind, "value": action.value,
            })
        return out

    def _wheel_param(self, direction: str) -> str | None:
        if self._layout.ring is None:
            return None
        return self._layout.ring.cw if direction == "cw" else self._layout.ring.ccw

    def _wheel_action(self, direction: str) -> ButtonAction:
        param = self._wheel_param(direction)
        if param and param in self._cfg.wheels:
            return self._cfg.wheels[param]
        kind, value = self._WHEEL_DEFAULTS[direction]
        return ButtonAction(kind, value)

    # ---- exposed structure ----------------------------------------------
    hasPad = Property(bool, lambda self: bool(self._layout.all_buttons), notify=changed)
    layoutMatched = Property(bool, lambda self: self._layout.matched, notify=changed)
    displayName = Property(str, lambda self: self._layout.display_name, notify=changed)

    topKeys = Property("QVariantList", lambda self: self._key_model(self._layout.top_keys),
                       notify=changed)
    bottomKeys = Property("QVariantList", lambda self: self._key_model(self._layout.bottom_keys),
                          notify=changed)

    hasRing = Property(bool, lambda self: self._layout.ring is not None, notify=changed)
    ringModes = Property(int, lambda self: self._layout.ring.modes if self._layout.ring else 0,
                         notify=changed)
    ringCenterNum = Property(
        int,
        lambda self: self._layout.ring.center if self._layout.ring and self._layout.ring.center
        else -1,
        notify=changed,
    )
    ringCenterLabel = Property(
        str, lambda self: self._layout.ring.center_label if self._layout.ring else "",
        notify=changed,
    )

    def _center_action(self) -> ButtonAction:
        num = self._layout.ring.center if self._layout.ring else None
        return self._button_action(num) if num is not None else ButtonAction("disabled", "")

    ringCenterKind = Property(str, lambda self: self._center_action().kind, notify=changed)
    ringCenterValue = Property(str, lambda self: self._center_action().value, notify=changed)

    cwKind = Property(str, lambda self: self._wheel_action("cw").kind, notify=changed)
    cwValue = Property(str, lambda self: self._wheel_action("cw").value, notify=changed)
    ccwKind = Property(str, lambda self: self._wheel_action("ccw").kind, notify=changed)
    ccwValue = Property(str, lambda self: self._wheel_action("ccw").value, notify=changed)

    # ---- ring daemon -----------------------------------------------------
    def _get_ring_daemon(self) -> bool:
        return self._cfg.ring_daemon

    def _set_ring_daemon(self, value: bool) -> None:
        if value != self._cfg.ring_daemon:
            self._cfg.ring_daemon = value
            self.changed.emit()
            # Enabling the toggle silences the xsetwacom keystroke fallback, so re-check that the
            # daemon can actually take over — otherwise the ring would go dead (the footgun).
            self.refreshRingDaemon()

    # When true the background daemon drives the ring as real REL_WHEEL scroll; when false the
    # ring falls back to the xsetwacom keystroke mapping (cw/ccw above).
    ringDaemon = Property(bool, _get_ring_daemon, _set_ring_daemon, notify=changed)

    def _get_pad_daemon(self) -> bool:
        return self._cfg.pad_daemon

    def _set_pad_daemon(self, value: bool) -> None:
        if value != self._cfg.pad_daemon:
            self._cfg.pad_daemon = value
            self.changed.emit()
            # Owning the pad needs the same daemon as the ring — re-check it's actually ready so
            # the user isn't promised mouse buttons that never arrive.
            self.refreshRingDaemon()

    # When true the daemon grabs the whole pad so the express keys inject real mouse buttons /
    # scroll / click-drag; when false the express keys stay on the xsetwacom keystroke floor.
    # Readiness (evdev + service) is the same service as the ring — reuse ringDaemonReady/Status.
    padDaemon = Property(bool, _get_pad_daemon, _set_pad_daemon, notify=changed)

    def _recompute_ring_status(self) -> None:
        """Decide whether the daemon is ready to drive the ring and, if not, why."""
        if not ring_daemon.is_available():
            self._ring_ready = False
            self._ring_status = (
                "python-evdev isn’t installed, so the daemon can’t run. The ring won’t scroll "
                "while this is on — install the ‘daemon’ extra (pip install -e '.[daemon]')."
            )
        elif not self._ring_setup.is_installed():
            self._ring_ready = False
            self._ring_status = (
                "The ring daemon isn’t installed yet. The ring won’t scroll while this is on — "
                "run ‘wacom-panel --install-ring-daemon’, then log out and back in."
            )
        elif not self._ring_setup.is_active():
            self._ring_ready = False
            self._ring_status = (
                "The ring daemon is installed but not running, so the ring won’t scroll. Start "
                "it with ‘systemctl --user start wacom-control-panel-ring.service’."
            )
        else:
            self._ring_ready = True
            self._ring_status = ""

    @Slot()
    def refreshRingDaemon(self) -> None:
        """Re-check daemon readiness (called on page load and whenever the toggle changes)."""
        self._recompute_ring_status()
        self.ringDaemonStatusChanged.emit()

    # True when the daemon can actually drive the ring (evdev present, service installed+running).
    ringDaemonReady = Property(bool, lambda self: self._ring_ready,
                               notify=ringDaemonStatusChanged)
    # Empty when ready; otherwise a human-readable reason the ring won't scroll yet.
    ringDaemonStatus = Property(str, lambda self: self._ring_status,
                                notify=ringDaemonStatusChanged)

    # ---- per-mode ring editor (daemon path) ------------------------------
    def _ring_mode(self, index: int) -> RingMode:
        if 0 <= index < len(self._cfg.ring_modes):
            return self._cfg.ring_modes[index]
        return RingMode()  # not yet stored -> the daemon's default (scroll down/up)

    def _ensure_ring_mode(self, index: int) -> RingMode:
        """Grow ``ring_modes`` with default entries up to ``index`` so it can be edited."""
        while len(self._cfg.ring_modes) <= index:
            self._cfg.ring_modes.append(RingMode())
        return self._cfg.ring_modes[index]

    # The editor always edits the tablet's currently-active mode (selection follows the hardware).
    ringModeCwKind = Property(
        str, lambda self: self._ring_mode(self._active_ring_mode).cw.kind, notify=changed)
    ringModeCwValue = Property(
        str, lambda self: self._ring_mode(self._active_ring_mode).cw.value, notify=changed)
    ringModeCcwKind = Property(
        str, lambda self: self._ring_mode(self._active_ring_mode).ccw.kind, notify=changed)
    ringModeCcwValue = Property(
        str, lambda self: self._ring_mode(self._active_ring_mode).ccw.value, notify=changed)

    # Friendly name of the mode being edited (= the active one), e.g. "Mode 2".
    ringModeName = Property(str, lambda self: f"Mode {self._active_ring_mode + 1}",
                            notify=ringModeChanged)

    @Slot(str, str, str)
    def setRingMode(self, direction: str, kind: str, value: str) -> None:
        """Set the active mode's cw/ccw action (daemon ring path)."""
        if direction not in ("cw", "ccw"):
            return
        mode = self._ensure_ring_mode(self._active_ring_mode)
        setattr(mode, direction, ButtonAction(kind=kind, value=value))
        self.changed.emit()

    @Slot()
    def refreshRingMode(self) -> None:
        """Poll the tablet's live LED mode from sysfs; the editor edits whatever mode is active."""
        if not self._led_resolved:
            self._led_path = ring_daemon.find_led_select()
            self._led_resolved = True
        mode = ring_daemon.read_mode(self._led_path)
        if mode != self._active_ring_mode:
            self._active_ring_mode = mode
            self.ringModeChanged.emit()
            self.changed.emit()  # the editor now reflects the newly-active mode's actions

    # The tablet's currently-lit LED mode (0-based); drives the live LED indicators + editor.
    activeRingMode = Property(int, lambda self: self._active_ring_mode, notify=ringModeChanged)

    # ---- edits -----------------------------------------------------------
    @Slot(int, str, str)
    def setButton(self, num: int, kind: str, value: str) -> None:
        self._cfg.buttons[str(num)] = ButtonAction(kind=kind, value=value)
        self.changed.emit()

    @Slot(str, str, str)
    def setWheel(self, direction: str, kind: str, value: str) -> None:
        param = self._wheel_param(direction)
        if param:
            self._cfg.wheels[param] = ButtonAction(kind=kind, value=value)
            self.changed.emit()

    def needs_setup(self) -> bool:
        """True when this tablet has pad buttons but no recognised layout (wizard candidate)."""
        return bool(self._layout.all_buttons) and not self._layout.matched


class TabletSetupVM(QObject):
    """Drives the first-run setup wizard: capture each pad key, then write a user layout.

    Capture is Qt-native (no threads): a ``QProcess`` runs ``xinput test-xi2 --root`` for the
    xsetwacom button numbers, and — best-effort, where the evdev node is readable — a
    ``QSocketNotifier`` on the pad's evdev fd reads the ``BTN_*`` codes for the ``pad_daemon``
    feature. The two are correlated per physical press (both fire within a few ms).
    """

    changed = Signal()       # step / counts / instruction changed
    captured = Signal()      # a key was just captured (drives the flash indicator)
    finished = Signal()      # a layout was saved; the Controller reloads the pad

    _PAIR_WINDOW_S = 0.25    # evdev code is "the same press" if seen this recently

    def __init__(self, tablet, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tablet = tablet
        self._pad = tablet.pad if tablet is not None else None
        self._spec: libwacom_db.TabletSpec | None = None
        self._steps: list[str] = []
        self._step = 0
        self._above: list[tablet_setup.Capture] = []
        self._below: list[tablet_setup.Capture] = []
        self._center: tablet_setup.Capture | None = None
        self._numbers: list[int] = []
        # capture plumbing
        self._proc: QProcess | None = None
        self._parser: pad_capture.Xi2ButtonParser | None = None
        self._stdout = ""
        self._evdev = None
        self._notifier: QSocketNotifier | None = None
        self._pending_evdev: tuple[str, float] | None = None

    def set_tablet(self, tablet) -> None:
        """Re-target the VM after a hotplug; ``start()`` re-resolves the rest from here."""
        self._tablet = tablet
        self._pad = tablet.pad if tablet is not None else None

    # ---- lifecycle -------------------------------------------------------
    @Slot()
    def start(self) -> None:
        """Resolve the tablet shape, reset the pad to button-emitting, begin capturing."""
        if self._pad is None:
            return
        self._above, self._below, self._center = [], [], None
        self._spec = self._resolve_spec()
        self._steps = self._build_steps()
        self._step = 0
        self._numbers = detect_pad_buttons(self._tablet)
        self._reset_pad_buttons()
        self._open_capture()
        self.changed.emit()

    @Slot()
    def cancel(self) -> None:
        self._close_capture()

    def _resolve_spec(self) -> libwacom_db.TabletSpec | None:
        vendor = product = None
        dev = ring_daemon.find_pad_device() if ring_daemon.is_available() else None
        if dev is not None:
            try:
                vendor, product = dev.info.vendor, dev.info.product
            finally:
                dev.close()
        name = self._pad.name if self._pad else ""
        return libwacom_db.find_tablet_spec(vendor, product, name=name)

    def _build_steps(self) -> list[str]:
        if self._spec is not None and self._spec.has_ring:
            return ["intro", "above", "center", "below", "done"]
        return ["intro", "all", "done"]

    def _reset_pad_buttons(self) -> None:
        if self._pad is None:
            return
        for cmd in pad_capture.reset_buttons_command(self._pad.name, self._numbers):
            # cmd = ["xsetwacom", "--set", name, "Button", n, "button", n]
            xsetwacom.set_param(cmd[2], cmd[3], *cmd[4:], dry=False)

    # ---- capture plumbing ------------------------------------------------
    def _open_capture(self) -> None:
        self._parser = pad_capture.Xi2ButtonParser(self._pad.id)
        self._proc = QProcess(self)
        self._proc.readyReadStandardOutput.connect(self._on_xinput)
        argv = pad_capture.xinput_capture_command()
        self._proc.start(argv[0], argv[1:])
        self._open_evdev()

    def _open_evdev(self) -> None:
        if not ring_daemon.is_available():
            return
        dev = ring_daemon.find_pad_device()
        if dev is None:
            return
        self._evdev = dev
        self._notifier = QSocketNotifier(dev.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._on_evdev)

    def _close_capture(self) -> None:
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier = None
        if self._evdev is not None:
            try:
                self._evdev.close()
            except OSError:
                pass
            self._evdev = None
        if self._proc is not None:
            self._proc.readyReadStandardOutput.disconnect()
            self._proc.kill()
            self._proc.waitForFinished(500)
            self._proc = None
        self._parser = None

    def _on_xinput(self) -> None:
        if self._proc is None or self._parser is None:
            return
        self._stdout += bytes(self._proc.readAllStandardOutput()).decode(errors="ignore")
        lines = self._stdout.split("\n")
        self._stdout = lines.pop()  # keep the trailing partial line
        for line in lines:
            number = self._parser.feed(line)
            if number is not None:
                self._record(number)

    def _on_evdev(self) -> None:
        if self._evdev is None:
            return
        from evdev import ecodes
        try:
            events = list(self._evdev.read())
        except (OSError, BlockingIOError):
            return
        for event in events:
            if event.type == ecodes.EV_KEY and event.value == 1:  # key down
                name = ecodes.BTN.get(event.code)
                if isinstance(name, (list, tuple)):
                    name = name[0]
                if name:
                    self._pending_evdev = (name, time.monotonic())

    # ---- recording a press ----------------------------------------------
    def _record(self, xnum: int) -> None:
        step = self._current_step
        if step not in ("above", "below", "center", "all"):
            return  # ignore presses on the intro / done screens
        evdev_name = None
        if self._pending_evdev is not None:
            name, ts = self._pending_evdev
            if time.monotonic() - ts <= self._PAIR_WINDOW_S:
                evdev_name = name
            self._pending_evdev = None
        cap = tablet_setup.Capture(xnum=xnum, evdev=evdev_name)
        if step == "center":
            self._center = cap
        elif step == "below":
            self._below.append(cap)
        else:  # "above" or "all"
            self._above.append(cap)
        self.captured.emit()
        self.changed.emit()

    @Slot()
    def undoLast(self) -> None:
        step = self._current_step
        if step == "center":
            self._center = None
        elif step == "below" and self._below:
            self._below.pop()
        elif self._above:
            self._above.pop()
        self.changed.emit()

    # ---- navigation ------------------------------------------------------
    @Slot()
    def nextStep(self) -> None:
        if self._step < len(self._steps) - 1:
            self._step += 1
            self.changed.emit()

    @Slot()
    def back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self.changed.emit()

    @Slot()
    def finish(self) -> None:
        """Assemble + save the layout, then tell the Controller to reload the pad."""
        spec = self._spec
        layout = tablet_setup.build_layout(
            display_name=(spec.name if spec and spec.name else (self._pad.name if self._pad
                                                                else "My Tablet")),
            model=spec.model if spec else "",
            has_ring=bool(spec and spec.has_ring),
            ring_modes=spec.ring_modes if spec else 1,
            top=self._above,
            bottom=self._below,
            center=self._center,
        )
        save_user_layout(layout)
        self._close_capture()
        self.finished.emit()

    # ---- exposed state ---------------------------------------------------
    @property
    def _current_step(self) -> str:
        return self._steps[self._step] if self._steps else "intro"

    currentStep = Property(str, lambda self: self._current_step, notify=changed)
    isFirstStep = Property(bool, lambda self: self._step == 0, notify=changed)
    isLastStep = Property(bool, lambda self: self._step >= len(self._steps) - 1, notify=changed)
    hasRing = Property(bool, lambda self: bool(self._spec and self._spec.has_ring), notify=changed)
    evdevAvailable = Property(bool, lambda self: self._evdev is not None, notify=changed)
    tabletLabel = Property(
        str,
        lambda self: (self._spec.name if self._spec and self._spec.name
                      else (self._pad.name if self._pad else "your tablet")),
        notify=changed,
    )
    expectedCount = Property(
        int,
        lambda self: (self._spec.num_buttons if self._spec else len(self._numbers)),
        notify=changed,
    )
    totalCaptured = Property(
        int,
        lambda self: len(self._above) + len(self._below) + (1 if self._center else 0),
        notify=changed,
    )

    def _group_count(self) -> int:
        step = self._current_step
        if step == "center":
            return 1 if self._center else 0
        if step == "below":
            return len(self._below)
        return len(self._above)

    groupCount = Property(int, _group_count, notify=changed)

    def _instruction(self) -> str:
        step = self._current_step
        if step == "above":
            return "Press each button ABOVE the touch ring, from the top down."
        if step == "center":
            return "Press the button in the CENTRE of the touch ring."
        if step == "below":
            return "Press each button BELOW the touch ring, from the top down."
        if step == "all":
            return "Press each button on your tablet, from the top down."
        return ""

    instruction = Property(str, _instruction, notify=changed)


class Controller(QObject):
    """Top-level object exposed to QML: profiles, actions, persistence + the mapping VM."""

    statusMessage = Signal(str)
    profilesChanged = Signal()
    persistChanged = Signal()
    setupChanged = Signal()  # the recognised-tablet state changed (wizard finished / hotplug)
    tabletChanged = Signal()  # the connected tablet changed (plugged / unplugged)

    def __init__(self, store: ProfileStore | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store or ProfileStore()
        self._persistence = Persistence()
        self._tablets = devices.list_tablets() if xsetwacom.is_available() else []
        self._tablet = self._tablets[0] if self._tablets else None
        self._outputs = displays.list_outputs()
        self._mapping = MappingVM(self)
        self._mapping.set_context(self._tablet, self._outputs)
        self._pen = PenVM(self)
        self._pen.set_preset_store(PressurePresetStore(self._store.root))
        self._touch = TouchVM(self)
        self._pad = PadVM(self)
        self._pad.set_context(self._tablet)
        self._setup = TabletSetupVM(self._tablet, self)
        self._setup.finished.connect(self._on_setup_finished)
        self._load_active()
        # Poll for tablets being plugged/unplugged while the window is open. xsetwacom's device
        # list is the same source we read at startup; diffing it every few seconds needs no
        # extra dependency (pyudev isn't installed) and stays in step with what the app uses.
        self._poll = QTimer(self)
        self._poll.setInterval(3000)
        self._poll.timeout.connect(self._poll_devices)
        self._poll.start()

    mapping = Property(QObject, lambda self: self._mapping, constant=True)
    pen = Property(QObject, lambda self: self._pen, constant=True)
    touch = Property(QObject, lambda self: self._touch, constant=True)
    pad = Property(QObject, lambda self: self._pad, constant=True)
    setup = Property(QObject, lambda self: self._setup, constant=True)
    tabletName = Property(
        str, lambda self: self._tablet.name if self._tablet else "(no tablet detected)",
        notify=tabletChanged,
    )
    # True when a tablet is connected with pad buttons but no recognised layout — the wizard
    # auto-opens on this. Flips false once the wizard saves a user layout for the model.
    needsSetup = Property(
        bool,
        lambda self: self._tablet is not None and self._pad.needs_setup(),
        notify=setupChanged,
    )

    def _on_setup_finished(self) -> None:
        """A wizard run saved a layout: re-read it, restore live bindings, drop the prompt."""
        self._pad.set_context(self._tablet)
        profile = self._store.active_profile()
        if profile is not None:
            self._pad.load(profile.pad)
            apply_profile(self._current_profile(), self._tablet, self._outputs, dry_run=False)
        self.setupChanged.emit()
        self.statusMessage.emit("Tablet set up — your buttons are ready to configure.")

    # ---- live hotplug ----------------------------------------------------
    def _poll_devices(self) -> None:
        """Re-query tablets; if the connected set changed, refresh context."""
        tablets = devices.list_tablets() if xsetwacom.is_available() else []
        if [t.name for t in tablets] == [t.name for t in self._tablets]:
            return
        self._on_tablets_changed(tablets)

    def _on_tablets_changed(self, tablets) -> None:
        """A tablet was plugged/unplugged: re-point the VMs without dropping unsaved edits.

        ``set_context`` only re-renders the layout against the current in-memory config, so the
        user's in-progress edits survive. ``needsSetup`` is re-evaluated; QML reacts to the
        ``setupChanged`` signal to offer the setup dialog for an unrecognised tablet.
        """
        previous = self._tablet.name if self._tablet else None
        self._tablets = tablets
        self._tablet = tablets[0] if tablets else None
        self._mapping.set_context(self._tablet, self._outputs)
        self._pad.set_context(self._tablet)
        self._setup.set_tablet(self._tablet)
        self.tabletChanged.emit()
        self.setupChanged.emit()
        current = self._tablet.name if self._tablet else None
        if current and current != previous:
            self.statusMessage.emit(f"Tablet connected: {current}")
        elif current is None and previous:
            self.statusMessage.emit("Tablet disconnected.")

    profileNames = Property("QStringList", lambda self: self._store.names(),
                            notify=profilesChanged)
    activeProfile = Property(str, lambda self: self._store.get_active() or "",
                             notify=profilesChanged)
    persistInstalled = Property(bool, lambda self: self._persistence.is_installed(),
                                notify=persistChanged)

    # ---- profiles --------------------------------------------------------
    def _load_profile(self, profile: Profile) -> None:
        self._mapping.load(profile.mapping)
        self._pen.load(profile.pen)
        self._touch.load(profile.touch)
        self._pad.load(profile.pad)

    def _current_profile(self) -> Profile:
        name = self._store.get_active() or "Default"
        return Profile(
            name=name,
            mapping=self._mapping.to_mapping(),
            pen=self._pen.to_config(),
            touch=self._touch.to_config(),
            pad=self._pad.to_config(),
        )

    def _load_active(self) -> None:
        self._load_profile(self._store.ensure_default())
        self.profilesChanged.emit()

    @Slot(str)
    def selectProfile(self, name: str) -> None:
        if not name:
            return
        self._store.set_active(name)
        profile = self._store.load(name)
        if profile is not None:
            self._load_profile(profile)
            self.profilesChanged.emit()
            self.statusMessage.emit(f"Switched to “{name}”.")

    @Slot(str)
    def newProfile(self, name: str) -> None:
        name = name.strip()
        if not name:
            return
        self._store.save(Profile(name=name))
        self._store.set_active(name)
        self._load_active()
        self.statusMessage.emit(f"Created “{name}”.")

    @Slot(str)
    def duplicateProfile(self, name: str) -> None:
        name = name.strip()
        current = self._store.active_profile()
        if not name or current is None:
            return
        clone = Profile.from_dict(current.to_dict())
        clone.name = name
        self._store.save(clone)
        self._store.set_active(name)
        self._load_active()
        self.statusMessage.emit(f"Duplicated to “{name}”.")

    @Slot(str)
    def renameProfile(self, name: str) -> None:
        name = name.strip()
        current = self._store.get_active()
        if name and current and name != current:
            self._store.rename(current, name)
            self._load_active()
            self.statusMessage.emit(f"Renamed to “{name}”.")

    @Slot()
    def deleteProfile(self) -> None:
        current = self._store.get_active()
        if current:
            self._store.delete(current)
            self._load_active()
            self.statusMessage.emit(f"Deleted “{current}”.")

    # ---- apply / save / revert -------------------------------------------
    @Slot()
    def apply(self) -> None:
        if self._tablet is None:
            self.statusMessage.emit("No Wacom tablet detected.")
            return
        try:
            apply_profile(self._current_profile(), self._tablet, self._outputs, dry_run=False)
        except xsetwacom.XsetwacomError as exc:
            self.statusMessage.emit(f"Apply failed: {exc}")
            return
        self.statusMessage.emit("Applied settings to tablet.")

    @Slot()
    def save(self) -> None:
        profile = self._current_profile()
        self._store.save(profile)
        # The ring daemon reads the saved profile, so nudge it to pick up ring-mode edits now.
        self._pad.reload_daemon()
        self.statusMessage.emit(f"Saved “{profile.name}”.")

    @Slot()
    def revert(self) -> None:
        profile = self._store.active_profile()
        if profile is not None:
            self._load_profile(profile)
            self.statusMessage.emit(f"Reverted to saved “{profile.name}”.")

    # ---- persistence -----------------------------------------------------
    @Slot(bool)
    def setPersist(self, enabled: bool) -> None:
        if enabled:
            notes = self._persistence.install()
            msg = "Auto-reapply enabled."
            if notes:
                msg += " " + notes[0]
        else:
            self._persistence.uninstall()
            msg = "Auto-reapply disabled."
        self.persistChanged.emit()
        self.statusMessage.emit(msg)
