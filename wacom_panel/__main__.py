"""Command-line entry point.

With no action flag it launches the GUI. ``--list`` and ``--apply`` provide a headless path
for scripting and for verifying mappings without the Qt UI.
"""

from __future__ import annotations

import argparse
import sys

from .backend import devices, displays, xsetwacom
from .core.engine import apply_mapping, mapping_commands, tablet_native_area
from .core.persistence import Persistence
from .core.profile import MappingConfig
from .core.store import ProfileStore
from .core.watcher import apply_active, watch


def _cmd_list() -> int:
    if not xsetwacom.is_available():
        print("xsetwacom not found on PATH.", file=sys.stderr)
        return 1
    tablets = devices.list_tablets()
    if not tablets:
        print("No Wacom devices detected.")
    for tab in tablets:
        tw, th = tablet_native_area(tab)
        print(f"Tablet: {tab.name}  (native area {tw} x {th}, aspect {tw / th:.3f})")
        for dev in tab.devices:
            print(f"    [{dev.id:>3}] {dev.type:<7} {dev.name}")
    print()
    outs = displays.list_outputs()
    print("Outputs:")
    for o in outs:
        star = " *primary" if o.primary else ""
        print(f"    {o.name:<10} {o.width}x{o.height}+{o.x}+{o.y}  aspect {o.aspect:.3f}{star}")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    tablets = devices.list_tablets()
    if not tablets:
        print("No Wacom devices detected.", file=sys.stderr)
        return 1
    tablet = tablets[0]
    outs = displays.list_outputs()

    mapping = MappingConfig(
        output=args.output,
        force_proportions=args.force_proportions,
        rotate=args.rotate,
        mode=args.mode,
        zoom=args.zoom,
        apply_to_touch=args.touch,
    )
    commands = mapping_commands(mapping, tablet, outs)
    if args.dry_run:
        for cmd in commands:
            print(" ".join(_quote(c) for c in cmd))
        return 0
    apply_mapping(mapping, tablet, outs, dry_run=False)
    print(f"Applied mapping to {tablet.name} "
          f"({'whole desktop' if not args.output else args.output}).")
    return 0


def _cmd_apply_active() -> int:
    return 0 if apply_active(ProfileStore()) else 1


def _cmd_watch() -> int:
    return watch(ProfileStore())


def _cmd_persistence(install: bool) -> int:
    p = Persistence()
    if install:
        notes = p.install()
        print(f"Installed login autostart + hotplug watcher under {p.app_dir.parent}.")
        for note in notes:
            print(f"  note: {note}")
    else:
        p.uninstall()
        print("Removed auto-reapply hooks.")
    return 0


def _cmd_ring_daemon() -> int:
    from .daemon.ring_daemon import run as run_ring_daemon
    return run_ring_daemon()


def _connected_pad_ids() -> list[tuple[str, str]]:
    """The connected pad's (vendor, product) hex ids, so install can grant its access too."""
    from .daemon import ring_daemon
    dev = ring_daemon.find_pad_device() if ring_daemon.is_available() else None
    if dev is None:
        return []
    try:
        return [(f"{dev.info.vendor:04x}", f"{dev.info.product:04x}")]
    finally:
        dev.close()


def _cmd_ring_setup(install: bool) -> int:
    from .core.ring_setup import RingSetup
    setup = RingSetup()
    notes = setup.install(_connected_pad_ids()) if install else setup.uninstall()
    print("Installed ring daemon (permissions + user service)." if install
          else "Removed ring daemon (permissions + user service).")
    for note in notes:
        print(f"  note: {note}")
    return 0


def _quote(token: str) -> str:
    return f'"{token}"' if " " in token else token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wacom-panel", description=__doc__)
    parser.add_argument("--list", action="store_true", help="list tablets and outputs, then exit")
    parser.add_argument("--apply", action="store_true", help="apply a mapping headlessly")
    parser.add_argument("--output",
                        help="target output connector (e.g. DP-4); omit for whole desktop")
    parser.add_argument("--force-proportions", action="store_true",
                        help="letterbox the tablet area to match the output aspect")
    parser.add_argument("--rotate", default="none", choices=["none", "cw", "ccw", "half"])
    parser.add_argument("--mode", default="Absolute", choices=["Absolute", "Relative"])
    parser.add_argument("--zoom", type=float, default=1.0, help="0<zoom<=1, use less of the tablet")
    parser.add_argument("--touch", action="store_true", help="also map the touch device")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    parser.add_argument("--apply-active", action="store_true",
                        help="apply the active saved profile (used by login/hotplug hooks)")
    parser.add_argument("--watch", action="store_true",
                        help="run the hotplug watcher (reapply on device reconnect)")
    parser.add_argument("--install-persistence", action="store_true",
                        help="install login autostart + systemd --user hotplug watcher")
    parser.add_argument("--uninstall-persistence", action="store_true",
                        help="remove the auto-reapply hooks")
    parser.add_argument("--ring-daemon", action="store_true",
                        help="run the touch-ring scroll daemon (evdev -> uinput REL_WHEEL)")
    parser.add_argument("--install-ring-daemon", action="store_true",
                        help="grant ring-daemon permissions (per-device uaccess udev rules) and "
                             "enable its user service")
    parser.add_argument("--uninstall-ring-daemon", action="store_true",
                        help="remove the ring daemon's permissions and user service")
    args = parser.parse_args(argv)

    if args.list:
        return _cmd_list()
    if args.apply_active:
        return _cmd_apply_active()
    if args.watch:
        return _cmd_watch()
    if args.install_persistence:
        return _cmd_persistence(install=True)
    if args.uninstall_persistence:
        return _cmd_persistence(install=False)
    if args.ring_daemon:
        return _cmd_ring_daemon()
    if args.install_ring_daemon:
        return _cmd_ring_setup(install=True)
    if args.uninstall_ring_daemon:
        return _cmd_ring_setup(install=False)
    if args.apply:
        return _cmd_apply(args)

    # Default: launch the GUI.
    from .app import main as gui_main
    return gui_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
