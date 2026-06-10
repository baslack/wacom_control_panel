"""The mapping editor page: linked screen/tablet canvases plus precise controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..backend.devices import Tablet
from ..backend.displays import Output
from ..core.engine import resolve_area, tablet_native_area
from ..core.mapping import ANCHORS, ROTATIONS, Area
from ..core.profile import MappingConfig

_WHOLE_DESKTOP = "Whole desktop"


class MappingPage(QWidget):
    """Edits a :class:`MappingConfig`. Emits :data:`applyRequested` / :data:`saveRequested`."""

    applyRequested = Signal()
    saveRequested = Signal()
    revertRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from .canvas import ScreenCanvas, TabletCanvas  # local import keeps Qt optional at CLI

        self._tablet: Tablet | None = None
        self._outputs: list[Output] = []
        self._tablet_size = (44704, 27940)
        self._loading = False

        self.screen_canvas = ScreenCanvas()
        self.tablet_canvas = TabletCanvas()

        # ---- controls -----------------------------------------------------
        self.output_combo = QComboBox()
        self.force_check = QCheckBox("Force proportions (no stretch)")
        self.rotate_combo = QComboBox()
        self.rotate_combo.addItems(list(ROTATIONS))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Absolute", "Relative"])
        self.anchor_combo = QComboBox()
        self.anchor_combo.addItems(list(ANCHORS))
        self.touch_check = QCheckBox("Also map touch")

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 100)
        self.zoom_slider.setValue(100)
        self.zoom_label = QLabel("100%")

        self.spin_x1 = QSpinBox()
        self.spin_y1 = QSpinBox()
        self.spin_x2 = QSpinBox()
        self.spin_y2 = QSpinBox()
        for s in (self.spin_x1, self.spin_y1, self.spin_x2, self.spin_y2):
            s.setRange(0, 1_000_000)
            s.setSingleStep(100)

        self.apply_btn = QPushButton("Apply")
        self.revert_btn = QPushButton("Revert")
        self.save_btn = QPushButton("Save to profile")

        self._build_layout()
        self._connect()

    # ---- layout -----------------------------------------------------------
    def _build_layout(self) -> None:
        canvases = QVBoxLayout()
        screen_box = QGroupBox("Target display")
        sb = QVBoxLayout(screen_box)
        sb.addWidget(self.screen_canvas)
        tablet_box = QGroupBox("Tablet active area")
        tb = QVBoxLayout(tablet_box)
        tb.addWidget(self.tablet_canvas)
        canvases.addWidget(screen_box, 1)
        canvases.addWidget(tablet_box, 1)

        form = QFormLayout()
        form.addRow("Output:", self.output_combo)
        form.addRow(self.force_check)
        form.addRow("Rotation:", self.rotate_combo)
        form.addRow("Mode:", self.mode_combo)
        form.addRow("Anchor:", self.anchor_combo)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(self.zoom_slider)
        zoom_row.addWidget(self.zoom_label)
        form.addRow("Zoom:", zoom_row)
        form.addRow(self.touch_check)

        area_box = QGroupBox("Area (device units)")
        ab = QFormLayout(area_box)
        ab.addRow("Left (x1):", self.spin_x1)
        ab.addRow("Top (y1):", self.spin_y1)
        ab.addRow("Right (x2):", self.spin_x2)
        ab.addRow("Bottom (y2):", self.spin_y2)

        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_btn)
        buttons.addWidget(self.revert_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.save_btn)

        controls = QVBoxLayout()
        controls.addLayout(form)
        controls.addWidget(area_box)
        controls.addStretch(1)
        controls.addLayout(buttons)
        controls_widget = QWidget()
        controls_widget.setLayout(controls)
        controls_widget.setMaximumWidth(320)

        root = QHBoxLayout(self)
        root.addLayout(canvases, 1)
        root.addWidget(controls_widget)

    def _connect(self) -> None:
        self.screen_canvas.selectionChanged.connect(self._on_screen_selected)
        self.output_combo.currentIndexChanged.connect(self._on_output_combo)
        self.force_check.toggled.connect(self._on_force_toggled)
        self.rotate_combo.currentTextChanged.connect(self._recompute_if_forced)
        self.anchor_combo.currentTextChanged.connect(self._recompute_if_forced)
        self.zoom_slider.valueChanged.connect(self._on_zoom)
        self.tablet_canvas.areaChanged.connect(self._on_canvas_area)
        for s in (self.spin_x1, self.spin_y1, self.spin_x2, self.spin_y2):
            s.editingFinished.connect(self._on_spins)
        self.apply_btn.clicked.connect(self.applyRequested)
        self.save_btn.clicked.connect(self.saveRequested)
        self.revert_btn.clicked.connect(self._on_revert)

    # ---- context / state --------------------------------------------------
    def set_context(self, tablet: Tablet | None, outputs: list[Output]) -> None:
        self._tablet = tablet
        self._outputs = outputs
        if tablet is not None:
            self._tablet_size = tablet_native_area(tablet)
        self.tablet_canvas.set_tablet_size(*self._tablet_size)
        self.screen_canvas.set_outputs(outputs)
        self._populate_output_combo()

    def _populate_output_combo(self) -> None:
        self._loading = True
        self.output_combo.clear()
        self.output_combo.addItem(_WHOLE_DESKTOP, userData=None)
        for o in self._outputs:
            self.output_combo.addItem(f"{o.name} ({o.width}×{o.height})", userData=o.name)
        self._loading = False

    def set_mapping(self, mapping: MappingConfig) -> None:
        self._loading = True
        self._select_output(mapping.output)
        self.force_check.setChecked(mapping.force_proportions)
        self.rotate_combo.setCurrentText(mapping.rotate)
        self.mode_combo.setCurrentText(mapping.mode)
        self.anchor_combo.setCurrentText(mapping.anchor)
        self.zoom_slider.setValue(int(round(mapping.zoom * 100)))
        self.zoom_label.setText(f"{int(round(mapping.zoom * 100))}%")
        self.touch_check.setChecked(mapping.apply_to_touch)
        self.tablet_canvas.set_lock_aspect(mapping.force_proportions)
        if self._tablet:
            area = resolve_area(mapping, self._tablet, self._outputs)
        else:
            area = mapping.area_obj
        if area is None:
            area = Area(0, 0, *self._tablet_size)
        self._apply_area_to_widgets(area)
        self.screen_canvas.set_selected(mapping.output)
        self._loading = False

    def mapping(self) -> MappingConfig:
        return MappingConfig(
            output=self.output_combo.currentData(),
            force_proportions=self.force_check.isChecked(),
            rotate=self.rotate_combo.currentText(),
            mode=self.mode_combo.currentText(),
            anchor=self.anchor_combo.currentText(),
            zoom=self.zoom_slider.value() / 100.0,
            area=[self.spin_x1.value(), self.spin_y1.value(),
                  self.spin_x2.value(), self.spin_y2.value()],
            apply_to_touch=self.touch_check.isChecked(),
        )

    # ---- helpers ----------------------------------------------------------
    def _select_output(self, name: str | None) -> None:
        idx = self.output_combo.findData(name)
        self.output_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _apply_area_to_widgets(self, area: Area) -> None:
        self.spin_x1.setValue(area.x1)
        self.spin_y1.setValue(area.y1)
        self.spin_x2.setValue(area.x2)
        self.spin_y2.setValue(area.y2)
        self.tablet_canvas.set_area(area)

    def _recompute_forced_area(self) -> None:
        if not self.force_check.isChecked():
            return
        area = resolve_area(self.mapping(), self._tablet, self._outputs) if self._tablet else None
        if area is not None:
            prev = self._loading
            self._loading = True
            self._apply_area_to_widgets(area)
            self._loading = prev

    # ---- signal handlers --------------------------------------------------
    def _on_screen_selected(self, name) -> None:
        self._select_output(name)

    def _on_output_combo(self, _idx: int) -> None:
        if self._loading:
            return
        self.screen_canvas.set_selected(self.output_combo.currentData())
        self._recompute_forced_area()

    def _on_force_toggled(self, checked: bool) -> None:
        self.tablet_canvas.set_lock_aspect(checked)
        if not self._loading:
            self._recompute_forced_area()

    def _recompute_if_forced(self, *_args) -> None:
        if not self._loading:
            self._recompute_forced_area()

    def _on_zoom(self, value: int) -> None:
        self.zoom_label.setText(f"{value}%")
        if not self._loading:
            self._recompute_forced_area()

    def _on_canvas_area(self, area: Area) -> None:
        if self._loading:
            return
        self._loading = True
        self.spin_x1.setValue(area.x1)
        self.spin_y1.setValue(area.y1)
        self.spin_x2.setValue(area.x2)
        self.spin_y2.setValue(area.y2)
        self._loading = False

    def _on_spins(self) -> None:
        if self._loading:
            return
        area = Area(self.spin_x1.value(), self.spin_y1.value(),
                    self.spin_x2.value(), self.spin_y2.value())
        self.tablet_canvas.set_area(area)

    def _on_revert(self) -> None:
        # MainWindow owns the active profile; ask it to reload our state from disk.
        self.revertRequested.emit()
