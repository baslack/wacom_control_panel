"""Command-line entry point.

With no action flag it launches the GUI. ``--list`` and ``--apply`` provide a headless path
for scripting and for verifying mappings without the Qt UI.
"""

from __future__ import annotations

import argparse
import sys

from .backend import devices, displays, xsetwacom
from .core.engine import apply_mapping, mapping_commands, tablet_native_area
from .core.profile import MappingConfig


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
    args = parser.parse_args(argv)

    if args.list:
        return _cmd_list()
    if args.apply:
        return _cmd_apply(args)

    # Default: launch the GUI.
    from .app import main as gui_main
    return gui_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
