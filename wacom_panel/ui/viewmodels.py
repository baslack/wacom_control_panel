"""QObject view-models that expose the (Qt-free) core to QML.

QML binds to :class:`Controller` (set as the ``controller`` context property). The mapping
fields live on :attr:`Controller.mapping` (a :class:`MappingVM`); profile and action methods
live on the controller itself. All UI logic stays here; ``core`` stays pure.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..backend import devices, displays, xsetwacom
from ..core.engine import (
    apply_profile,
    detect_pad_buttons,
    resolve_area,
    tablet_native_area,
)
from ..core.mapping import ANCHORS, ROTATIONS, Area
from ..core.pad_layout import PadLayout, load_layout
from ..core.persistence import Persistence
from ..core.pressure_presets import PressurePresetStore
from ..core.profile import (
    ButtonAction,
    MappingConfig,
    PadConfig,
    PenConfig,
    Profile,
    TouchConfig,
)
from ..core.store import ProfileStore

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

    # Default touch-ring actions (the device default is scroll up/down).
    _WHEEL_DEFAULTS = {"up": ("button", "4"), "down": ("button", "5")}

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cfg = PadConfig()
        self._layout: PadLayout = load_layout("", [])

    def set_context(self, tablet) -> None:
        numbers = detect_pad_buttons(tablet) if tablet is not None else []
        name = tablet.name if tablet is not None else ""
        self._layout = load_layout(name, numbers)
        self.changed.emit()

    def load(self, pad: PadConfig) -> None:
        self._cfg = pad
        self.changed.emit()

    def to_config(self) -> PadConfig:
        return self._cfg

    # ---- helpers ---------------------------------------------------------
    def _button_action(self, num: int) -> ButtonAction:
        return self._cfg.buttons.get(str(num)) or ButtonAction("button", str(num))

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
        kind, value = self._WHEEL_DEFAULTS["up" if direction == "cw" else "down"]
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


class Controller(QObject):
    """Top-level object exposed to QML: profiles, actions, persistence + the mapping VM."""

    statusMessage = Signal(str)
    profilesChanged = Signal()
    persistChanged = Signal()

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
        self._load_active()

    mapping = Property(QObject, lambda self: self._mapping, constant=True)
    pen = Property(QObject, lambda self: self._pen, constant=True)
    touch = Property(QObject, lambda self: self._touch, constant=True)
    pad = Property(QObject, lambda self: self._pad, constant=True)
    tabletName = Property(
        str, lambda self: self._tablet.name if self._tablet else "(no tablet detected)",
        constant=True,
    )

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
