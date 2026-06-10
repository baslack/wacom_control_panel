"""GUI bootstrap: QtQuick (QML) application with the Material style."""

from __future__ import annotations

import os
import sys
from pathlib import Path

QML_MAIN = Path(__file__).parent / "ui" / "qml" / "Main.qml"


def _session_warning() -> str | None:
    """Return a warning string if xsetwacom is unlikely to work in this session."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return (
            "Wayland session detected — xsetwacom only works under X11, so applying will "
            "have no effect. Log into an X11/Xorg session."
        )
    if not os.environ.get("DISPLAY"):
        return "No X11 DISPLAY found; xsetwacom commands will fail."
    return None


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    from .ui.viewmodels import Controller

    app = QGuiApplication.instance() or QGuiApplication(
        sys.argv if argv is None else [sys.argv[0]]
    )
    app.setApplicationName("Wacom Control Panel")
    QQuickStyle.setStyle("Material")

    controller = Controller()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
    if not engine.rootObjects():
        print("Failed to load QML UI.", file=sys.stderr)
        return 1

    warning = _session_warning()
    if warning:
        controller.statusMessage.emit(warning)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
