"""Procedural goblin and war-banner rendering."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.render import draw_body
from dungeons_desktops.game.defenders.goblins.actor import Goblin
from dungeons_desktops.game.defenders.goblins.weapons import Banner
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import pen, qt, world_pen
from dungeons_desktops.rig.skeleton import BoneTransform

GOBLIN_SKIN = QColor(132, 186, 88)
GOBLIN_FAR = QColor(88, 128, 60)
GOBLIN_HEAD = QColor(58, 92, 44)
GOBLIN_EYE = QColor(250, 220, 80)
BANNER_COLOR = QColor(150, 30, 34)
BANNER_EDGE = QColor(60, 14, 16)


def draw_goblin(painter: QPainter, goblin: Goblin, outline: QColor | None = None) -> None:
    facing = goblin.facing
    radius = goblin.layout.head_radius
    scale = goblin.layout.scale
    weapon = goblin.weapon
    strokes = weapon.strokes(goblin.transforms(), facing)
    held = weapon.held

    def ear(transforms) -> None:
        center = transforms[goblin.layout.head].end
        back = -facing
        points = [
            center + Vec2(back * 0.5 * radius, -0.7 * radius),
            center + Vec2(back * (radius + 8.0 * scale), -1.1 * radius),
            center + Vec2(back * 0.9 * radius, 0.1 * radius),
        ]
        painter.setPen(pen(GOBLIN_SKIN, max(0.6, 1.5 * scale)))
        painter.setBrush(GOBLIN_HEAD)
        painter.drawPolygon([qt(point) for point in points])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(GOBLIN_EYE)
        eye = max(0.6, 1.5 * scale)
        painter.drawEllipse(
            qt(center + Vec2(facing * 0.45 * radius, -0.15 * radius)), eye, eye
        )
        painter.setPen(pen(GOBLIN_SKIN, max(0.5, 1.2 * scale)))
        mouth = center + Vec2(facing * 0.35 * radius, 0.4 * radius)
        painter.drawLine(qt(mouth), qt(mouth + Vec2(facing * 3.0, -0.8) * scale))
        if held:
            draw_strokes(painter, strokes)
            if isinstance(weapon, Banner):
                _draw_banner_cloth(painter, weapon, transforms, facing)

    if not held:
        if isinstance(weapon, Banner):
            _draw_banner_cloth(painter, weapon, goblin.transforms(), facing)
        draw_strokes(painter, strokes)
    draw_body(painter, goblin, GOBLIN_SKIN, GOBLIN_FAR, GOBLIN_HEAD, ear, outline=outline)


def _draw_banner_cloth(
    painter: QPainter, banner: Banner, transforms: dict[str, BoneTransform], facing: int
) -> None:
    top, _ = banner.top(transforms, facing)
    scale = banner.scale
    back = Vec2(-facing, 0.0)
    width, height = 26.0 * scale, 16.0 * scale
    upper, lower = [], []
    for index in range(5):
        amount = index / 4
        wave = math.sin(banner.clock * 9.0 - amount * 4.0) * 2.5 * scale * amount
        along = top + back * (width * amount)
        upper.append(along + Vec2(0.0, wave))
        lower.append(along + Vec2(0.0, height * (1.0 - 0.25 * amount) + wave))
    lower[-1] = lower[-1] + back * (-4.0 * scale) + Vec2(0.0, -height * 0.3)
    painter.setPen(world_pen(BANNER_EDGE, 2.4 * scale))
    painter.setBrush(BANNER_COLOR)
    painter.drawPolygon([qt(point) for point in upper + lower[::-1]])
    middle = top + back * (width * 0.4) + Vec2(0.0, height * 0.45)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(GOBLIN_EYE)
    painter.drawEllipse(qt(middle), 3.0 * scale, 3.0 * scale)
    painter.setBrush(BANNER_EDGE)
    painter.drawEllipse(qt(middle), 1.2 * scale, 1.8 * scale)
