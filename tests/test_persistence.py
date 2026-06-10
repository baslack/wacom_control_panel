"""Tests for the persistence hook rendering and (sandboxed) install/uninstall."""

from wacom_panel.core.persistence import AUTOSTART_NAME, SERVICE_NAME, Persistence


def _persistence(tmp_path):
    return Persistence(python="/opt/venv/bin/python", config_home=tmp_path)


def test_render_apply_script(tmp_path):
    p = _persistence(tmp_path)
    script = p.render_apply_script()
    assert script.startswith("#!/usr/bin/env bash")
    assert '"/opt/venv/bin/python" -m wacom_panel --apply-active' in script


def test_render_autostart_points_at_script(tmp_path):
    p = _persistence(tmp_path)
    desktop = p.render_autostart()
    assert "[Desktop Entry]" in desktop
    assert f"Exec={p.apply_script}" in desktop
    assert p.autostart_file.name == AUTOSTART_NAME


def test_render_systemd_unit(tmp_path):
    p = _persistence(tmp_path)
    unit = p.render_systemd_unit()
    assert "ExecStart=/opt/venv/bin/python -m wacom_panel --watch" in unit
    assert "WantedBy=default.target" in unit
    assert p.systemd_unit.name == SERVICE_NAME


def test_install_writes_files_and_uninstall_removes(tmp_path):
    p = _persistence(tmp_path)
    assert not p.is_installed()
    # systemctl will not be available/effective in the sandbox; install tolerates that.
    p.install(enable_watch=False)
    assert p.is_installed()
    assert p.apply_script.exists()
    assert p.autostart_file.exists()
    assert p.systemd_unit.exists()
    assert p.apply_script.stat().st_mode & 0o111  # executable

    p.uninstall()
    assert not p.is_installed()
    assert not p.apply_script.exists()
    assert not p.systemd_unit.exists()
