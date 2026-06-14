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


class _FakeSetup:
    def __init__(self, *, installed: bool, active: bool) -> None:
        self._installed = installed
        self._active = active

    def is_installed(self) -> bool:
        return self._installed

    def is_active(self) -> bool:
        return self._active


def _pad_vm(monkeypatch, *, evdev_ok: bool, installed: bool, active: bool):
    from wacom_panel.ui import viewmodels

    monkeypatch.setattr(viewmodels.ring_daemon, "is_available", lambda: evdev_ok)
    vm = viewmodels.PadVM()
    vm._ring_setup = _FakeSetup(installed=installed, active=active)
    vm.refreshRingDaemon()
    return vm


def test_ring_daemon_ready_when_installed_and_active(qapp, monkeypatch):
    vm = _pad_vm(monkeypatch, evdev_ok=True, installed=True, active=True)
    assert vm.ringDaemonReady
    assert vm.ringDaemonStatus == ""


def test_ring_daemon_warns_when_evdev_missing(qapp, monkeypatch):
    vm = _pad_vm(monkeypatch, evdev_ok=False, installed=True, active=True)
    assert not vm.ringDaemonReady
    assert "evdev" in vm.ringDaemonStatus


def test_ring_daemon_warns_when_not_installed(qapp, monkeypatch):
    vm = _pad_vm(monkeypatch, evdev_ok=True, installed=False, active=False)
    assert not vm.ringDaemonReady
    assert "install-ring-daemon" in vm.ringDaemonStatus


def test_ring_daemon_warns_when_installed_but_inactive(qapp, monkeypatch):
    vm = _pad_vm(monkeypatch, evdev_ok=True, installed=True, active=False)
    assert not vm.ringDaemonReady
    assert "not running" in vm.ringDaemonStatus


def test_toggling_ring_daemon_rechecks_readiness(qapp, monkeypatch):
    # Enabling the toggle must re-evaluate readiness (it silences the keystroke fallback).
    vm = _pad_vm(monkeypatch, evdev_ok=True, installed=False, active=False)
    seen = []
    vm.ringDaemonStatusChanged.connect(lambda: seen.append(vm.ringDaemonReady))
    vm.ringDaemon = True
    assert seen == [False]  # toggle fired a fresh check, still not ready


def test_toggling_pad_daemon_sets_config_and_rechecks_readiness(qapp, monkeypatch):
    # Owning the pad grabs it, so the same readiness check must fire (same daemon as the ring).
    vm = _pad_vm(monkeypatch, evdev_ok=True, installed=False, active=False)
    seen = []
    vm.ringDaemonStatusChanged.connect(lambda: seen.append(vm.ringDaemonReady))
    assert vm.padDaemon is False
    vm.padDaemon = True
    assert vm.padDaemon is True
    assert vm._cfg.pad_daemon is True
    assert seen == [False]  # toggle fired a fresh readiness check


def _pad_vm_with_ring(qapp, modes=4):
    from wacom_panel.core.pad_layout import PadLayout, PadRing
    from wacom_panel.core.profile import PadConfig
    from wacom_panel.ui.viewmodels import PadVM

    vm = PadVM()
    vm._layout = PadLayout(
        display_name="Test Pad",
        ring=PadRing(center=1, center_label="Mode", modes=modes,
                     cw="AbsWheelUp", ccw="AbsWheelDown"),
    )
    vm.load(PadConfig(ring_daemon=True))
    return vm


def test_ring_mode_defaults_to_scroll(qapp):
    vm = _pad_vm_with_ring(qapp)
    # An unstored mode reports the daemon default: cw scroll down, ccw scroll up.
    assert (vm.ringModeCwKind, vm.ringModeCwValue) == ("scroll", "down")
    assert (vm.ringModeCcwKind, vm.ringModeCcwValue) == ("scroll", "up")


def test_set_ring_mode_writes_active_mode(qapp):
    vm = _pad_vm_with_ring(qapp)
    vm._active_ring_mode = 1  # the editor edits whatever mode the tablet is on
    vm.setRingMode("cw", "key", "Next")
    cfg = vm.to_config()
    # ring_modes padded to index 1; mode 1's cw is the new key, mode 0 left default.
    assert len(cfg.ring_modes) == 2
    assert (cfg.ring_modes[1].cw.kind, cfg.ring_modes[1].cw.value) == ("key", "Next")
    assert cfg.ring_modes[1].ccw.kind == "scroll"  # untouched default


def test_to_config_trims_trailing_default_modes(qapp):
    vm = _pad_vm_with_ring(qapp)
    vm._active_ring_mode = 1
    vm.setRingMode("cw", "scroll", "down")   # same as default -> mode stays all-default
    vm.setRingMode("ccw", "scroll", "up")
    assert vm.to_config().ring_modes == []   # both trailing defaults trimmed away


def test_ring_mode_name_tracks_active(qapp):
    vm = _pad_vm_with_ring(qapp)
    assert vm.ringModeName == "Mode 1"
    vm._active_ring_mode = 2
    assert vm.ringModeName == "Mode 3"


def test_reload_daemon_signals_only_when_on_and_active(qapp):
    vm = _pad_vm_with_ring(qapp)

    class _Setup:
        def __init__(self, active):
            self._active = active
            self.reloaded = 0

        def is_active(self):
            return self._active

        def reload(self):
            self.reloaded += 1

    vm._ring_setup = _Setup(active=True)
    vm.reload_daemon()
    assert vm._ring_setup.reloaded == 1          # ring_daemon on + active -> signalled

    vm._ring_setup = _Setup(active=False)
    vm.reload_daemon()
    assert vm._ring_setup.reloaded == 0          # not active -> no signal


# ---- TabletSetupVM (the setup wizard) ----------------------------------------------------------

def _setup_vm(has_ring=True, modes=4):
    import time

    from wacom_panel.core.libwacom_db import TabletSpec
    from wacom_panel.ui.viewmodels import TabletSetupVM

    pad = Tablet(name="Wacom Test", devices=[Device("Wacom Test Pad pad", 19, "PAD")])
    vm = TabletSetupVM(pad)
    vm._spec = TabletSpec(name="Wacom Test", model="TST-1", num_buttons=9 if has_ring else 4,
                          has_ring=has_ring, ring_modes=modes)
    vm._steps = vm._build_steps()
    return vm, time


def _goto(vm, step):
    while vm.currentStep != step:
        vm.nextStep()


def test_setup_steps_ring_vs_ringless(qapp):
    ring, _ = _setup_vm(has_ring=True)
    assert ring._steps == ["intro", "above", "center", "below", "done"]
    flat, _ = _setup_vm(has_ring=False)
    assert flat._steps == ["intro", "all", "done"]


def test_capture_records_into_the_current_group(qapp):
    vm, _ = _setup_vm(has_ring=True)
    _goto(vm, "above")
    vm._record(2)
    vm._record(3)
    assert vm.groupCount == 2
    _goto(vm, "center")
    vm._record(1)
    _goto(vm, "below")
    vm._record(10)
    assert vm.totalCaptured == 4  # 2 above + centre + 1 below


def test_presses_ignored_outside_capture_steps(qapp):
    vm, _ = _setup_vm(has_ring=True)
    vm._record(5)  # still on "intro"
    assert vm.totalCaptured == 0


def test_evdev_pairing_window(qapp):
    vm, time = _setup_vm(has_ring=False)
    _goto(vm, "all")
    vm._pending_evdev = ("BTN_1", time.monotonic())
    vm._record(2)                                   # recent -> paired
    vm._pending_evdev = ("BTN_2", time.monotonic() - 10)
    vm._record(3)                                   # stale -> dropped
    assert vm._above[0].evdev == "BTN_1"
    assert vm._above[1].evdev is None


def test_undo_last_pops_current_group(qapp):
    vm, _ = _setup_vm(has_ring=True)
    _goto(vm, "above")
    vm._record(2)
    vm._record(3)
    vm.undoLast()
    assert vm.groupCount == 1
    assert vm._above[0].xnum == 2


def test_finish_builds_and_saves_layout(qapp, monkeypatch):
    from wacom_panel.ui import viewmodels

    saved = {}
    monkeypatch.setattr(viewmodels, "save_user_layout", lambda data: saved.update(data) or "p")

    vm, _ = _setup_vm(has_ring=True)
    _goto(vm, "above")
    vm._pending_evdev = (None, 0)  # no evdev paired
    vm._record(2)
    vm._record(3)
    _goto(vm, "center")
    vm._record(1)
    _goto(vm, "below")
    vm._record(10)
    _goto(vm, "done")
    vm.finish()

    assert saved["display_name"] == "Wacom Test"
    assert [k["button"] for k in saved["top_keys"]] == [2, 3]
    assert [k["button"] for k in saved["bottom_keys"]] == [10]
    assert saved["ring"]["center"] == 1
    assert saved["ring"]["modes"] == 4


def test_pad_vm_needs_setup(qapp):
    from wacom_panel.core.pad_layout import PadKey, PadLayout
    from wacom_panel.ui.viewmodels import PadVM

    vm = PadVM()
    vm._layout = PadLayout(display_name="Pad", top_keys=[PadKey(2, "B")], matched=False)
    assert vm.needs_setup() is True
    vm._layout = PadLayout(display_name="Known", top_keys=[PadKey(2, "B")], matched=True)
    assert vm.needs_setup() is False
    vm._layout = PadLayout(display_name="Empty", matched=False)  # no buttons
    assert vm.needs_setup() is False


def test_refresh_ring_mode_follows_tablet(qapp, monkeypatch):
    from wacom_panel.ui import viewmodels

    vm = _pad_vm_with_ring(qapp, modes=4)
    monkeypatch.setattr(viewmodels.ring_daemon, "find_led_select", lambda: "/sys/fake")
    current = {"mode": 2}
    monkeypatch.setattr(viewmodels.ring_daemon, "read_mode", lambda _p: current["mode"])

    seen = []
    vm.ringModeChanged.connect(lambda: seen.append(vm.activeRingMode))
    vm.refreshRingMode()
    assert vm.activeRingMode == 2
    assert vm.ringModeName == "Mode 3"   # editor now targets the active mode
    assert seen == [2]

    # No change -> no further signal.
    vm.refreshRingMode()
    assert seen == [2]


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
