"""Tests for the xinput raw-event parser — fed real captured `xinput test-xi2 --root` text."""

from wacom_panel.core.pad_capture import (
    Xi2ButtonParser,
    reset_buttons_command,
    xinput_capture_command,
)

# A verbatim slice of `xinput test-xi2 --root` from the PTH-660 (pad device id 19): three express
# keys pressed (buttons 2, 3, 8), plus some motion noise that must be ignored.
_SAMPLE = """\
EVENT type 17 (RawMotion)
    device: 2 (19)
    detail: 0
    valuators:
EVENT type 15 (RawButtonPress)
    device: 2 (19)
    time:   4887042
    detail: 2
    flags:
    valuators:
EVENT type 6 (Motion)
    device: 2 (19)
    detail: 0
EVENT type 15 (RawButtonPress)
    device: 2 (19)
    time:   4887462
    detail: 3
    flags:
EVENT type 15 (RawButtonPress)
    device: 2 (19)
    time:   4887897
    detail: 8
    flags:
"""


def _run(parser: Xi2ButtonParser, text: str) -> list[int]:
    return [b for line in text.splitlines() if (b := parser.feed(line)) is not None]


def test_parses_button_numbers_in_order():
    assert _run(Xi2ButtonParser(19), _SAMPLE) == [2, 3, 8]


def test_ignores_other_devices():
    # Same stream, but the parser is watching a different device id → nothing matches.
    assert _run(Xi2ButtonParser(99), _SAMPLE) == []


def test_motion_and_release_lines_do_not_emit():
    parser = Xi2ButtonParser(19)
    assert parser.feed("EVENT type 17 (RawMotion)") is None
    assert parser.feed("    device: 2 (19)") is None
    assert parser.feed("    detail: 5") is None  # detail under a non-press event → ignored


def test_detail_without_matching_device_is_skipped():
    parser = Xi2ButtonParser(19)
    parser.feed("EVENT type 15 (RawButtonPress)")
    parser.feed("    device: 2 (77)")  # wrong source device
    assert parser.feed("    detail: 4") is None


def test_capture_command_is_root_raw():
    assert xinput_capture_command() == ["xinput", "test-xi2", "--root"]


def test_reset_buttons_command_emits_button_actions():
    cmds = reset_buttons_command("Wacom Foo Pad pad", [2, 3])
    assert cmds == [
        ["xsetwacom", "--set", "Wacom Foo Pad pad", "Button", "2", "button", "2"],
        ["xsetwacom", "--set", "Wacom Foo Pad pad", "Button", "3", "button", "3"],
    ]
