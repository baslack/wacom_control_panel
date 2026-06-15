"""Install / uninstall the ring daemon — the one part of the app that needs privilege.

The ring daemon (and the setup wizard's button-capture) need to read the pad's evdev node and
write ``/dev/uinput``. Rather than add the user to the broad ``input`` group (read access to
*every* input device, incl. keyboards — and a re-login), we grant **least-privilege** access with
``uaccess`` udev rules: logind hands the *logged-in seat user* a per-device ACL, applied
immediately (no re-login). Two rule files, both ours and fully reversible:

* ``70-wacom-uinput.rules`` — tags ``/dev/uinput`` ``uaccess`` (kept ``GROUP=input`` too as a
  harmless fallback for non-logind seats);
* ``70-wacom-pad-uaccess.rules`` — one ``uaccess`` line **per set-up tablet** (matched by its USB
  ids), so access is scoped to exactly the devices the user has configured — never a vendor-wide
  blanket.

The ``systemd --user`` service that runs ``--ring-daemon`` needs no root and is managed here too
(mirroring :class:`wacom_panel.core.persistence.Persistence`). All ``render_*`` methods are pure
strings so they unit-test without touching the system; the privileged step is funnelled through
one injectable ``runner`` for the same reason. Device USB ids are passed in by callers (the wizard
/ CLI) so this module stays free of any evdev/daemon import.
"""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

RING_SERVICE_NAME = "wacom-control-panel-ring.service"
UINPUT_RULE_PATH = Path("/etc/udev/rules.d/70-wacom-uinput.rules")
PAD_RULE_PATH = Path("/etc/udev/rules.d/70-wacom-pad-uaccess.rules")
WACOM_VENDOR = "056a"

# A privileged runner takes a bash script and returns True on success. Default uses pkexec/sudo.
Runner = Callable[[str], bool]

# A (vendor, product) USB id pair, each a 4-digit lowercase hex string.
Device = tuple[str, str]

_PAD_LINE_RE = re.compile(
    r'idVendor\}=="([0-9a-fA-F]{4})".*?idProduct\}=="([0-9a-fA-F]{4})"'
)


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))


def _default_runner(script: str) -> bool:
    """Run ``script`` as root via pkexec (GUI prompt) or sudo (terminal). False if neither works."""
    for launcher in (["pkexec", "bash", "-c", script], ["sudo", "bash", "-c", script]):
        try:
            subprocess.run(launcher, check=True)
            return True
        except FileNotFoundError:
            continue  # this launcher isn't installed; try the next
        except subprocess.CalledProcessError:
            return False  # launcher ran but the user cancelled / it failed
    return False


def _default_systemctl(*args: str) -> bool:
    """Run a ``systemctl --user`` subcommand; True on success."""
    try:
        subprocess.run(
            ["systemctl", "--user", *args],
            check=True, capture_output=True, text=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _norm_id(value: str) -> str:
    """Normalise a USB id to 4-digit lowercase hex (accepts ints, '0x..', mixed case)."""
    text = str(value).lower().removeprefix("0x")
    return text.zfill(4)[-4:]


def parse_pad_devices(text: str) -> list[Device]:
    """Extract the (vendor, product) pairs already granted in a pad-rule file's contents."""
    seen: list[Device] = []
    for match in _PAD_LINE_RE.finditer(text):
        device = (_norm_id(match.group(1)), _norm_id(match.group(2)))
        if device not in seen:
            seen.append(device)
    return seen


def granted_pad_devices(path: Path = PAD_RULE_PATH) -> list[Device]:
    """The tablets already granted pad access (read from the world-readable rule file)."""
    try:
        return parse_pad_devices(path.read_text())
    except OSError:
        return []


def merge_devices(existing: list[Device], vendor: str, product: str) -> list[Device]:
    """``existing`` plus this device (normalised), de-duplicated, order preserved."""
    device = (_norm_id(vendor), _norm_id(product))
    return existing if device in existing else [*existing, device]


class RingSetup:
    """Reversible installer for the ring daemon's permissions + user service (uaccess-based)."""

    def __init__(
        self,
        python: str | None = None,
        config_home: Path | None = None,
        app_dir: Path | None = None,
        user: str | None = None,
        runner: Runner | None = None,
        systemctl: Callable[..., bool] | None = None,
    ) -> None:
        self.python = python or sys.executable
        self.config_home = config_home or _config_home()
        self.app_dir = app_dir or (self.config_home / "wacom-control-panel")
        self.user = user or getpass.getuser()
        self._run_privileged = runner or _default_runner
        # Injectable so tests never touch the real `systemctl --user` (its enable/disable target
        # the global service *name*, not our tmp config dir — a real side effect otherwise).
        self._systemctl = systemctl or _default_systemctl

    # ---- paths ------------------------------------------------------------
    @property
    def systemd_unit(self) -> Path:
        return self.config_home / "systemd" / "user" / RING_SERVICE_NAME

    # ---- rendering (pure) -------------------------------------------------
    def render_uinput_rule(self) -> str:
        return (
            "# Generated by Wacom Control Panel — lets the ring daemon emit synthetic scroll.\n"
            'KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="input", '
            'OPTIONS+="static_node=uinput", TAG+="uaccess"\n'
        )

    def render_pad_rule(self, devices: list[Device]) -> str:
        """A uaccess line per set-up tablet — least privilege, scoped to these USB ids only.

        ``ENV{ID_INPUT_TABLET_PAD}=="1"`` narrows the grant to the **pad** interface alone, so the
        tablet's pen/touch nodes are left untouched (the daemon and wizard only need the pad).
        """
        lines = [
            "# Generated by Wacom Control Panel — grants the logged-in user access to each",
            "# set-up tablet's PAD interface only (these devices, the active seat user; no group).",
        ]
        for vendor, product in devices:
            lines.append(
                f'SUBSYSTEM=="input", ATTRS{{idVendor}}=="{_norm_id(vendor)}", '
                f'ATTRS{{idProduct}}=="{_norm_id(product)}", '
                'ENV{ID_INPUT_TABLET_PAD}=="1", TAG+="uaccess"'
            )
        return "\n".join(lines) + "\n"

    def render_exec_start(self) -> str:
        """The unit ExecStart — plain; uaccess grants the service access with no ``sg`` wrapper."""
        return f"{self.python} -m wacom_panel --ring-daemon"

    def render_systemd_unit(self) -> str:
        return (
            "[Unit]\n"
            "Description=Wacom Control Panel — touch-ring scroll daemon\n"
            "After=graphical-session.target\n"
            "PartOf=graphical-session.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            "Environment=PYTHONUNBUFFERED=1\n"  # so the daemon's status reaches the journal live
            f"ExecStart={self.render_exec_start()}\n"
            "Restart=on-failure\n"
            "RestartSec=3\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    @staticmethod
    def _pad_trigger_lines(devices: list[Device]) -> list[str]:
        # `--action=change` (NOT add): on an already-connected device `add` is a no-op for the
        # uaccess builtin, so the ACL wouldn't apply until the next replug. Match by the udev
        # *properties* (idVendor lives on the parent USB device, not the event node's own attrs).
        lines = []
        for vendor, product in devices:
            lines.append(
                "udevadm trigger --action=change --subsystem-match=input "
                f"--property-match=ID_VENDOR_ID={_norm_id(vendor)} "
                f"--property-match=ID_MODEL_ID={_norm_id(product)} || true"
            )
        return lines

    def render_install_script(self, pad_devices: list[Device]) -> str:
        lines = [
            "set -e",
            f"cat > {UINPUT_RULE_PATH} <<'EOF'",
            self.render_uinput_rule().rstrip("\n"),
            "EOF",
        ]
        if pad_devices:
            lines += [
                f"cat > {PAD_RULE_PATH} <<'EOF'",
                self.render_pad_rule(pad_devices).rstrip("\n"),
                "EOF",
            ]
        lines.append("udevadm control --reload-rules")
        lines.append("udevadm trigger --action=change /sys/class/misc/uinput || true")
        lines += self._pad_trigger_lines(pad_devices)
        return "\n".join(lines) + "\n"

    def render_grant_script(self, pad_devices: list[Device]) -> str:
        """Rewrite the pad rule with the full device set, reload, and apply to those devices."""
        lines = [
            "set -e",
            f"cat > {PAD_RULE_PATH} <<'EOF'",
            self.render_pad_rule(pad_devices).rstrip("\n"),
            "EOF",
            "udevadm control --reload-rules",
        ]
        lines += self._pad_trigger_lines(pad_devices)
        return "\n".join(lines) + "\n"

    def render_uninstall_script(self) -> str:
        return (
            f"rm -f {UINPUT_RULE_PATH} {PAD_RULE_PATH}\n"
            "udevadm control --reload-rules\n"
        )

    # ---- state ------------------------------------------------------------
    def is_installed(self) -> bool:
        return self.systemd_unit.exists()

    def is_active(self) -> bool:
        """True if the ``systemd --user`` ring service is currently running."""
        return self._systemctl("is-active", "--quiet", RING_SERVICE_NAME)

    def reload(self) -> bool:
        """SIGHUP the running ring service so it re-reads the saved profile (e.g. after a Save)."""
        return self._systemctl("kill", "-s", "HUP", RING_SERVICE_NAME)

    # ---- side effects -----------------------------------------------------
    def grant_pad_access(self, vendor: str, product: str) -> bool:
        """Add a uaccess rule for this tablet's pad and apply it now. True if the root step ran.

        Caller should verify real access afterwards (e.g. re-open the evdev node), since uaccess
        only takes on a logind seat. Idempotent: re-granting an already-listed device is a no-op
        write that still re-applies the ACL.
        """
        devices = merge_devices(granted_pad_devices(), vendor, product)
        return self._run_privileged(self.render_grant_script(devices))

    def install(self, pad_devices: list[Device] | None = None) -> list[str]:
        """Grant permissions (uinput + any connected pad) + install the user service."""
        notes: list[str] = []
        pad_devices = pad_devices or []

        if not self._run_privileged(self.render_install_script(pad_devices)):
            notes.append(
                "Could not apply the privileged setup (udev uaccess rules). "
                "Re-run with pkexec/sudo available, or apply it manually."
            )
            return notes

        if not pad_devices:
            notes.append(
                "No tablet was connected, so only /dev/uinput was set up. Run the Pad tab's "
                "setup for each tablet to grant its buttons access."
            )

        # User service (no root needed).
        self._write(self.systemd_unit, self.render_systemd_unit())
        if not self._systemctl("daemon-reload") or not self._systemctl(
            "enable", "--now", RING_SERVICE_NAME
        ):
            notes.append(
                "Could not enable the ring daemon service automatically. "
                f"Run: systemctl --user enable --now {RING_SERVICE_NAME}"
            )
        return notes

    def uninstall(self) -> list[str]:
        """Remove the service + both udev rules. Nothing to revert in any group membership."""
        notes: list[str] = []
        self._systemctl("disable", "--now", RING_SERVICE_NAME)
        self.systemd_unit.unlink(missing_ok=True)
        self._systemctl("daemon-reload")

        if not self._run_privileged(self.render_uninstall_script()):
            notes.append(
                "Could not remove the udev rules automatically; delete "
                f"{UINPUT_RULE_PATH} and {PAD_RULE_PATH} manually."
            )
        return notes

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
