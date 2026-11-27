"""Aboleth swim locomotion, tentacle chains, and render smoke."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.desktop.session import SUPPORTED_DEFENDERS
from dungeons_desktops.game.defenders.aboleth.actor import ABOLETH_HP, MAX_LEAN, Aboleth
from dungeons_desktops.game.defenders.aboleth.render import (
    BODY,
    LOWER_SEGMENTS,
    UPPER_SEGMENTS,
    draw_aboleth,
    tentacle_chain,
)
from dungeons_desktops.game.unlocks import DEFENDER_NAMES
from dungeons_desktops.game.world.simulation import SimWorld

FLOOR = 400.0
STEP = 1 / 60


def run(world: SimWorld, seconds: float) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)


def test_aboleth_is_opt_in_defender():
    assert "aboleth" in SUPPORTED_DEFENDERS
    assert DEFENDER_NAMES["aboleth"] == "Aboleth"


def test_tentacle_chain_length_and_segments_are_stable():
    root = Vec2(0.0, 0.0)
    upper = tentacle_chain(root, -2.0, 34.0, UPPER_SEGMENTS, clock=1.5, phase=0.4)
    lower = tentacle_chain(
        root, 1.2, 44.0, LOWER_SEGMENTS, clock=1.5, phase=0.2, flick=0.5
    )
    assert len(upper) == UPPER_SEGMENTS + 1
    assert len(lower) == LOWER_SEGMENTS + 1
    # Bezier chord is near the requested length (not exact polyline arc length).
    assert 28.0 < upper[-1].distance_to(root) < 38.0
    assert 38.0 < lower[-1].distance_to(root) < 48.0


def test_s_curve_pulls_tentacle_off_a_simple_arc():
    root = Vec2(0.0, 0.0)
    plain = tentacle_chain(root, 1.2, 48.0, LOWER_SEGMENTS, 0.0, 0.0, bend=0.2)
    curved = tentacle_chain(
        root, 1.2, 48.0, LOWER_SEGMENTS, 0.0, 0.0, bend=0.2, s_curve=28.0
    )
    # Midpoint of a symmetric S lands on the chord; bow shows at the third-points.
    third = max(1, len(plain) // 3)
    assert curved[third].distance_to(plain[third]) > 5.0
    assert max(a.distance_to(b) for a, b in zip(plain, curved, strict=True)) > 7.0


def test_facing_flips_with_strong_sideways_drift_and_lean_stays_bounded():
    world = SimWorld([], FLOOR, 700, ceiling=0.0, seed=3)
    aboleth = world.add_aboleth(Vec2(350, 180), facing=1)
    aboleth.drift = Vec2(80.0, 0.0)
    aboleth.update(0.05)
    assert aboleth.facing == 1
    assert abs(aboleth.lean) <= MAX_LEAN + 1e-6

    aboleth.drift = Vec2(-80.0, 0.0)
    aboleth.update(0.05)
    assert aboleth.facing == -1
    assert abs(aboleth.lean) <= MAX_LEAN + 1e-6


def test_add_aboleth_swims_and_stays_on_screen():
    world = SimWorld([], FLOOR, 700, ceiling=0.0, seed=4)
    aboleth = world.add_aboleth(Vec2(200, 160), facing=1)
    assert aboleth.max_hp == ABOLETH_HP
    assert aboleth in world.monsters()
    assert world.locate(aboleth) == aboleth.center()
    assert world.monster_at(aboleth.center()) is aboleth

    start = aboleth.feet
    clock0 = aboleth.clock
    run(world, 3.0)
    assert aboleth.clock > clock0
    assert aboleth.feet.distance_to(start) > 1.0
    assert 40.0 <= aboleth.feet.x <= world.width - 40.0
    assert 20.0 <= aboleth.feet.y <= FLOOR - 10.0


def test_draw_aboleth_smoke_and_body_pixels():
    world = SimWorld([], FLOOR, 700, ceiling=0.0, seed=5)
    aboleth = world.add_aboleth(Vec2(180, 140), facing=1)
    image = QImage(360, 280, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_aboleth(painter, aboleth, QColor("#20232a"))
    draw_aboleth(painter, aboleth)
    painter.end()
    assert any(
        image.pixelColor(x, y).name() == BODY.name()
        for x in range(120, 250)
        for y in range(100, 180)
    )


def test_trail_bias_shifts_tentacle_curl():
    root = Vec2(0.0, 0.0)
    calm = tentacle_chain(root, 1.2, 40.0, LOWER_SEGMENTS, 2.0, 0.5, trail=0.0)
    trailed = tentacle_chain(root, 1.2, 40.0, LOWER_SEGMENTS, 2.0, 0.5, trail=-0.4)
    tip_delta = trailed[-1] - calm[-1]
    assert tip_delta.length() > 0.5
    assert math.isfinite(tip_delta.x)
