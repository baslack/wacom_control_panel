"""Read the system's libwacom ``*.tablet`` database — pure, no libwacom bindings needed.

libwacom ships a tablet description for every supported device as a plain INI file under
``/usr/share/libwacom/`` (≈400 of them). We don't need the C library or its GObject bindings to
*read* one — ``configparser`` is enough. This module looks up the description for a connected
tablet and extracts just what the setup wizard needs to scaffold its UI: the friendly name, how
many pad buttons it has, and whether it has a touch ring (and how many LED modes).

It deliberately does **not** try to know which xsetwacom button number each physical key is —
libwacom's button *letters* famously don't match xsetwacom's numbering (see the hardware notes).
That mapping is what the wizard captures interactively; libwacom only tells us the *shape*.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

# The standard libwacom data directory. Overridable in tests / on unusual distros.
LIBWACOM_DIR = Path("/usr/share/libwacom")

# A ``DeviceMatch`` entry looks like ``usb:056a:0315`` (possibly several, ``;``-separated, plus
# bluetooth:/generic entries we ignore).
_USB_MATCH_RE = re.compile(r"usb:([0-9a-fA-F]{4}):([0-9a-fA-F]{4})")


@dataclass(frozen=True)
class TabletSpec:
    """The shape of a tablet's pad, scaffolded from its libwacom description."""

    name: str            # e.g. "Wacom Intuos Pro M"
    model: str           # e.g. "PTH-651" (may be empty)
    num_buttons: int     # number of physical ExpressKeys
    has_ring: bool
    ring_modes: int      # LED/ring modes (1 if unknown / no multi-mode ring)
    # evdev BTN_* names libwacom lists for the pad, in button-letter order, when present. A hint
    # only — the wizard still captures the live codes; empty for most files.
    evdev_codes: list[str] = field(default_factory=list)


def _read_tablet_file(path: Path) -> configparser.ConfigParser | None:
    # optionxform=str keeps key case (Name, DeviceMatch, Ring…); inline ';' comments are off by
    # default in Python 3 so "Left=A;B;C;D" is preserved intact.
    cfg = configparser.ConfigParser(strict=False)
    cfg.optionxform = str  # type: ignore[assignment, method-assign]
    try:
        if not cfg.read(path, encoding="utf-8"):
            return None
    except (OSError, configparser.Error):
        return None
    return cfg


def _letters(value: str) -> list[str]:
    """Split a ``A;B;C`` button list into non-empty tokens."""
    return [tok for tok in (value or "").split(";") if tok.strip()]


def _spec_from_config(cfg: configparser.ConfigParser) -> TabletSpec:
    device = cfg["Device"] if cfg.has_section("Device") else {}
    features = cfg["Features"] if cfg.has_section("Features") else {}
    buttons = cfg["Buttons"] if cfg.has_section("Buttons") else {}

    # Total ExpressKeys = the union of every physical side group (a key appears in exactly one).
    letters: set[str] = set()
    for side in ("Top", "Bottom", "Left", "Right"):
        letters.update(_letters(buttons.get(side, "")))

    has_ring = bool(features.get("Ring")) or "Ring" in buttons or "Ring2" in buttons
    try:
        ring_modes = int(buttons.get("RingNumModes", "1"))
    except ValueError:
        ring_modes = 1

    return TabletSpec(
        name=device.get("Name", "").strip(),
        model=device.get("ModelName", "").strip(),
        num_buttons=len(letters),
        has_ring=has_ring,
        ring_modes=max(1, ring_modes),
        evdev_codes=_letters(buttons.get("EvdevCodes", "")),
    )


def _usb_ids(cfg: configparser.ConfigParser) -> set[tuple[int, int]]:
    if not cfg.has_section("Device"):
        return set()
    match = cfg["Device"].get("DeviceMatch", "")
    return {
        (int(v, 16), int(p, 16)) for v, p in _USB_MATCH_RE.findall(match)
    }


def find_tablet_spec(
    vendor_id: int | None = None,
    product_id: int | None = None,
    name: str = "",
    *,
    directory: Path | None = None,
) -> TabletSpec | None:
    """Best libwacom description for a tablet, or ``None`` if the database has no match.

    Matches by USB ``vendor:product`` id first (exact, reliable), then falls back to a
    case-insensitive match of ``name`` against the file's ``Name`` (either way around, since the
    xsetwacom device name carries a tool suffix like " Pad pad").
    """
    directory = directory or LIBWACOM_DIR
    if not directory.is_dir():
        return None

    want_usb = vendor_id is not None and product_id is not None
    name_l = name.strip().lower()
    name_fallback: TabletSpec | None = None

    for path in sorted(directory.glob("*.tablet")):
        cfg = _read_tablet_file(path)
        if cfg is None:
            continue
        if want_usb and (vendor_id, product_id) in _usb_ids(cfg):
            return _spec_from_config(cfg)
        if name_fallback is None and name_l:
            file_name = cfg["Device"].get("Name", "").strip().lower() if cfg.has_section(
                "Device"
            ) else ""
            if file_name and (file_name in name_l or name_l in file_name):
                spec = _spec_from_config(cfg)
                if not want_usb:
                    return spec
                name_fallback = spec  # keep looking for a USB hit, but remember this

    return name_fallback
