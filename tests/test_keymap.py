"""Pure tests for the key-combo → evdev keycode mapping — no evdev, no hardware."""

from wacom_panel.daemon import keymap

# ---- resolve: one token -> evdev ecode name --------------------------------------------------


def test_resolve_named_keys():
    assert keymap.resolve("Down") == "KEY_DOWN"
    assert keymap.resolve("Prior") == "KEY_PAGEUP"
    assert keymap.resolve("Next") == "KEY_PAGEDOWN"
    assert keymap.resolve("F5") == "KEY_F5"


def test_resolve_modifiers_use_left_variant():
    assert keymap.resolve("ctrl") == "KEY_LEFTCTRL"
    assert keymap.resolve("control") == "KEY_LEFTCTRL"
    assert keymap.resolve("shift") == "KEY_LEFTSHIFT"
    assert keymap.resolve("super") == "KEY_LEFTMETA"


def test_resolve_strips_press_release_prefix():
    assert keymap.resolve("+ctrl") == "KEY_LEFTCTRL"
    assert keymap.resolve("-shift") == "KEY_LEFTSHIFT"


def test_resolve_letters_and_digits():
    assert keymap.resolve("z") == "KEY_Z"
    assert keymap.resolve("A") == "KEY_A"
    assert keymap.resolve("7") == "KEY_7"


def test_resolve_unknown_is_none():
    assert keymap.resolve("Nonsense") is None
    assert keymap.resolve("") is None


# ---- to_chord: combo -> (presses, reverse releases) ------------------------------------------


def test_chord_single_key_press_then_release():
    assert keymap.to_chord("Next") == (["KEY_PAGEDOWN"], ["KEY_PAGEDOWN"])


def test_chord_modifier_combo_releases_in_reverse():
    # "ctrl z" is an Undo chord: Ctrl down, z down, then z up, Ctrl up.
    presses, releases = keymap.to_chord("ctrl z")
    assert presses == ["KEY_LEFTCTRL", "KEY_Z"]
    assert releases == ["KEY_Z", "KEY_LEFTCTRL"]


def test_chord_skips_unknown_tokens():
    presses, releases = keymap.to_chord("ctrl bogus z")
    assert presses == ["KEY_LEFTCTRL", "KEY_Z"]
    assert releases == ["KEY_Z", "KEY_LEFTCTRL"]


def test_chord_all_unknown_is_empty():
    assert keymap.to_chord("bogus") == ([], [])


# ---- supported names: the uinput capability set ----------------------------------------------


def test_supported_names_cover_table_letters_and_digits():
    names = keymap.supported_evdev_names()
    assert "KEY_PAGEDOWN" in names      # from the table
    assert "KEY_Z" in names             # letters
    assert "KEY_0" in names             # digits
    # Every name resolve() can emit must be advertisable.
    for token in ("Down", "ctrl", "F12", "q", "3"):
        assert keymap.resolve(token) in names
