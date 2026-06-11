"""Tests for spatial pad layout loading + matching."""

from wacom_panel.core.pad_layout import load_layout


def test_intuos_pro_m_layout_matches_by_name():
    layout = load_layout("Wacom Intuos Pro M Pad pad", [1, 2, 3, 8, 9, 10, 11, 12, 13])
    assert layout.matched is True
    assert layout.display_name == "Wacom Intuos Pro M"
    assert [k.button for k in layout.top_keys] == [1, 2, 3, 8]
    assert [k.button for k in layout.bottom_keys] == [9, 10, 11, 12]
    assert layout.ring is not None
    assert layout.ring.center == 13
    assert layout.ring.modes == 4
    assert layout.ring.cw == "AbsWheelUp"
    assert layout.ring.ccw == "AbsWheelDown"
    assert 13 in layout.all_buttons


def test_unknown_tablet_falls_back_to_generic():
    layout = load_layout("Some Other Tablet", [1, 2, 3])
    assert layout.matched is False
    assert [k.button for k in layout.top_keys] == [1, 2, 3]
    assert layout.bottom_keys == []
    assert layout.ring is None


def test_detected_buttons_filter_layout_keys():
    # If the device reports only a subset, absent keys are dropped from the layout.
    layout = load_layout("Wacom Intuos Pro M", [1, 2, 3, 8])
    assert [k.button for k in layout.top_keys] == [1, 2, 3, 8]
    assert layout.bottom_keys == []  # 9-12 not detected
    assert layout.ring is not None
    assert layout.ring.center is None  # 13 not detected


def test_empty_detected_keeps_all_layout_keys():
    # No detection info (empty list) means trust the layout file as-is.
    layout = load_layout("Wacom Intuos Pro M", [])
    assert len(layout.top_keys) == 4
    assert len(layout.bottom_keys) == 4
    assert layout.ring.center == 13
