"""Tests for the ring-daemon installer: pure renderers + reversible group logic.

The privileged step is funnelled through an injectable ``runner``, so these never call
pkexec/sudo or touch ``/etc``.
"""

from wacom_panel.core.ring_setup import RingSetup


def _setup(tmp_path, runner, *, user="alice", sg="/usr/bin/sg"):
    return RingSetup(
        python="/usr/bin/python3",
        config_home=tmp_path,
        app_dir=tmp_path / "app",
        user=user,
        runner=runner,
        sg=sg,
    )


def test_render_udev_rule_grants_uinput_to_input_group(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    rule = s.render_udev_rule()
    assert 'KERNEL=="uinput"' in rule
    assert 'GROUP="input"' in rule
    assert 'MODE="0660"' in rule


def test_render_systemd_unit_runs_ring_daemon(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    unit = s.render_systemd_unit()
    assert "--ring-daemon" in unit
    assert "/usr/bin/python3 -m wacom_panel --ring-daemon" in unit


def test_exec_start_wraps_in_sg_when_available(tmp_path):
    # The user systemd manager lacks the 'input' group until a full re-login, so the service
    # joins it itself via sg.
    s = _setup(tmp_path, runner=lambda _s: True, sg="/usr/bin/sg")
    assert s.render_exec_start() == (
        '/usr/bin/sg input -c "exec /usr/bin/python3 -m wacom_panel --ring-daemon"'
    )


def test_exec_start_plain_without_sg(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True, sg="")
    assert s.render_exec_start() == "/usr/bin/python3 -m wacom_panel --ring-daemon"


def test_install_script_adds_group_only_when_requested(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    with_group = s.render_install_script(add_group=True)
    without_group = s.render_install_script(add_group=False)
    assert "usermod -aG input alice" in with_group
    assert "usermod" not in without_group
    # Both write the rule and reload udev.
    for script in (with_group, without_group):
        assert "70-wacom-uinput.rules" in script
        assert "udevadm control --reload-rules" in script


def test_install_writes_unit_and_runs_privileged(tmp_path):
    scripts = []
    s = _setup(tmp_path, runner=lambda script: scripts.append(script) or True)
    s.install()
    assert s.systemd_unit.exists()
    assert len(scripts) == 1
    assert "70-wacom-uinput.rules" in scripts[0]


def test_uninstall_reverts_group_only_when_marker_present(tmp_path):
    scripts = []
    s = _setup(tmp_path, runner=lambda script: scripts.append(script) or True)
    # Simulate a prior install that added the group (marker present) + a unit on disk.
    s._write(s.marker, "")
    s._write(s.systemd_unit, "unit")

    s.uninstall()

    assert not s.systemd_unit.exists()
    assert not s.marker.exists()
    # The privileged uninstall script reverts the group because the marker existed.
    assert any("gpasswd -d alice input" in script for script in scripts)


def test_uninstall_leaves_preexisting_group_membership_alone(tmp_path):
    scripts = []
    s = _setup(tmp_path, runner=lambda script: scripts.append(script) or True)
    # No marker -> we never added the user; uninstall must not remove their membership.
    s._write(s.systemd_unit, "unit")

    s.uninstall()

    assert all("gpasswd" not in script for script in scripts)


def test_install_reports_failure_when_privileged_step_fails(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: False)
    notes = s.install()
    assert any("privileged setup" in n for n in notes)
    # No user service should be written if the privileged step failed.
    assert not s.systemd_unit.exists()
