# `layouts/` — physical pad-layout descriptions

Each JSON file here describes one tablet model's **pad**: which `xsetwacom` button number maps
to which physical express key, plus the touch ring. Keeping this as data (not code) lets new
models be added without touching Python. Loaded by
[`../core/pad_layout.py`](../core/pad_layout.py) and surfaced spatially by `PadPage.qml`.

## Why a layout file at all

The pad's physical keys do **not** correspond to obvious button numbers, and the libwacom
letter order did not match this hardware. The only reliable source is measurement: press each
key while watching `xinput test-xi2 <pad-id>` and read the raw button number. See the
[hardware notes](../../README.md#9-hard-won-hardware-notes). A layout file records that measured
truth so the UI can show keys where they physically are.

## Schema

```jsonc
{
  "match": ["intuos pro m", "pth-660"],   // case-insensitive substrings; matched against the
                                          //   tablet device name. First file that matches wins.
  "display_name": "Wacom Intuos Pro M",   // shown as the Pad tab heading
  "_note": "...",                          // optional free text (ignored by the loader)

  "top_keys": [                            // express keys above the ring, top → bottom
    { "button": 2, "label": "Key 1" },     //   button = xsetwacom Button N (measured!)
    { "button": 3, "label": "Key 2" }
  ],
  "ring": {                                // omit entirely if the tablet has no touch ring
    "center": 1,                           //   xsetwacom Button N of the centre/mode key
    "center_label": "Mode",
    "modes": 4,                            //   display only — xsetwacom has no per-mode binding
    "cw":  "AbsWheelDown",                 //   wheel param for clockwise rotation
    "ccw": "AbsWheelUp"                    //   wheel param for counter-clockwise
  },
  "bottom_keys": [                         // express keys below the ring, top → bottom
    { "button": 10, "label": "Key 5" }
  ],

  // Raw evdev code name (e.g. "BTN_1") → xsetwacom button number. Verified by grabbing the
  // pad node (EVIOCGRAB) and pressing each key. Used by the ring daemon when pad_daemon is on
  // to translate BTN_* press events into the configured pad action. Omit (or leave empty)
  // for tablets where the pad-grab feature hasn't been mapped; they fall back to xsetwacom only.
  "evdev_buttons": {
    "BTN_0": 1,       // centre / mode-switch button — daemon NEVER re-injects this
    "BTN_1": 2
    // ...
  }
}
```

Field notes:
- **`button`** is the xsetwacom logical button number (what `xsetwacom set <pad> Button N …`
  takes), as *measured* — not a guess.
- **`cw`/`ccw`** are wheel **parameter names** (`AbsWheelUp` / `AbsWheelDown`). Which physical
  direction is which also varies by hardware and must be observed; on the PTH-660 clockwise is
  `AbsWheelDown`.
- **`modes`** is informational for the `xsetwacom` path (one `AbsWheelUp`/`Down` pair with no
  per-mode multiplexing). With `ring_daemon` on, the daemon reads the live LED index from sysfs
  and the Pad tab's per-LED-mode editor assigns a distinct action per mode; `modes` tells the
  UI how many LEDs/modes to show.
- **`evdev_buttons`** is optional. When present it enables `pad_daemon` support: the daemon maps
  the raw `BTN_*` code to a xsetwacom button number and injects the configured action as a real
  mouse button / keystroke / scroll via uinput. Populate it by grabbing the pad node and pressing
  each key (see "Adding a new tablet" below). `BTN_0` is conventionally the centre/mode button
  and must be present but is **never re-injected** by the daemon.
- Unknown keys are dropped if device detection reports a subset; an empty detection list trusts
  the file as-is. No matching file → a generic flat key list (`matched = false`).

## Adding a new tablet

1. Plug it in; find the pad id: `xsetwacom --list devices | grep -i pad`, then the X id via
   `xinput list`.
2. `xinput test-xi2 <pad-id>` and press each express key (and the ring centre) one at a time,
   noting the `RawButtonPress detail` number for each. Spin the ring each way to learn which
   direction triggers `AbsWheelUp` vs `AbsWheelDown`.
3. **Optional — `evdev_buttons` for `pad_daemon` support:** find the pad's `/dev/input/eventN`
   node (it has `ABS_WHEEL`). Run a quick script that grabs the node with `EVIOCGRAB` and logs
   `EV_KEY` events, then press each express key to record the `BTN_*` code → xsetwacom number
   mapping. Confirm that grabbing does not interfere with LED mode cycling (verified true on the
   PTH-660; the kernel HID driver updates `status_led0_select` below evdev).
4. Copy `intuos-pro-m.json`, set `match` to substrings of the device name, and fill in the
   measured `button` numbers, ring params, and (if done) `evdev_buttons`.
5. Confirm `pyproject.toml` ships `layouts/*.json` in `package-data` (it does), add a case to
   `tests/test_pad_layout.py`, and verify in the Pad tab.

> On X / `xf86-input-wacom` **without the pad daemon**, pad buttons only deliver **keystrokes**
> to apps — mouse-button/scroll actions silently fail. The Pad tab's editor is keystroke-only by
> default. With `pad_daemon` enabled (requires `evdev_buttons` in the layout + the ring daemon
> service), express keys can inject real mouse buttons and scroll via uinput.
