"""Pure tests for the touch-ring translator — no evdev, no hardware."""

from wacom_panel.core.profile import ButtonAction, RingMode
from wacom_panel.daemon.ring_translator import Emit, RingTranslator

# ring_max=23 -> 24 values -> step = round(24/24) = 1, i.e. one wheel tick per ring position.


def _wheels(emits):
    return [e.value for e in emits if e.kind == "wheel"]


def test_first_touch_is_baseline_only():
    t = RingTranslator(ring_max=23)
    assert t.on_value(5) == []  # baseline, nothing emitted


def test_forward_default_scrolls_down():
    t = RingTranslator(ring_max=23)
    t.on_value(5)
    # +1 position clockwise -> default cw action is scroll down -> REL_WHEEL -1
    assert t.on_value(6) == [Emit("wheel", -1)]


def test_backward_default_scrolls_up():
    t = RingTranslator(ring_max=23)
    t.on_value(5)
    # -2 positions -> ccw -> scroll up -> two REL_WHEEL +1
    assert _wheels(t.on_value(3)) == [1, 1]


def test_finger_lift_resets_baseline():
    t = RingTranslator(ring_max=23)
    t.on_value(5)
    t.on_value(8)
    assert t.on_value(0) == []      # lift
    assert t.on_value(20) == []     # next touch is a fresh baseline, no giant jump
    assert _wheels(t.on_value(21)) == [-1]


def test_wraparound_takes_shortest_path():
    t = RingTranslator(ring_max=23)
    t.on_value(23)
    # 23 -> 1 across the seam is +2 (clockwise), not -22
    assert _wheels(t.on_value(1)) == [-1, -1]


def test_invert_flips_direction():
    t = RingTranslator(ring_max=23, invert=True)
    t.on_value(5)
    # +1 position, inverted -> ccw -> scroll up
    assert t.on_value(6) == [Emit("wheel", 1)]


def test_per_mode_action_lookup():
    modes = [RingMode(),  # mode 0: default scroll
             RingMode(cw=ButtonAction("key", "Page_Down"),
                      ccw=ButtonAction("key", "Page_Up"))]
    t = RingTranslator(modes, ring_max=23)
    t.on_value(5, 1)
    assert t.on_value(6, 1) == [Emit("key", "Page_Down")]
    # Out-of-range mode index falls back to default scroll.
    t.reset()
    t.on_value(5, 9)
    assert t.on_value(6, 9) == [Emit("wheel", -1)]


def test_sub_tick_motion_accumulates():
    # With a coarser ring (more positions per tick) small steps accumulate to whole ticks.
    t = RingTranslator(ring_max=47)  # step = round(48/24) = 2
    t.on_value(10)
    assert t.on_value(11) == []        # +1 < step, nothing yet
    assert t.on_value(12) == [Emit("wheel", -1)]  # +1 more reaches a full tick


def test_set_modes_swaps_table():
    t = RingTranslator([], ring_max=23)
    t.set_modes([RingMode(cw=ButtonAction("scroll", "up"))])
    t.on_value(5)
    # cw now scrolls up
    assert t.on_value(6) == [Emit("wheel", 1)]
