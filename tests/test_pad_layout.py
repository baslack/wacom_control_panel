"""Tests for spatial pad layout loading + matching."""

from wacom_panel.core.pad_layout import load_layout


def test_intuos_pro_m_layout_matches_by_name():
    # Button numbers verified empirically on PTH-660 (see pad-button-facts memory):
    # top 2,3,8,9; centre 1; bottom 10-13; clockwise = AbsWheelDown.
    layout = load_layout("Wacom Intuos Pro M Pad pad", [1, 2, 3, 8, 9, 10, 11, 12, 13])
    assert layout.matched is True
    assert layout.display_name == "Wacom Intuos Pro M"
    assert [k.button for k in layout.top_keys] == [2, 3, 8, 9]
    assert [k.button for k in layout.bottom_keys] == [10, 11, 12, 13]
    assert layout.ring is not None
    assert layout.ring.center == 1
    assert layout.ring.modes == 4
    assert layout.ring.cw == "AbsWheelDown"
    assert layout.ring.ccw == "AbsWheelUp"
    assert 1 in layout.all_buttons


def test_intuos_pro_m_has_evdev_button_map():
    # Verified on the grabbed PTH-660: BTN_0 = centre/mode (1), BTN_1.. = express keys.
    layout = load_layout("Wacom Intuos Pro M Pad pad", [])
    assert layout.evdev_buttons["BTN_0"] == 1   # centre / mode switch
    assert layout.evdev_buttons["BTN_1"] == 2   # top-left express key
    assert layout.evdev_buttons["BTN_8"] == 13  # bottom-most express key


def test_generic_layout_has_no_evdev_map():
    layout = load_layout("Some Other Tablet", [1, 2, 3])
    assert layout.evdev_buttons == {}


def test_unknown_tablet_falls_back_to_generic():
    layout = load_layout("Some Other Tablet", [1, 2, 3])
    assert layout.matched is False
    assert [k.button for k in layout.top_keys] == [1, 2, 3]
    assert layout.bottom_keys == []
    assert layout.ring is None


def test_detected_buttons_filter_layout_keys():
    # If the device reports only a subset, absent keys are dropped from the layout.
    layout = load_layout("Wacom Intuos Pro M", [1, 2, 3, 8, 9])  # top keys + centre only
    assert [k.button for k in layout.top_keys] == [2, 3, 8, 9]
    assert layout.bottom_keys == []  # 10-13 not detected
    assert layout.ring is not None
    assert layout.ring.center == 1  # centre detected


def test_empty_detected_keeps_all_layout_keys():
    # No detection info (empty list) means trust the layout file as-is.
    layout = load_layout("Wacom Intuos Pro M", [])
    assert len(layout.top_keys) == 4
    assert len(layout.bottom_keys) == 4
    assert layout.ring.center == 1
