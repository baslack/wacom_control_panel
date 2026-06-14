"""Tests for the libwacom *.tablet database reader — pure, fixture-driven."""

from pathlib import Path

from wacom_panel.core.libwacom_db import TabletSpec, find_tablet_spec

# A ring tablet (Intuos Pro M) and a small ring-less one (Intuos S), mirroring the real files.
_PRO_M = """\
[Device]
Name=Wacom Intuos Pro M
ModelName=PTH-651
DeviceMatch=usb:056a:0315
Layout=intuos-pro-m.svg

[Features]
Stylus=true
Touch=true
Ring=true
StatusLEDs=Ring

[Buttons]
Left=A;B;C;D;E;F;G;H;I
Ring=A
RingNumModes=4
"""

_INTUOS_S = """\
[Device]
Name=Wacom Intuos S
ModelName=CTL-4100
DeviceMatch=usb:056a:0374

[Features]
Stylus=true

[Buttons]
Top=A;B;C;D
EvdevCodes=BTN_0;BTN_1;BTN_2;BTN_3
"""


def _db(tmp_path: Path) -> Path:
    (tmp_path / "intuos-pro-m.tablet").write_text(_PRO_M)
    (tmp_path / "intuos-s-p3.tablet").write_text(_INTUOS_S)
    return tmp_path


def test_match_by_usb_id_ring_tablet(tmp_path):
    spec = find_tablet_spec(0x056A, 0x0315, directory=_db(tmp_path))
    assert spec == TabletSpec(
        name="Wacom Intuos Pro M", model="PTH-651",
        num_buttons=9, has_ring=True, ring_modes=4, evdev_codes=[],
    )


def test_match_by_usb_id_ringless_tablet(tmp_path):
    spec = find_tablet_spec(0x056A, 0x0374, directory=_db(tmp_path))
    assert spec.name == "Wacom Intuos S"
    assert spec.num_buttons == 4
    assert spec.has_ring is False
    assert spec.ring_modes == 1
    assert spec.evdev_codes == ["BTN_0", "BTN_1", "BTN_2", "BTN_3"]


def test_match_by_name_when_no_usb(tmp_path):
    # The xsetwacom device name carries a tool suffix; substring match both ways.
    spec = find_tablet_spec(name="Wacom Intuos Pro M Pad pad", directory=_db(tmp_path))
    assert spec is not None and spec.model == "PTH-651"


def test_no_match_returns_none(tmp_path):
    assert find_tablet_spec(0x1234, 0x5678, name="Nope", directory=_db(tmp_path)) is None


def test_missing_directory_returns_none(tmp_path):
    assert find_tablet_spec(0x056A, 0x0315, directory=tmp_path / "absent") is None


def test_semicolons_in_button_list_not_treated_as_comment(tmp_path):
    # configparser must keep "A;B;C;D" intact (inline ';' comments are off).
    spec = find_tablet_spec(0x056A, 0x0315, directory=_db(tmp_path))
    assert spec.num_buttons == 9
