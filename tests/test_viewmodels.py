"""View-model + QML-load tests (run headless via the offscreen Qt platform)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtQml")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from wacom_panel.backend.devices import Device, Tablet  # noqa: E402
from wacom_panel.backend.displays import Output  # noqa: E402
from wacom_panel.core.profile import MappingConfig  # noqa: E402

TABLET = Tablet(name="Wacom Test", devices=[Device("Wacom Test Pen stylus", 1, "STYLUS")])
OUTPUTS = [Output("DP-4", 1920, 1080, 0, 0, True), Output("DP-2", 1920, 1080, 1920, 0)]


@pytest.fixture(scope="session")
def qapp():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture(autouse=True)
def _fixed_tablet_area(monkeypatch):
    # Avoid touching real hardware: pin the native tablet size.
    for mod in ("wacom_panel.core.engine", "wacom_panel.ui.viewmodels"):
        monkeypatch.setattr(mod + ".tablet_native_area", lambda _t: (44704, 27940),
                            raising=True)


def test_force_proportions_single_output(qapp):
    from wacom_panel.ui.viewmodels import MappingVM

    vm = MappingVM()
    vm.set_context(TABLET, OUTPUTS)
    vm.load(MappingConfig(output="DP-4", force_proportions=True))
    assert vm.areaY1 > 0  # letterboxed vertically
    aspect = (vm.areaX2 - vm.areaX1) / (vm.areaY2 - vm.areaY1)
    assert aspect == pytest.approx(1920 / 1080, rel=1e-2)


def test_force_proportions_whole_desktop(qapp):
    from wacom_panel.ui.viewmodels import MappingVM

    vm = MappingVM()
    vm.set_context(TABLET, OUTPUTS)
    vm.load(MappingConfig(output=None, force_proportions=True))
    aspect = (vm.areaX2 - vm.areaX1) / (vm.areaY2 - vm.areaY1)
    assert aspect == pytest.approx(3840 / 1080, rel=1e-2)  # both monitors


def test_output_index_roundtrip(qapp):
    from wacom_panel.ui.viewmodels import MappingVM

    vm = MappingVM()
    vm.set_context(TABLET, OUTPUTS)
    vm.outputIndex = 2  # DP-2
    assert vm.selectedOutput == "DP-2"
    vm.selectOutputByName("DP-4")
    assert vm.outputIndex == 1


def test_canvas_area_override(qapp):
    from wacom_panel.ui.viewmodels import MappingVM

    vm = MappingVM()
    vm.set_context(TABLET, OUTPUTS)
    vm.setAreaFromCanvas(100, 200, 300, 400)
    assert (vm.areaX1, vm.areaY1, vm.areaX2, vm.areaY2) == (100, 200, 300, 400)


def test_qml_main_loads(qapp, tmp_path, monkeypatch):
    """Main.qml + components parse and instantiate against a real Controller."""
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    from wacom_panel.app import QML_MAIN
    from wacom_panel.core.store import ProfileStore
    from wacom_panel.ui.viewmodels import Controller

    QQuickStyle.setStyle("Material")
    controller = Controller(store=ProfileStore(root=tmp_path))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
    assert engine.rootObjects(), "Main.qml failed to instantiate"
