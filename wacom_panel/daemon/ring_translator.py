"""Pure translation of touch-ring motion into scroll / key events.

No ``evdev``, no ``uinput``, no I/O — just the math, so it is unit-testable without hardware.

The ring reports an absolute position (``ABS_WHEEL``) that climbs / falls as the finger moves
around it, and ``0`` when the finger lifts. We turn successive positions into relative wheel
*ticks*, honouring the per-LED-mode action table and damping the encoder's fine resolution down
to a wheel-like feel.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.profile import ButtonAction, RingMode

# How many scroll ticks make up one full revolution of the ring, regardless of the encoder's
# raw resolution (~72 steps/rev). Roughly matches a normal mouse wheel so the ring doesn't feel
# hair-trigger. The daemon reads the true encoder maximum from the device and damps to this.
_TICKS_PER_REV = 24


@dataclass(frozen=True)
class Emit:
    """One synthetic event for the daemon to inject.

    ``kind`` ``"wheel"`` → ``value`` is a ``REL_WHEEL`` delta (``+1`` up / ``-1`` down).
    ``kind`` ``"key"``   → ``value`` is an xsetwacom-style key combo (Phase 2 in the daemon).
    """

    kind: str
    value: int | str


def _action_emits(action: ButtonAction, ticks: int) -> list[Emit]:
    if ticks <= 0:
        return []
    if action.kind == "scroll":
        step = 1 if action.value == "up" else -1
        return [Emit("wheel", step)] * ticks
    if action.kind == "key" and action.value.strip():
        return [Emit("key", action.value.strip())] * ticks
    return []


class RingTranslator:
    """Stateful absolute-position → relative-tick converter for one ring.

    Feed it raw ``ABS_WHEEL`` values via :meth:`on_value`; it returns the events to inject. It
    tracks the finger-down baseline (the first sample after a touch emits nothing), resets on
    finger-lift (value ``0``), takes the shortest path around the wrap point, and accumulates
    sub-tick motion so a slow drag still scrolls smoothly.
    """

    def __init__(
        self,
        modes: list[RingMode] | None = None,
        *,
        ring_max: int = 71,
        invert: bool = False,
    ) -> None:
        self._modes = list(modes or [])
        self._range = ring_max + 1  # touched values span 1..ring_max; 0 means released
        self._invert = invert
        self._step = max(1, round(self._range / _TICKS_PER_REV))
        self._last: int | None = None
        self._accum = 0

    def reset(self) -> None:
        """Forget the current touch (call on finger-lift or device re-acquire)."""
        self._last = None
        self._accum = 0

    def set_modes(self, modes: list[RingMode] | None) -> None:
        """Swap the per-mode action table (e.g. after a SIGHUP profile reload)."""
        self._modes = list(modes or [])

    def _mode(self, index: int) -> RingMode:
        if 0 <= index < len(self._modes):
            return self._modes[index]
        return RingMode()  # default: scroll down (cw) / up (ccw)

    def on_value(self, value: int, mode_index: int = 0) -> list[Emit]:
        """Translate one raw ring sample for the active LED mode into events to inject."""
        if value <= 0:  # finger lifted
            self.reset()
            return []
        if self._last is None:  # first sample of a touch is the baseline
            self._last = value
            return []

        delta = value - self._last
        self._last = value
        # Shortest path around the ring (e.g. 71 -> 1 is +2, not -70).
        half = self._range // 2
        if delta > half:
            delta -= self._range
        elif delta < -half:
            delta += self._range
        if delta == 0:
            return []
        if self._invert:
            delta = -delta

        # Damp the fine encoder resolution to wheel-like ticks, carrying the remainder.
        self._accum += delta
        ticks = int(self._accum / self._step)
        if ticks == 0:
            return []
        self._accum -= ticks * self._step

        mode = self._mode(mode_index)
        action = mode.cw if ticks > 0 else mode.ccw
        return _action_emits(action, abs(ticks))
