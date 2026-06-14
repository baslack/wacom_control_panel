"""Translate xsetwacom-style key strings into evdev key events — pure, no ``evdev`` import.

The ring daemon's per-mode ``"key"`` actions (and, later, the express keys) store their binding
as an xsetwacom-style combo in ``ButtonAction.value`` — the same grammar the GUI writes, e.g.
``"Down"``, ``"Prior"``, ``"ctrl z"``, ``"ctrl shift z"`` (see ``ui/qml/ActionEditor.qml``). To
inject those through ``uinput`` the daemon needs the corresponding Linux input keycodes.

This module does the mapping *by evdev ecode name* (``"KEY_DOWN"``) rather than the integer code,
so it imports no ``evdev`` and unit-tests without the ``daemon`` extra — exactly like
:mod:`wacom_panel.daemon.ring_translator`. The daemon resolves the names to ints at injection
time via ``evdev.ecodes.ecodes[name]``.
"""

from __future__ import annotations

import string

# xsetwacom / X-keysym token -> evdev ecode name. Single letters (a-z) and digits (0-9) are
# handled programmatically in resolve(); this table covers the named keys the app can produce.
KEYSYM_TO_EVDEV: dict[str, str] = {
    # arrows / navigation
    "Up": "KEY_UP",
    "Down": "KEY_DOWN",
    "Left": "KEY_LEFT",
    "Right": "KEY_RIGHT",
    "Prior": "KEY_PAGEUP",
    "Page_Up": "KEY_PAGEUP",
    "Next": "KEY_PAGEDOWN",
    "Page_Down": "KEY_PAGEDOWN",
    "Home": "KEY_HOME",
    "End": "KEY_END",
    # modifiers (left-hand variants)
    "ctrl": "KEY_LEFTCTRL",
    "control": "KEY_LEFTCTRL",
    "shift": "KEY_LEFTSHIFT",
    "alt": "KEY_LEFTALT",
    "super": "KEY_LEFTMETA",
    "meta": "KEY_LEFTMETA",
    # whitespace / editing
    "Return": "KEY_ENTER",
    "Enter": "KEY_ENTER",
    "space": "KEY_SPACE",
    "Escape": "KEY_ESC",
    "Esc": "KEY_ESC",
    "Tab": "KEY_TAB",
    "BackSpace": "KEY_BACKSPACE",
    "Delete": "KEY_DELETE",
    # symbols commonly paired with Ctrl (e.g. zoom)
    "plus": "KEY_EQUAL",
    "equal": "KEY_EQUAL",
    "minus": "KEY_MINUS",
}
# function keys F1-F12
KEYSYM_TO_EVDEV.update({f"F{n}": f"KEY_F{n}" for n in range(1, 13)})

# xsetwacom mouse-button number -> evdev BTN ecode name, for express keys the daemon injects
# while it owns the pad. Scroll buttons (4/5) are *not* here — they become REL_WHEEL ticks, not
# key events (see BUTTON_TO_SCROLL); xsetwacom's 4/5/6/7 are wheel up/down/left/right.
BUTTON_TO_EVDEV: dict[int, str] = {
    1: "BTN_LEFT",
    2: "BTN_MIDDLE",
    3: "BTN_RIGHT",
    8: "BTN_SIDE",    # "Back"
    9: "BTN_EXTRA",   # "Forward"
}
# Mouse "buttons" that are really wheel ticks: number -> REL_WHEEL delta (one notch).
BUTTON_TO_SCROLL: dict[int, int] = {4: 1, 5: -1}


def resolve(token: str) -> str | None:
    """Map one combo token (e.g. ``"+ctrl"``, ``"z"``, ``"Prior"``) to an evdev ecode name.

    Strips a leading ``+``/``-`` (press/release) prefix, then matches the named table, single
    letters (``a``-``z`` → ``KEY_<UPPER>``) and digits (``0``-``9`` → ``KEY_<n>``). Returns
    ``None`` for anything unknown so a typo is skipped rather than killing the daemon.
    """
    token = token.lstrip("+-")
    if not token:
        return None
    if token in KEYSYM_TO_EVDEV:
        return KEYSYM_TO_EVDEV[token]
    if len(token) == 1:
        if token in string.ascii_letters:
            return f"KEY_{token.upper()}"
        if token in string.digits:
            return f"KEY_{token}"
    return None


def to_chord(combo: str) -> tuple[list[str], list[str]]:
    """Expand a key combo into a momentary chord tap.

    Returns ``(presses, releases)`` as ordered evdev ecode names: every resolvable token is
    pressed in order, then released in reverse. So ``"Down"`` → press/release Down, and
    ``"ctrl z"`` → Ctrl↓ z↓ … z↑ Ctrl↑ (an Undo chord). Unknown tokens are skipped.
    """
    presses = [name for tok in combo.split() if (name := resolve(tok)) is not None]
    return presses, list(reversed(presses))


def supported_evdev_names() -> set[str]:
    """Every ecode name :func:`resolve` can emit — used to advertise the uinput key capabilities."""
    names = set(KEYSYM_TO_EVDEV.values())
    names.update(f"KEY_{c}" for c in string.ascii_uppercase)
    names.update(f"KEY_{d}" for d in string.digits)
    return names


def resolve_button(number: int) -> str | None:
    """Map an xsetwacom mouse-button number to an evdev ``BTN_*`` name (``None`` if unmapped)."""
    return BUTTON_TO_EVDEV.get(int(number))


def supported_buttons() -> set[str]:
    """Every mouse ``BTN_*`` name the pad daemon can emit — for the uinput key capabilities."""
    return set(BUTTON_TO_EVDEV.values())
