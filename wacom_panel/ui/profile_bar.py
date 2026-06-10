"""Top bar for selecting and managing named profiles."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget


class ProfileBar(QWidget):
    """Profile selector + new/duplicate/rename/delete actions.

    Pure view: it emits intent signals; the main window performs storage operations and
    calls :meth:`set_profiles` to refresh.
    """

    profileSelected = Signal(str)
    newProfile = Signal()
    duplicateProfile = Signal()
    renameProfile = Signal()
    deleteProfile = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self.combo = QComboBox()
        self.combo.setMinimumWidth(180)

        new_btn = QPushButton("New")
        dup_btn = QPushButton("Duplicate")
        rename_btn = QPushButton("Rename")
        del_btn = QPushButton("Delete")

        layout = QHBoxLayout(self)
        layout.addWidget(QLabel("Profile:"))
        layout.addWidget(self.combo)
        layout.addWidget(new_btn)
        layout.addWidget(dup_btn)
        layout.addWidget(rename_btn)
        layout.addWidget(del_btn)
        layout.addStretch(1)

        self.combo.currentTextChanged.connect(self._on_selected)
        new_btn.clicked.connect(self.newProfile)
        dup_btn.clicked.connect(self.duplicateProfile)
        rename_btn.clicked.connect(self.renameProfile)
        del_btn.clicked.connect(self.deleteProfile)

    def set_profiles(self, names: list[str], active: str | None) -> None:
        self._loading = True
        self.combo.clear()
        self.combo.addItems(names)
        if active and active in names:
            self.combo.setCurrentText(active)
        self._loading = False

    def current(self) -> str:
        return self.combo.currentText()

    def _on_selected(self, name: str) -> None:
        if not self._loading and name:
            self.profileSelected.emit(name)
