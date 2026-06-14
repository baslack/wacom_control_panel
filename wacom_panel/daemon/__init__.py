"""Userspace touch-ring daemon.

The touch ring is reported by the kernel as an absolute axis (``ABS_WHEEL``). ``xsetwacom``
can only bind it to keystrokes — it cannot emit ``REL_WHEEL`` (relative scroll), which is what
applications actually want. This subpackage reads the ring's raw events via ``evdev`` and
injects synthetic scroll via ``uinput``, below libinput, so it works on X11 *and* Wayland.

Layering: ``daemon`` depends on ``core`` (pure data only) and may import ``evdev``; ``core``
and ``backend`` never import ``daemon``. The translation math lives in
:mod:`wacom_panel.daemon.ring_translator` (pure, no ``evdev``) so it is unit-testable without
hardware; :mod:`wacom_panel.daemon.ring_daemon` is the thin evdev/uinput I/O loop.
"""
