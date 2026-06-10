"""Main application window: profile bar + mapping page, wired to store and engine."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..backend import devices, displays, xsetwacom
from ..core.engine import apply_mapping
from ..core.persistence import Persistence
from ..core.profile import Profile
from ..core.store import ProfileStore
from .mapping_page import MappingPage
from .profile_bar import ProfileBar


class MainWindow(QMainWindow):
    def __init__(self, store: ProfileStore | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Wacom Control Panel")
        self.resize(940, 600)

        self.store = store or ProfileStore()
        self.persistence = Persistence()
        self.tablets = devices.list_tablets() if xsetwacom.is_available() else []
        self.outputs = displays.list_outputs()
        self.tablet = self.tablets[0] if self.tablets else None

        self.profile_bar = ProfileBar()
        self.mapping_page = MappingPage()
        self.mapping_page.set_context(self.tablet, self.outputs)

        self.persist_check = QCheckBox("Reapply active profile on login & device replug")
        self.persist_check.setChecked(self.persistence.is_installed())

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.profile_bar)
        layout.addWidget(self.mapping_page, 1)
        layout.addWidget(self.persist_check)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        self._connect()
        self._reload_profiles()

    # ---- wiring -----------------------------------------------------------
    def _connect(self) -> None:
        self.profile_bar.profileSelected.connect(self._on_profile_selected)
        self.profile_bar.newProfile.connect(self._on_new_profile)
        self.profile_bar.duplicateProfile.connect(self._on_duplicate_profile)
        self.profile_bar.renameProfile.connect(self._on_rename_profile)
        self.profile_bar.deleteProfile.connect(self._on_delete_profile)

        self.mapping_page.applyRequested.connect(self._on_apply)
        self.mapping_page.saveRequested.connect(self._on_save)
        self.mapping_page.revertRequested.connect(self._on_revert)

        self.persist_check.toggled.connect(self._on_persist_toggled)

    # ---- profiles ---------------------------------------------------------
    def _reload_profiles(self) -> None:
        active = self.store.ensure_default()
        names = self.store.names()
        self.profile_bar.set_profiles(names, active.name)
        self.mapping_page.set_mapping(active.mapping)
        self._status(f"Loaded profile “{active.name}”.")

    def _active(self) -> Profile:
        return self.store.active_profile() or self.store.ensure_default()

    def _on_profile_selected(self, name: str) -> None:
        self.store.set_active(name)
        profile = self.store.load(name)
        if profile is not None:
            self.mapping_page.set_mapping(profile.mapping)
            self._status(f"Switched to “{name}”.")

    def _on_new_profile(self) -> None:
        name = self._ask_name("New profile", "Name:")
        if name:
            self.store.save(Profile(name=name))
            self.store.set_active(name)
            self._reload_profiles()

    def _on_duplicate_profile(self) -> None:
        current = self._active()
        name = self._ask_name("Duplicate profile", "New name:", f"{current.name} copy")
        if name:
            clone = Profile.from_dict(current.to_dict())
            clone.name = name
            self.store.save(clone)
            self.store.set_active(name)
            self._reload_profiles()

    def _on_rename_profile(self) -> None:
        current = self._active()
        name = self._ask_name("Rename profile", "New name:", current.name)
        if name and name != current.name:
            self.store.rename(current.name, name)
            self._reload_profiles()

    def _on_delete_profile(self) -> None:
        current = self._active()
        if QMessageBox.question(self, "Delete profile", f"Delete “{current.name}”?") \
                == QMessageBox.StandardButton.Yes:
            self.store.delete(current.name)
            self._reload_profiles()

    def _ask_name(self, title: str, label: str, default: str = "") -> str | None:
        text, ok = QInputDialog.getText(self, title, label, text=default)
        text = text.strip()
        return text if ok and text else None

    # ---- apply / save / revert -------------------------------------------
    def _on_apply(self) -> None:
        if self.tablet is None:
            QMessageBox.warning(self, "No tablet", "No Wacom tablet detected.")
            return
        mapping = self.mapping_page.mapping()
        try:
            apply_mapping(mapping, self.tablet, self.outputs, dry_run=False)
        except xsetwacom.XsetwacomError as exc:
            QMessageBox.critical(self, "Apply failed", str(exc))
            return
        self._status("Applied mapping to tablet.")

    def _on_save(self) -> None:
        profile = self._active()
        profile.mapping = self.mapping_page.mapping()
        self.store.save(profile)
        self._status(f"Saved “{profile.name}”.")

    def _on_revert(self) -> None:
        profile = self._active()
        self.mapping_page.set_mapping(profile.mapping)
        self._status(f"Reverted to saved “{profile.name}”.")

    def _on_persist_toggled(self, checked: bool) -> None:
        if checked:
            notes = self.persistence.install()
            msg = "Auto-reapply enabled (login + hotplug)."
            if notes:
                QMessageBox.information(self, "Auto-reapply", "\n".join(notes))
        else:
            self.persistence.uninstall()
            msg = "Auto-reapply disabled."
        self._status(msg)

    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)
