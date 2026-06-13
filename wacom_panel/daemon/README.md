# `daemon/` — touch-ring scroll daemon

The touch ring is reported by the kernel as an **absolute** axis (`ABS_WHEEL`). `xsetwacom`
can only bind it to *keystrokes* — it cannot emit `REL_WHEEL` (relative scroll), which is what
applications actually want, so the rest of the app falls back to mapping the ring to arrow
keys. This subpackage closes that gap: it reads the ring's raw events via **`python-evdev`**
and injects synthetic `REL_WHEEL` via **`uinput`**, *below* libinput — so it works on **X11 and
Wayland** alike.

```
daemon/
├── ring_translator.py   # pure: ABS_WHEEL positions → scroll ticks (no evdev, unit-tested)
└── ring_daemon.py       # thin evdev/uinput I/O loop around the translator
```

## Layering

`daemon` sits beside `core`/`backend` in the dependency graph: it imports **`core` (pure data
only)** and may import `evdev`; nothing in `core`/`backend` imports `daemon`. As everywhere in
this repo, the *logic* (`ring_translator.py`) is separated from the *I/O* (`ring_daemon.py`) so
the math is testable without a tablet — see `tests/test_ring_translator.py`.

## `ring_translator.py` — the math (pure)

`RingTranslator` converts successive absolute ring positions into relative wheel ticks:

- the **first sample** after a touch is a baseline (emits nothing);
- **finger-lift** (value `0`) resets the baseline, so the next touch never produces a jump;
- motion takes the **shortest path** around the wrap seam (e.g. `71 → 1` is `+2`, not `−70`);
- the encoder's fine resolution (~72 steps/rev) is **damped** to ~24 wheel ticks/rev, carrying
  the remainder so a slow drag still scrolls;
- the per-LED-**mode** action table (`PadConfig.ring_modes`) is consulted, defaulting to
  scroll-down clockwise / scroll-up counter-clockwise. `invert=` flips direction if a given
  unit's encoder counts the other way.

It returns `Emit(kind, value)` items (`"wheel"` → a `REL_WHEEL` delta; `"key"` reserved for a
later phase).

## `ring_daemon.py` — the loop (I/O)

`RingDaemon.run()`:

1. creates a `uinput` device advertising `REL_WHEEL`;
2. discovers the pad evdev node (name contains *wacom* + *pad*, has `ABS_WHEEL`) and reads its
   true `ABS_WHEEL` maximum to size the translator;
3. discovers the active-mode sysfs file by glob
   (`/sys/bus/hid/drivers/wacom/*/wacom_led/status_led0_select` — the HID id varies per unit);
4. on each `ABS_WHEEL` event reads the current mode and injects the translator's output —
   **only when the active profile has `ring_daemon` enabled** (otherwise the ring is driven by
   the `xsetwacom` keystroke fallback and the daemon stays out of the way);
5. reloads the active profile on **`SIGHUP`**, shuts down cleanly on **`SIGTERM`/`SIGINT`**, and
   **re-acquires** the device if the tablet is unplugged.

It does **not** grab the pad exclusively, so the express keys keep working through `xsetwacom`.
When the daemon owns the ring, `engine.pad_commands` sets the ring's `AbsWheel*` params to `"0"`
so the X driver doesn't double up with the daemon's scroll.

## Permissions & lifecycle

Reading the pad node needs the **`input` group**; writing `/dev/uinput` needs access (granted
on a desktop session by the logind *uaccess* ACL, and by a udev rule otherwise). Both — plus a
`systemd --user` service that runs `--ring-daemon` — are installed and **fully reverted** by
`wacom_panel/core/ring_setup.py` (`wacom-panel --install-ring-daemon` /
`--uninstall-ring-daemon`). This privileged setup is the only non-root-free part of the app.

`evdev` is the optional **`daemon`** extra; if it's missing, `--ring-daemon` exits with a clear
message instead of crashing (mirroring the optional `pyudev` path in `core/watcher.py`).
