# Wacom Control Panel

A graphical [`xsetwacom`](https://github.com/linuxwacom/xf86-input-wacom) frontend for
Linux/X11, built with PySide6. Its centerpiece is a visual tablet-to-display mapping editor
with **forced proportions** — aspect-correct, distortion-free mapping that the stock control
panels lack — plus named profiles that survive reboot, logout, and replug.

> **X11 only.** `xsetwacom` does not work under Wayland. The app detects your session type
> and warns rather than misbehaving.

## Why

Mapping a 16:10 tablet (e.g. Intuos Pro M, native area 44704×27940) onto a 16:9 monitor
stretches the pen. "Force proportions" shrinks the tablet's active *Area* to letterbox-match
the target output's aspect ratio, so circles stay circular while keeping the maximum usable
tablet surface.

## Status

Under active development. See `eager-orbiting-salamander.md` plan / the build phases:

- **Phase 0** — backend wrapper, core mapping math, headless CLI, tests.
- **Phase 1** — MVP visual mapping UI with profiles. *(usable milestone)*
- **Phase 2** — auto-reapply persistence (login autostart + replug watcher).
- **Phase 3** — pressure curve, pen/pad buttons, touch toggles.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,udev]"

# headless smoke test (no GUI, no changes applied)
python -m wacom_panel --list
python -m wacom_panel --apply --output DP-4 --force-proportions --dry-run

# run the GUI
python -m wacom_panel
# tests
pytest
```

## Persistence (auto-reapply)

`xsetwacom` settings are runtime-only. Enable the "Reapply active profile on login & device
replug" toggle in the app (or use the CLI) to keep your mapping alive — no root required:

```sh
python -m wacom_panel --install-persistence     # login autostart + systemd --user watcher
python -m wacom_panel --uninstall-persistence
python -m wacom_panel --apply-active             # apply the active profile now (used by hooks)
python -m wacom_panel --watch                    # hotplug watcher (the service runs this)
```

`--install-persistence` writes an XDG autostart entry (applies at login) and a
`systemd --user` service that runs the hotplug watcher (reapplies on replug). The watcher uses
`pyudev` when available and otherwise polls.

## License

MIT
