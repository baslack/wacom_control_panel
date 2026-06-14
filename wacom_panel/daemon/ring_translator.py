"""Pure translation of touch-ring motion into scroll / key events.

No ``evdev``, no ``uinput``, no I/O — just the math, so it is unit-testable without hardware.

The ring reports an absolute position (``ABS_WHEEL``) that climbs / falls as the finger moves
around it, and ``0`` when the finger lifts. We turn successive positions into **high-resolution**
scroll deltas (``REL_WHEEL_HI_RES``, 120 units = one notch).

The ring's encoder only samples at ~33 Hz, so a fast finger produces a few large jumps per
second — which reads as start/stop stutter. :class:`ScrollSmoother` fixes that: the daemon feeds
each jump in and *pays it out* in small increments across the gap until the next sample, so the
injected motion is smooth (~150 Hz) regardless of the choppy input rate. The smoother also emits
the legacy coarse ``REL_WHEEL`` tick (one per 120 high-res units) for apps that ignore high-res.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.profile import ButtonAction, RingMode

# How many scroll notches make up one full revolution of the ring, regardless of the encoder's
# raw resolution (~72 steps/rev). Roughly a normal mouse wheel so the ring isn't hair-trigger.
_NOTCHES_PER_REV = 24
# Linux high-res wheel convention: 120 units == one classic wheel notch.
_HI_RES_PER_NOTCH = 120


@dataclass(frozen=True)
class Emit:
    """One synthetic event for the daemon to inject.

    ``kind`` ``"wheel"``    → ``value`` is a classic ``REL_WHEEL`` delta (``+1`` up / ``-1`` down).
    ``kind`` ``"wheel_hi"`` → ``value`` is a ``REL_WHEEL_HI_RES`` delta (120 == one notch).
    ``kind`` ``"key"``      → ``value`` is an xsetwacom-style key combo the daemon taps via uinput
                              (mapped to evdev keycodes by :mod:`wacom_panel.daemon.keymap`).
    """

    kind: str
    value: int | str


class RingTranslator:
    """Stateful absolute-position → scroll/key converter for one ring.

    Feed it raw ``ABS_WHEEL`` values via :meth:`on_value`; it returns the events to inject. It
    tracks the finger-down baseline (the first sample after a touch emits nothing), resets on
    finger-lift (value ``0``), takes the shortest path around the wrap point, and — for scroll
    actions — emits smooth high-res motion with a coarse tick carried on the side.
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
        # Fine scroll per ring position, and positions per discrete key tick.
        self._hi_per_pos = _HI_RES_PER_NOTCH * _NOTCHES_PER_REV / self._range
        self._key_step = max(1, round(self._range / _NOTCHES_PER_REV))
        self._last: int | None = None
        self._key_accum = 0   # ring positions not yet promoted to a key press

    def reset(self) -> None:
        """Forget the current touch (call on finger-lift or device re-acquire)."""
        self._last = None
        self._key_accum = 0

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

        action = self._mode(mode_index).cw if delta > 0 else self._mode(mode_index).ccw
        return self._emit_action(action, abs(delta))

    def _emit_action(self, action: ButtonAction, positions: int) -> list[Emit]:
        if action.kind == "scroll":
            sign = 1 if action.value == "up" else -1
            return self._scroll(sign * positions)
        if action.kind == "key" and action.value.strip():
            self._key_accum += positions
            ticks = self._key_accum // self._key_step
            if ticks <= 0:
                return []
            self._key_accum -= ticks * self._key_step
            return [Emit("key", action.value.strip())] * ticks
        return []

    def _scroll(self, signed_positions: int) -> list[Emit]:
        # One high-res target per sample; the daemon's ScrollSmoother spreads it over time and
        # derives the coarse REL_WHEEL ticks from the smoothed stream.
        return [Emit("wheel_hi", round(signed_positions * self._hi_per_pos))]


class ScrollSmoother:
    """Spreads choppy ~33 Hz ring jumps into a smooth high-res stream.

    The daemon :meth:`add`s each sample's high-res target, then calls :meth:`tick` on a fast
    timer; each tick pays out a fraction of what's still pending (an ease-out), emitting a
    ``wheel_hi`` increment plus a coarse ``wheel`` tick whenever 120 high-res units accrue.
    Integer-conserving: the sum of emitted high-res equals what was added (bar a <1-unit tail).
    """

    def __init__(self, fraction: float = 0.35) -> None:
        self._fraction = fraction
        self._pending = 0.0   # high-res units queued but not yet injected
        self._coarse = 0      # emitted high-res not yet promoted to a REL_WHEEL notch

    def add(self, hi_res: int) -> None:
        self._pending += hi_res

    def busy(self) -> bool:
        """True while there is still movement to pay out (drive the fast tick timer)."""
        return abs(self._pending) >= 1.0

    def reset(self) -> None:
        self._pending = 0.0
        self._coarse = 0

    def tick(self) -> list[Emit]:
        if abs(self._pending) < 1.0:
            return []
        chunk = self._pending * self._fraction
        if abs(chunk) < 1.0:  # always drain at least one unit so motion finishes promptly
            chunk = math.copysign(1.0, self._pending)
        chunk = int(chunk)  # toward zero; magnitude >= 1
        self._pending -= chunk

        emits: list[Emit] = [Emit("wheel_hi", chunk)]
        self._coarse += chunk
        while self._coarse >= _HI_RES_PER_NOTCH:
            emits.append(Emit("wheel", 1))
            self._coarse -= _HI_RES_PER_NOTCH
        while self._coarse <= -_HI_RES_PER_NOTCH:
            emits.append(Emit("wheel", -1))
            self._coarse += _HI_RES_PER_NOTCH
        return emits
