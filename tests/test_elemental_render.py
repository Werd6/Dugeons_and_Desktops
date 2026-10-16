"""Exercise the actual painter paths, including effects after their owner changes."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.render.elementals import draw_elemental
from dungeons_desktops.systems.elemental_powers import (
    SPECIALS,
    BurningPatch,
    Caught,
    FireballShot,
    Shockwave,
    Wave,
)
from dungeons_desktops.systems.elementals import KINDS, MELEE_WINDUP, SHIFT_TIME, Action
from dungeons_desktops.systems.flames import Flame
from dungeons_desktops.systems.world import SimWorld


def scene(kind):
    world = SimWorld([], 180.0, 360.0, ceiling=0.0, seed=2)
    elemental = world.add_elemental(Vec2(90, 180), kind=kind)
    target = world.add_stickman(Vec2(230, 180), "barbarian")
    target.stop()
    return world, elemental, target


def paint(elemental):
    image = QImage(360, 220, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        draw_elemental(painter, elemental, QColor("#20232a"))
    finally:
        painter.end()
    return image


def special_scene(kind):
    world, elemental, target = scene(kind)
    elemental.action = Action.SPECIAL
    elemental.special = SPECIALS[kind](elemental, target)
    elemental.special.time = elemental.special.windup * 0.9
    if kind == "water":
        elemental.effects = [Wave(235, 180, 0, 360, None, 1, travelled=85)]
    elif kind == "earth":
        elemental.effects = [Shockwave(90, 180, 0, 360, None, radius=100)]
    elif kind == "air":
        elemental.special.direction = Vec2(0.8, -0.6)
        elemental.effects = [Caught(target, Vec2(0.8, -0.6))]
    else:
        elemental.effects = [
            FireballShot(elemental, Vec2(170, 110), Vec2(120, -80)),
            BurningPatch(
                260,
                180,
                None,
                flames=[
                    Flame(Vec2(245 + i * 6, 176 - (i % 3) * 4), Vec2(0, -30), i * 0.03, 0.8)
                    for i in range(6)
                ],
            ),
        ]
    return world, elemental, target


@pytest.mark.parametrize("kind", KINDS)
def test_each_form_draws_idle_melee_and_special(kind):
    _, elemental, _ = scene(kind)
    idle = paint(elemental)
    elemental.action = Action.MELEE
    elemental.action_time = MELEE_WINDUP
    assert paint(elemental) != idle
    _, elemental, _ = special_scene(kind)
    assert paint(elemental) != idle


def test_shift_shrinks_and_burrow_clips_the_body_at_the_surface():
    _, elemental, _ = scene("earth")
    idle = paint(elemental)
    elemental.action = Action.SHIFT
    elemental.action_time = SHIFT_TIME / 2
    assert paint(elemental) != idle
    elemental.action = Action.BURROW
    elemental.sunk = 0.7
    sunk = paint(elemental)
    assert sunk != idle
    assert all(
        sunk.pixelColor(x, y).alpha() == 0
        for x in range(sunk.width())
        for y in range(182, sunk.height())
    )
    elemental.sunk = 1.0
    empty = paint(elemental)
    assert all(
        empty.pixelColor(x, y).alpha() == 0
        for x in range(empty.width())
        for y in range(empty.height())
    )


@pytest.mark.parametrize("kind", KINDS)
def test_effects_render_when_owner_is_underground_or_fully_faded(kind):
    _, elemental, _ = special_scene(kind)
    elemental.sunk = 1.0
    underground = paint(elemental)
    assert any(
        underground.pixelColor(x, y).alpha()
        for x in range(underground.width())
        for y in range(underground.height())
    )
    elemental.sunk = 0.0
    elemental.die(elemental.center(), Vec2(0, 0))
    elemental.down_time = 100.0
    assert paint(elemental) == underground
