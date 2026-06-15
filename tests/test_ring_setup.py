"""Tests for the ring-daemon installer: pure renderers + the uaccess permission model.

The privileged step is funnelled through an injectable ``runner``, so these never call
pkexec/sudo or touch ``/etc``.
"""

from wacom_panel.core.ring_setup import (
    RingSetup,
    granted_pad_devices,
    merge_devices,
    parse_pad_devices,
)


def _setup(tmp_path, runner, *, user="alice", systemctl=None):
    # systemctl defaults to a no-op so tests never start/stop/enable the *real* user service
    # (its commands target the global service name, not our tmp config dir).
    return RingSetup(
        python="/usr/bin/python3",
        config_home=tmp_path,
        app_dir=tmp_path / "app",
        user=user,
        runner=runner,
        systemctl=systemctl or (lambda *a: True),
    )


# ---- pure renderers ----------------------------------------------------------------------------

def test_uinput_rule_tags_uaccess_and_keeps_group_fallback(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    rule = s.render_uinput_rule()
    assert 'KERNEL=="uinput"' in rule
    assert 'TAG+="uaccess"' in rule      # the least-privilege grant
    assert 'GROUP="input"' in rule       # harmless non-logind fallback


def test_pad_rule_is_per_device_uaccess(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    rule = s.render_pad_rule([("056a", "0315")])
    assert 'ATTRS{idVendor}=="056a"' in rule
    assert 'ATTRS{idProduct}=="0315"' in rule
    assert 'TAG+="uaccess"' in rule
    # Narrowed to the pad interface only — pen/touch nodes of the same tablet are untouched.
    assert 'ENV{ID_INPUT_TABLET_PAD}=="1"' in rule
    # Exactly one match line — no vendor-wide blanket.
    assert rule.count("SUBSYSTEM==") == 1


def test_pad_rule_normalises_ids(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    rule = s.render_pad_rule([("0x56A", "315")])  # mixed case / short / 0x prefix
    assert 'ATTRS{idVendor}=="056a"' in rule
    assert 'ATTRS{idProduct}=="0315"' in rule


def test_exec_start_is_plain_no_sg(tmp_path):
    # uaccess grants the service access by uid, so no `sg input` wrapper is needed any more.
    s = _setup(tmp_path, runner=lambda _s: True)
    assert s.render_exec_start() == "/usr/bin/python3 -m wacom_panel --ring-daemon"
    assert "sg " not in s.render_systemd_unit()


# ---- granted-device parsing --------------------------------------------------------------------

def test_parse_and_merge_pad_devices(tmp_path):
    text = (
        'SUBSYSTEM=="input", ATTRS{idVendor}=="056a", ATTRS{idProduct}=="0315", TAG+="uaccess"\n'
        'SUBSYSTEM=="input", ATTRS{idVendor}=="056a", ATTRS{idProduct}=="033e", TAG+="uaccess"\n'
    )
    assert parse_pad_devices(text) == [("056a", "0315"), ("056a", "033e")]
    # merge is idempotent + normalising
    assert merge_devices([("056a", "0315")], "056A", "0315") == [("056a", "0315")]
    assert merge_devices([("056a", "0315")], "056a", "033e") == [
        ("056a", "0315"), ("056a", "033e")
    ]


def test_granted_pad_devices_reads_file(tmp_path):
    path = tmp_path / "pad.rules"
    path.write_text(
        'SUBSYSTEM=="input", ATTRS{idVendor}=="056a", ATTRS{idProduct}=="0315", TAG+="uaccess"\n'
    )
    assert granted_pad_devices(path) == [("056a", "0315")]
    assert granted_pad_devices(tmp_path / "missing.rules") == []  # absent -> empty


# ---- install / grant / uninstall scripts -------------------------------------------------------

def test_install_script_writes_both_rules_and_triggers_change(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    script = s.render_install_script([("056a", "0315")])
    assert "70-wacom-uinput.rules" in script
    assert "70-wacom-pad-uaccess.rules" in script
    assert "udevadm control --reload-rules" in script
    # The spike gotcha: must be --action=change (add is a no-op on a connected device).
    assert "--action=change" in script
    assert "--action=add" not in script
    # No input-group juggling anywhere.
    assert "usermod" not in script and "gpasswd" not in script


def test_install_script_without_pad_only_does_uinput(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    script = s.render_install_script([])
    assert "70-wacom-uinput.rules" in script
    assert "70-wacom-pad-uaccess.rules" not in script


def test_grant_pad_access_appends_idempotently(tmp_path, monkeypatch):
    import wacom_panel.core.ring_setup as rs

    scripts = []
    monkeypatch.setattr(rs, "granted_pad_devices", lambda *a, **k: [("056a", "0315")])
    s = _setup(tmp_path, runner=lambda script: scripts.append(script) or True)

    assert s.grant_pad_access("056a", "033e") is True
    # Full set rewritten (existing + new), applied with a change trigger.
    assert 'ATTRS{idProduct}=="0315"' in scripts[0]
    assert 'ATTRS{idProduct}=="033e"' in scripts[0]
    assert "--action=change" in scripts[0]

    # Re-granting an already-listed device still runs (re-applies ACL) but doesn't duplicate.
    scripts.clear()
    assert s.grant_pad_access("056a", "0315") is True
    assert scripts[0].count('ATTRS{idProduct}=="0315"') == 1


def test_grant_pad_access_false_when_privileged_fails(tmp_path, monkeypatch):
    import wacom_panel.core.ring_setup as rs
    monkeypatch.setattr(rs, "granted_pad_devices", lambda *a, **k: [])
    s = _setup(tmp_path, runner=lambda _s: False)
    assert s.grant_pad_access("056a", "0315") is False


def test_uninstall_script_removes_both_rules_no_group(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    script = s.render_uninstall_script()
    assert "70-wacom-uinput.rules" in script
    assert "70-wacom-pad-uaccess.rules" in script
    assert "gpasswd" not in script and "usermod" not in script


# ---- install / uninstall side effects ----------------------------------------------------------

def test_install_writes_unit_and_runs_privileged(tmp_path):
    scripts = []
    s = _setup(tmp_path, runner=lambda script: scripts.append(script) or True)
    s.install([("056a", "0315")])
    assert s.systemd_unit.exists()
    assert len(scripts) == 1
    assert "70-wacom-uinput.rules" in scripts[0]


def test_install_without_tablet_notes_uinput_only(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: True)
    notes = s.install([])
    assert any("uinput" in n for n in notes)


def test_uninstall_removes_unit_and_rules(tmp_path):
    scripts = []
    s = _setup(tmp_path, runner=lambda script: scripts.append(script) or True)
    s._write(s.systemd_unit, "unit")
    s.uninstall()
    assert not s.systemd_unit.exists()
    assert any("70-wacom-pad-uaccess.rules" in script for script in scripts)


def test_install_and_uninstall_use_injected_systemctl(tmp_path):
    # Guards against the tests (or anything else) shelling out to the real `systemctl --user`,
    # whose enable/disable act on the global service name regardless of config_home.
    calls = []
    s = _setup(tmp_path, runner=lambda _s: True,
               systemctl=lambda *a: calls.append(a) or True)
    s.install([("056a", "0315")])
    assert ("daemon-reload",) in calls
    assert ("enable", "--now", "wacom-control-panel-ring.service") in calls

    calls.clear()
    s.uninstall()
    assert ("disable", "--now", "wacom-control-panel-ring.service") in calls


def test_is_active_queries_systemctl(tmp_path):
    calls = []
    s = _setup(tmp_path, runner=lambda _s: True,
               systemctl=lambda *a: calls.append(a) or True)
    assert s.is_active() is True
    assert ("is-active", "--quiet", "wacom-control-panel-ring.service") in calls

    s_off = _setup(tmp_path, runner=lambda _s: True, systemctl=lambda *a: False)
    assert s_off.is_active() is False


def test_reload_sends_sighup_via_systemctl(tmp_path):
    calls = []
    s = _setup(tmp_path, runner=lambda _s: True,
               systemctl=lambda *a: calls.append(a) or True)
    assert s.reload() is True
    assert ("kill", "-s", "HUP", "wacom-control-panel-ring.service") in calls


def test_install_reports_failure_when_privileged_step_fails(tmp_path):
    s = _setup(tmp_path, runner=lambda _s: False)
    notes = s.install([("056a", "0315")])
    assert any("privileged setup" in n for n in notes)
    # No user service should be written if the privileged step failed.
    assert not s.systemd_unit.exists()
