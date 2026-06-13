"""Pure tests for the touch-ring translator + scroll smoother — no evdev, no hardware."""

from wacom_panel.core.profile import ButtonAction, RingMode
from wacom_panel.daemon.ring_translator import Emit, RingTranslator, ScrollSmoother

# ring_max=23 -> 24 values -> hi_per_pos = 120*24/24 = 120, i.e. one ring position == one notch,
# which keeps the high-res numbers easy to read in these assertions.


def _hi(emits):
    return [e.value for e in emits if e.kind == "wheel_hi"]


# ---- RingTranslator: positions -> high-res scroll targets / key ticks --------------------


def test_first_touch_is_baseline_only():
    t = RingTranslator(ring_max=23)
    assert t.on_value(5) == []  # baseline, nothing emitted


def test_forward_default_scrolls_down():
    t = RingTranslator(ring_max=23)
    t.on_value(5)
    assert t.on_value(6) == [Emit("wheel_hi", -120)]  # +1 cw -> default scroll down


def test_backward_default_scrolls_up():
    t = RingTranslator(ring_max=23)
    t.on_value(5)
    assert t.on_value(3) == [Emit("wheel_hi", 240)]  # -2 ccw -> scroll up, two notches' worth


def test_finger_lift_resets_baseline():
    t = RingTranslator(ring_max=23)
    t.on_value(5)
    t.on_value(8)
    assert t.on_value(0) == []      # lift
    assert t.on_value(20) == []     # next touch is a fresh baseline, no giant jump
    assert _hi(t.on_value(21)) == [-120]


def test_wraparound_takes_shortest_path():
    t = RingTranslator(ring_max=23)
    t.on_value(23)
    assert t.on_value(1) == [Emit("wheel_hi", -240)]  # 23 -> 1 is +2 (cw), not -22


def test_invert_flips_direction():
    t = RingTranslator(ring_max=23, invert=True)
    t.on_value(5)
    assert t.on_value(6) == [Emit("wheel_hi", 120)]  # +1 inverted -> ccw -> scroll up


def test_per_mode_key_action_is_discrete():
    modes = [RingMode(),  # mode 0: default scroll
             RingMode(cw=ButtonAction("key", "Page_Down"),
                      ccw=ButtonAction("key", "Page_Up"))]
    t = RingTranslator(modes, ring_max=23)
    t.on_value(5, 1)
    assert t.on_value(6, 1) == [Emit("key", "Page_Down")]
    # Out-of-range mode index falls back to default scroll.
    t.reset()
    t.on_value(5, 9)
    assert _hi(t.on_value(6, 9)) == [-120]


def test_set_modes_swaps_table():
    t = RingTranslator([], ring_max=23)
    t.set_modes([RingMode(cw=ButtonAction("scroll", "up"))])
    t.on_value(5)
    assert _hi(t.on_value(6)) == [120]  # cw now scrolls up


# ---- ScrollSmoother: spread choppy jumps, conserve total, derive coarse ticks -------------


def _drain(s):
    hi_total = 0
    coarse = []
    for _ in range(500):
        if not s.busy():
            break
        for e in s.tick():
            if e.kind == "wheel_hi":
                hi_total += e.value
            else:
                coarse.append(e.value)
    return hi_total, coarse


def test_smoother_idle_emits_nothing():
    s = ScrollSmoother()
    assert not s.busy()
    assert s.tick() == []


def test_smoother_conserves_total_and_emits_coarse_notches():
    s = ScrollSmoother()
    s.add(240)
    hi_total, coarse = _drain(s)
    assert hi_total == 240        # every high-res unit added is eventually injected
    assert coarse == [1, 1]       # 240 / 120 = two coarse notches, upward


def test_smoother_preserves_negative_direction():
    s = ScrollSmoother()
    s.add(-120)
    hi_total, coarse = _drain(s)
    assert hi_total == -120
    assert coarse == [-1]


def test_smoother_pays_out_gradually_not_all_at_once():
    s = ScrollSmoother()
    s.add(240)
    first = _hi(s.tick())[0]
    assert 0 < first < 240  # first slice is only a fraction of the queued jump


def test_smoother_drains_small_remainder_in_one_tick():
    s = ScrollSmoother()
    s.add(1)
    assert s.busy()
    assert _hi(s.tick()) == [1]
    assert not s.busy()
