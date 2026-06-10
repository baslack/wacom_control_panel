"""Custom-painted canvases: the display layout picker and the tablet area editor."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..backend.displays import Output, desktop_bounds
from ..core.mapping import Area

_ACCENT = QColor(56, 142, 233)
_ACCENT_FILL = QColor(56, 142, 233, 70)
_OUTLINE = QColor(120, 120, 120)
_BG = QColor(38, 38, 40)
_TEXT = QColor(230, 230, 230)


class ScreenCanvas(QWidget):
    """Draws the monitor layout to scale; click a monitor to target it.

    Emits :data:`selectionChanged` with the connector name, or ``None`` for whole desktop.
    """

    selectionChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._outputs: list[Output] = []
        self._selected: str | None = None
        self._rects: list[tuple[Output, QRectF]] = []
        self.setMinimumHeight(160)

    def set_outputs(self, outputs: list[Output]) -> None:
        self._outputs = outputs
        self.update()

    def set_selected(self, name: str | None) -> None:
        self._selected = name
        self.update()

    # ---- geometry ---------------------------------------------------------
    def _layout_rects(self) -> list[tuple[Output, QRectF]]:
        if not self._outputs:
            return []
        x, y, w, h = desktop_bounds(self._outputs)
        if w <= 0 or h <= 0:
            return []
        margin = 16.0
        avail_w = self.width() - 2 * margin
        avail_h = self.height() - 2 * margin
        scale = min(avail_w / w, avail_h / h)
        off_x = margin + (avail_w - w * scale) / 2
        off_y = margin + (avail_h - h * scale) / 2
        rects = []
        for o in self._outputs:
            rects.append((
                o,
                QRectF(
                    off_x + (o.x - x) * scale,
                    off_y + (o.y - y) * scale,
                    o.width * scale,
                    o.height * scale,
                ),
            ))
        return rects

    # ---- painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), _BG)
        self._rects = self._layout_rects()
        whole = self._selected is None
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() + 1)
        p.setFont(font)
        for o, r in self._rects:
            selected = whole or o.name == self._selected
            p.setBrush(QBrush(_ACCENT_FILL if selected else QColor(52, 52, 56)))
            p.setPen(QPen(_ACCENT if selected else _OUTLINE, 2 if selected else 1))
            p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 6, 6)
            p.setPen(_TEXT)
            label = f"{o.name}\n{o.width}×{o.height}"
            if o.primary:
                label += " ★"
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        for o, r in self._rects:
            if r.contains(pos):
                self._selected = o.name
                self.update()
                self.selectionChanged.emit(o.name)
                return


class TabletCanvas(QWidget):
    """Draws the tablet surface with a draggable / resizable active-area rectangle.

    Emits :data:`areaChanged` with an :class:`Area` (device units) as the user edits it.
    """

    areaChanged = Signal(object)

    _HANDLE = 12.0  # px hit radius for the resize handle

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tablet_w = 44704
        self._tablet_h = 27940
        self._area = Area(0, 0, self._tablet_w, self._tablet_h)
        self._lock_aspect = True
        self._scale = 1.0
        self._off = QPointF(0, 0)
        self._drag_mode: str | None = None  # "move" | "resize"
        self._drag_start = QPointF(0, 0)
        self._area_start = self._area
        self.setMinimumHeight(220)

    # ---- public API -------------------------------------------------------
    def set_tablet_size(self, w: int, h: int) -> None:
        self._tablet_w, self._tablet_h = max(1, w), max(1, h)
        self.update()

    def set_area(self, area: Area) -> None:
        self._area = self._clamp(area)
        self.update()

    def set_lock_aspect(self, locked: bool) -> None:
        self._lock_aspect = locked

    def area(self) -> Area:
        return self._area

    # ---- coordinate transforms -------------------------------------------
    def _recompute_transform(self) -> None:
        margin = 18.0
        avail_w = self.width() - 2 * margin
        avail_h = self.height() - 2 * margin
        self._scale = min(avail_w / self._tablet_w, avail_h / self._tablet_h)
        draw_w = self._tablet_w * self._scale
        draw_h = self._tablet_h * self._scale
        self._off = QPointF(
            margin + (avail_w - draw_w) / 2,
            margin + (avail_h - draw_h) / 2,
        )

    def _dev_to_widget(self, x: float, y: float) -> QPointF:
        return QPointF(self._off.x() + x * self._scale, self._off.y() + y * self._scale)

    def _widget_to_dev(self, pt: QPointF) -> tuple[float, float]:
        return (
            (pt.x() - self._off.x()) / self._scale,
            (pt.y() - self._off.y()) / self._scale,
        )

    def _area_rect(self) -> QRectF:
        tl = self._dev_to_widget(self._area.x1, self._area.y1)
        br = self._dev_to_widget(self._area.x2, self._area.y2)
        return QRectF(tl, br)

    def _clamp(self, area: Area) -> Area:
        x1 = max(0, min(area.x1, self._tablet_w - 1))
        y1 = max(0, min(area.y1, self._tablet_h - 1))
        x2 = max(x1 + 1, min(area.x2, self._tablet_w))
        y2 = max(y1 + 1, min(area.y2, self._tablet_h))
        return Area(int(x1), int(y1), int(x2), int(y2))

    # ---- painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        self._recompute_transform()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), _BG)

        tl = self._dev_to_widget(0, 0)
        br = self._dev_to_widget(self._tablet_w, self._tablet_h)
        tablet_rect = QRectF(tl, br)
        p.setBrush(QBrush(QColor(52, 52, 56)))
        p.setPen(QPen(_OUTLINE, 2))
        p.drawRoundedRect(tablet_rect, 8, 8)

        area_rect = self._area_rect()
        p.setBrush(QBrush(_ACCENT_FILL))
        p.setPen(QPen(_ACCENT, 2))
        p.drawRect(area_rect)

        # Resize handle (bottom-right).
        p.setBrush(QBrush(_ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(area_rect.right() - 6, area_rect.bottom() - 6, 12, 12))

        p.setPen(_TEXT)
        p.drawText(
            tablet_rect.adjusted(6, 4, -6, -4),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            f"Tablet {self._tablet_w}×{self._tablet_h}",
        )
        p.drawText(
            area_rect,
            Qt.AlignmentFlag.AlignCenter,
            f"{self._area.width}×{self._area.height}",
        )
        p.end()

    # ---- interaction ------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        rect = self._area_rect()
        handle = QRectF(rect.right() - self._HANDLE, rect.bottom() - self._HANDLE,
                        self._HANDLE * 2, self._HANDLE * 2)
        if handle.contains(pos):
            self._drag_mode = "resize"
        elif rect.contains(pos):
            self._drag_mode = "move"
        else:
            self._drag_mode = None
            return
        self._drag_start = pos
        self._area_start = self._area

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_mode is None:
            return
        pos = event.position()
        dx = (pos.x() - self._drag_start.x()) / self._scale
        dy = (pos.y() - self._drag_start.y()) / self._scale
        if self._drag_mode == "move":
            new = Area(
                int(self._area_start.x1 + dx), int(self._area_start.y1 + dy),
                int(self._area_start.x2 + dx), int(self._area_start.y2 + dy),
            )
            # Keep size, shift fully inside bounds.
            w, h = new.width, new.height
            x1 = max(0, min(new.x1, self._tablet_w - w))
            y1 = max(0, min(new.y1, self._tablet_h - h))
            self._area = Area(x1, y1, x1 + w, y1 + h)
        else:  # resize from bottom-right
            new_w = max(1, self._area_start.width + dx)
            if self._lock_aspect:
                aspect = self._area_start.width / self._area_start.height
                new_h = new_w / aspect
            else:
                new_h = max(1, self._area_start.height + dy)
            x2 = min(self._tablet_w, self._area_start.x1 + new_w)
            y2 = min(self._tablet_h, self._area_start.y1 + new_h)
            self._area = self._clamp(
                Area(self._area_start.x1, self._area_start.y1, int(x2), int(y2))
            )
        self.update()
        self.areaChanged.emit(self._area)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_mode is not None:
            self._drag_mode = None
            self.areaChanged.emit(self._area)
