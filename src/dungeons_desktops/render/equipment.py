"""Rendering for shared procedural equipment strokes."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.render.primitives import qt, world_pen
from dungeons_desktops.rig.equipment import Stroke

WEAPON_COLORS = {
    "steel": QColor(214, 224, 238),
    "hilt": QColor(206, 160, 78),
    "wood": QColor(150, 100, 62),
    "metal": QColor(128, 134, 150),
    "gunmetal": QColor(62, 72, 82),
    "scope_glass": QColor(126, 195, 211),
    "flash": QColor(255, 222, 120),
    "magic": QColor(196, 120, 255),
    "simulacrum": QColor(124, 203, 255),
    "shadow": QColor(116, 102, 155),
    "orb": QColor(255, 110, 176),
    "holy": QColor(252, 250, 240),
    "sun_wood": QColor(137, 86, 45),
    "sun_glow": QColor(255, 213, 92, 75),
    "sun_gold": QColor(255, 205, 70),
    "sun_core": QColor(255, 255, 232),
    "string": QColor(228, 222, 204),
    "shield": QColor(52, 84, 156),
    "grave_shield": QColor(50, 62, 72),
    "grave_trim": QColor(150, 164, 174),
    "grave_boss": QColor(91, 226, 204),
    "hero_shield": QColor(36, 48, 62),
    "hero_shield_trim": QColor(214, 226, 234),
    "hero_shield_strap": QColor(78, 88, 94),
    "hero_shield_boss": QColor(236, 224, 194),
    "divine_glow": QColor(176, 214, 255, 70),
    "divine": QColor(198, 214, 226),
    "divine_core": QColor(252, 255, 255),
    "bomb": QColor(220, 40, 52),
    "hero_vial": QColor(74, 220, 104),
    "glass": QColor(235, 200, 205),
    "cork": QColor(160, 115, 70),
    "leaf": QColor(92, 170, 70),
}
TRAIL = QColor(190, 215, 255)


def draw_strokes(painter: QPainter, strokes: Iterable[Stroke]) -> None:
    for stroke in strokes:
        color = WEAPON_COLORS[stroke.kind]
        painter.setPen(world_pen(color, stroke.width))
        if stroke.shape:
            painter.setBrush(color)
            painter.drawPolygon([qt(point) for point in stroke.shape])
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.drawLine(qt(stroke.start), qt(stroke.end))


def draw_trail(painter: QPainter, trail: list[Vec2]) -> None:
    for index, (start, end) in enumerate(zip(trail, trail[1:], strict=False)):
        color = QColor(TRAIL)
        color.setAlpha(int(200 * (index + 1) / len(trail)))
        painter.setPen(world_pen(color, 1.0 + 2.0 * (index + 1) / len(trail)))
        painter.drawLine(qt(start), qt(end))
