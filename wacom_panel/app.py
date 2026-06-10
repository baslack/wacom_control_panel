"""GUI bootstrap: QApplication, Wayland guard, main window."""

from __future__ import annotations

import os
import sys


def _session_warning() -> str | None:
    """Return a warning string if xsetwacom is unlikely to work in this session."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return (
            "You appear to be running a Wayland session. xsetwacom only works under X11, "
            "so applying settings will have no effect. Log into an X11/Xorg session to use "
            "this app."
        )
    if not os.environ.get("DISPLAY"):
        return "No X11 DISPLAY found; xsetwacom commands will fail."
    return None


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv if argv is None else [sys.argv[0]])
    app.setApplicationName("Wacom Control Panel")

    window = MainWindow()
    window.show()

    warning = _session_warning()
    if warning:
        QMessageBox.warning(window, "Session warning", warning)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
