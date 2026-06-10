"""Thin wrapper around the ``xsetwacom`` command-line tool.

Every call uses the argv-list form of :func:`subprocess.run`, so device names that
contain spaces (e.g. ``"Wacom Intuos Pro M Pen stylus"``) need no shell quoting.

A module-level ``dry_run`` switch (or per-call override) makes mutating calls return the
command that *would* run instead of executing it — used by the ``--dry-run`` CLI and tests.
"""

from __future__ import annotations

import shutil
import subprocess

#: Default binary; overridable for tests / unusual installs.
BINARY = "xsetwacom"

#: When True, :func:`set_param` / :func:`reset_area` only build & return the command.
dry_run = False


class XsetwacomError(RuntimeError):
    """Raised when an xsetwacom invocation exits non-zero."""


def is_available() -> bool:
    """True if the xsetwacom binary is on PATH."""
    return shutil.which(BINARY) is not None


def _run(args: list[str]) -> str:
    cmd = [BINARY, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:  # binary missing
        raise XsetwacomError(f"{BINARY} not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or "").strip()
        raise XsetwacomError(f"{' '.join(cmd)} failed: {msg}") from exc
    return proc.stdout


def list_devices_raw() -> str:
    """Raw text of ``xsetwacom --list devices``."""
    return _run(["--list", "devices"])


def get(device: str, param: str, *extra: str) -> str:
    """Return the current value of ``param`` for ``device`` (stripped)."""
    return _run(["--get", device, param, *extra]).strip()


def get_shell(device: str) -> str:
    """Raw ``--shell`` dump of all parameters for ``device``."""
    return _run(["--shell", device])


def get_shell_all(device: str) -> str:
    """Shell-format dump of every parameter (``-s --get <device> all``).

    Unlike plain ``--get``, this prints button/action parameters as ``set`` commands, so it can
    be parsed to discover which buttons a device actually has.
    """
    return _run(["-s", "--get", device, "all"])


def build_set_command(device: str, param: str, *values: object) -> list[str]:
    """Build the argv for a ``--set`` call (no execution). Pure, used by apply-script gen."""
    return [BINARY, "--set", device, param, *(str(v) for v in values)]


def set_param(device: str, param: str, *values: object, dry: bool | None = None) -> list[str]:
    """Set ``param`` on ``device``. Returns the command argv that was (or would be) run.

    Honours the module-level :data:`dry_run` unless overridden by ``dry``.
    """
    cmd = build_set_command(device, param, *values)
    if dry if dry is not None else dry_run:
        return cmd
    _run(cmd[1:])
    return cmd


def reset_area(device: str, *, dry: bool | None = None) -> list[str]:
    """Reset ``device`` Area to the full tablet (``ResetArea``)."""
    cmd = [BINARY, "--set", device, "ResetArea"]
    if dry if dry is not None else dry_run:
        return cmd
    _run(cmd[1:])
    return cmd
