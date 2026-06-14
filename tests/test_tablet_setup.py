"""Tests for assembling a layout dict from wizard captures."""

from wacom_panel.core.tablet_setup import Capture, build_layout


def test_ring_tablet_full_capture():
    # Mirrors the PTH-660: 4 above-ring, centre, 4 below-ring, all with evdev codes.
    layout = build_layout(
        display_name="Wacom Intuos Pro M",
        model="PTH-660",
        has_ring=True,
        ring_modes=4,
        top=[Capture(2, "BTN_1"), Capture(3, "BTN_2"), Capture(8, "BTN_3"), Capture(9, "BTN_4")],
        bottom=[Capture(10, "BTN_5"), Capture(11, "BTN_6"),
                Capture(12, "BTN_7"), Capture(13, "BTN_8")],
        center=Capture(1, "BTN_0"),
    )
    assert layout["display_name"] == "Wacom Intuos Pro M"
    assert layout["match"] == ["wacom intuos pro m", "pth-660"]
    assert [k["button"] for k in layout["top_keys"]] == [2, 3, 8, 9]
    assert [k["button"] for k in layout["bottom_keys"]] == [10, 11, 12, 13]
    assert [k["label"] for k in layout["top_keys"]] == ["Key 1", "Key 2", "Key 3", "Key 4"]
    assert layout["bottom_keys"][0]["label"] == "Key 5"  # labels continue across the ring
    assert layout["ring"] == {
        "center": 1, "center_label": "Mode", "modes": 4,
        "cw": "AbsWheelDown", "ccw": "AbsWheelUp",
    }
    assert layout["evdev_buttons"]["BTN_0"] == 1
    assert layout["evdev_buttons"]["BTN_8"] == 13


def test_ringless_tablet_no_ring_key():
    layout = build_layout(
        display_name="Wacom Intuos S",
        top=[Capture(2), Capture(3), Capture(8)],
    )
    assert "ring" not in layout
    assert layout["bottom_keys"] == []
    assert layout["match"] == ["wacom intuos s"]  # no model → single match token


def test_no_evdev_codes_omits_evdev_buttons():
    # When the evdev node was unreadable, captures carry no BTN_* → key omitted entirely.
    layout = build_layout(display_name="T", top=[Capture(2), Capture(3)])
    assert "evdev_buttons" not in layout


def test_partial_evdev_codes_only_includes_captured():
    layout = build_layout(
        display_name="T",
        top=[Capture(2, "BTN_1"), Capture(3)],  # second key: no evdev
    )
    assert layout["evdev_buttons"] == {"BTN_1": 2}
