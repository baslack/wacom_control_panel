"""QObject view-models that expose the (Qt-free) core to QML.

QML binds to :class:`Controller` (set as the ``controller`` context property). The mapping
fields live on :attr:`Controller.mapping` (a :class:`MappingVM`); profile and action methods
live on the controller itself. All UI logic stays here; ``core`` stays pure.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..backend import devices, displays, xsetwacom
from ..core.engine import apply_mapping, resolve_area, tablet_native_area
from ..core.mapping import ANCHORS, ROTATIONS, Area
from ..core.persistence import Persistence
from ..core.profile import MappingConfig, Profile
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
        self._load_active()

    mapping = Property(QObject, lambda self: self._mapping, constant=True)
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
    def _load_active(self) -> None:
        active = self._store.ensure_default()
        self._mapping.load(active.mapping)
        self.profilesChanged.emit()

    @Slot(str)
    def selectProfile(self, name: str) -> None:
        if not name:
            return
        self._store.set_active(name)
        profile = self._store.load(name)
        if profile is not None:
            self._mapping.load(profile.mapping)
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
            apply_mapping(self._mapping.to_mapping(), self._tablet, self._outputs, dry_run=False)
        except xsetwacom.XsetwacomError as exc:
            self.statusMessage.emit(f"Apply failed: {exc}")
            return
        self.statusMessage.emit("Applied mapping to tablet.")

    @Slot()
    def save(self) -> None:
        profile = self._store.active_profile() or self._store.ensure_default()
        profile.mapping = self._mapping.to_mapping()
        self._store.save(profile)
        self.statusMessage.emit(f"Saved “{profile.name}”.")

    @Slot()
    def revert(self) -> None:
        profile = self._store.active_profile()
        if profile is not None:
            self._mapping.load(profile.mapping)
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
