"""Tests for the aspect-correct mapping math."""

import pytest

from wacom_panel.core.mapping import (
    Area,
    fit_rect,
    forced_area,
    place_rect,
    target_area_aspect,
)

# Intuos Pro M native area, a 16:9 output.
TABLET_W, TABLET_H = 44704, 27940
OUT_W, OUT_H = 1920, 1080


def test_fit_rect_width_limited():
    # Target wider than the tablet -> full width, cropped height.
    w, h = fit_rect(TABLET_W, TABLET_H, OUT_W / OUT_H)
    assert w == TABLET_W
    assert h == pytest.approx(TABLET_W * OUT_H / OUT_W, abs=1)


def test_fit_rect_height_limited():
    # Target narrower than the tablet -> full height, cropped width.
    w, h = fit_rect(TABLET_W, TABLET_H, 1.0)  # square target into a 1.6 tablet
    assert h == TABLET_H
    assert w == TABLET_H


def test_forced_area_matches_output_aspect():
    area = forced_area(TABLET_W, TABLET_H, OUT_W, OUT_H)
    assert area.aspect == pytest.approx(OUT_W / OUT_H, rel=1e-3)


def test_forced_area_is_centered_and_full_width_for_16_9():
    area = forced_area(TABLET_W, TABLET_H, OUT_W, OUT_H)
    assert area.x1 == 0 and area.x2 == TABLET_W  # full width kept
    # Symmetric vertical letterbox.
    assert area.y1 == pytest.approx(TABLET_H - area.y2, abs=1)
    assert area.y1 > 0


def test_forced_area_within_bounds():
    area = forced_area(TABLET_W, TABLET_H, OUT_W, OUT_H, zoom=0.5)
    assert 0 <= area.x1 < area.x2 <= TABLET_W
    assert 0 <= area.y1 < area.y2 <= TABLET_H


def test_zoom_shrinks_area():
    full = forced_area(TABLET_W, TABLET_H, OUT_W, OUT_H, zoom=1.0)
    half = forced_area(TABLET_W, TABLET_H, OUT_W, OUT_H, zoom=0.5)
    assert half.width < full.width
    assert half.aspect == pytest.approx(full.aspect, rel=1e-2)


def test_rotation_swaps_target_aspect():
    a_o = OUT_W / OUT_H
    assert target_area_aspect(a_o, "none") == pytest.approx(a_o)
    assert target_area_aspect(a_o, "half") == pytest.approx(a_o)
    assert target_area_aspect(a_o, "cw") == pytest.approx(1 / a_o)
    assert target_area_aspect(a_o, "ccw") == pytest.approx(1 / a_o)


def test_rotated_area_is_height_limited():
    # With cw rotation onto a 16:9 output, the native area should become tall (full height).
    area = forced_area(TABLET_W, TABLET_H, OUT_W, OUT_H, rotate="cw")
    assert area.height == TABLET_H
    assert area.aspect == pytest.approx(OUT_H / OUT_W, rel=1e-3)


@pytest.mark.parametrize(
    "anchor,expect_x,expect_y",
    [
        ("top-left", 0, 0),
        ("top-right", 60, 0),
        ("bottom-left", 0, 80),
        ("center", 30, 40),
    ],
)
def test_place_rect_anchors(anchor, expect_x, expect_y):
    x, y = place_rect(100, 100, 40, 20, anchor)
    assert (x, y) == (expect_x, expect_y)


def test_area_helpers():
    a = Area(0, 1397, 44704, 26543)
    assert a.width == 44704
    assert a.height == 25146
    assert a.as_list() == [0, 1397, 44704, 26543]
