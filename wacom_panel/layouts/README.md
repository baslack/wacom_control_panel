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
  ]
}
```

Field notes:
- **`button`** is the xsetwacom logical button number (what `xsetwacom set <pad> Button N …`
  takes), as *measured* — not a guess.
- **`cw`/`ccw`** are wheel **parameter names** (`AbsWheelUp` / `AbsWheelDown`). Which physical
  direction is which also varies by hardware and must be observed; on the PTH-660 clockwise is
  `AbsWheelDown`.
- **`modes`** is informational. `xsetwacom` exposes a single ring action pair with no per-mode
  multiplexing (the mode LED cycling is a proprietary-driver feature), so the centre key is just
  a normal bindable button.
- Unknown keys are dropped if device detection reports a subset; an empty detection list trusts
  the file as-is. No matching file → a generic flat key list (`matched = false`).

## Adding a new tablet

1. Plug it in; find the pad id: `xsetwacom --list devices | grep -i pad`, then the X id via
   `xinput list`.
2. `xinput test-xi2 <pad-id>` and press each express key (and the ring centre) one at a time,
   noting the `RawButtonPress detail` number for each. Spin the ring each way to learn which
   direction triggers `AbsWheelUp` vs `AbsWheelDown`.
3. Copy `intuos-pro-m.json`, set `match` to substrings of the device name, and fill in the
   measured `button` numbers and ring params.
4. Confirm `pyproject.toml` ships `layouts/*.json` in `package-data` (it does), add a case to
   `tests/test_pad_layout.py`, and verify in the Pad tab.

> Reminder: on X / `xf86-input-wacom`, pad buttons only deliver **keystrokes** to apps — mouse-
> button/scroll actions silently fail — so bind keys (the Pad tab's editor enforces this).
