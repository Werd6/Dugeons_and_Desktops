"""Procedural goblin and war-banner rendering."""

from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.render import draw_body
from dungeons_desktops.game.defenders.goblins.actor import Goblin
from dungeons_desktops.game.defenders.goblins.appearance import (
    GOBLIN_EYE,
    GOBLIN_FAR,
    GOBLIN_HEAD,
    GOBLIN_SKIN,
    draw_goblin_face,
)
from dungeons_desktops.game.defenders.goblins.weapons import Banner
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import qt, world_pen
from dungeons_desktops.rig.equipment import Stroke
from dungeons_desktops.rig.skeleton import BoneTransform

BANNER_COLOR = QColor(150, 30, 34)
BANNER_EDGE = QColor(60, 14, 16)
KING_GOLD = QColor(246, 190, 48)
KING_GOLD_DARK = QColor(132, 76, 18)
KING_EYE = QColor(255, 246, 92)
GOLD_WEAPON_KINDS = {
    "steel": "sun_gold",
    "hilt": "sun_gold",
    "wood": "sun_gold",
    "metal": "sun_gold",
}


def _gold_strokes(strokes: list[Stroke]) -> list[Stroke]:
    return [
        replace(stroke, kind=GOLD_WEAPON_KINDS.get(stroke.kind, stroke.kind)) for stroke in strokes
    ]


@chromatic_appearance
def draw_goblin(painter: QPainter, goblin: Goblin, outline: QColor | None = None) -> None:
    crowned = goblin.crowned and getattr(goblin, "legendary", False)
    facing = goblin.facing
    weapon = goblin.weapon
    strokes = weapon.strokes(goblin.transforms(), facing)
    if getattr(goblin, "legendary", False):
        strokes = _gold_strokes(strokes)
    held = weapon.held

    def ear(transforms) -> None:
        draw_goblin_face(painter, goblin, transforms)
        if crowned:
            _draw_king_trim(painter, goblin, transforms)
        if held:
            draw_strokes(painter, strokes)
            if isinstance(weapon, Banner):
                _draw_banner_cloth(painter, weapon, transforms, facing)

    if not held:
        if isinstance(weapon, Banner):
            _draw_banner_cloth(painter, weapon, goblin.transforms(), facing)
        draw_strokes(painter, strokes)
    draw_body(painter, goblin, GOBLIN_SKIN, GOBLIN_FAR, GOBLIN_HEAD, ear, outline=outline)


def _draw_king_trim(painter: QPainter, goblin: Goblin, transforms) -> None:
    """A rough gold circlet, hot eye and rings on the Goblin King."""
    center = transforms[goblin.layout.head].end
    radius, scale = goblin.layout.head_radius, goblin.layout.scale
    facing = goblin.facing
    painter.setPen(world_pen(KING_GOLD_DARK, max(0.5, 0.8 * scale)))
    painter.setBrush(KING_GOLD)
    crown = [
        center + Vec2(-radius * 0.75, -radius * 0.65),
        center + Vec2(-radius * 0.55, -radius * 1.15),
        center + Vec2(-radius * 0.15, -radius * 0.72),
        center + Vec2(radius * 0.2, -radius * 1.25),
        center + Vec2(radius * 0.55, -radius * 0.68),
        center + Vec2(radius * 0.72, -radius * 0.58),
    ]
    painter.drawPolygon([qt(point) for point in crown])
    painter.setPen(world_pen(KING_GOLD, max(0.7, 1.1 * scale)))
    ear = center + Vec2(-facing * radius * 0.9, radius * 0.05)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(qt(ear), 1.5 * scale, 2.2 * scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(KING_EYE)
    eye = center + Vec2(facing * 0.45 * radius, -0.15 * radius)
    painter.drawEllipse(qt(eye), 1.8 * scale, 1.8 * scale)


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
