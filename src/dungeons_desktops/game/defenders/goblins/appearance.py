"""Shared goblin skin palette and face, independent of faction or equipment."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.render.primitives import pen, qt
from dungeons_desktops.rig.skeleton import BoneTransform

GOBLIN_SKIN = QColor(132, 186, 88)
GOBLIN_FAR = QColor(88, 128, 60)
GOBLIN_HEAD = QColor(58, 92, 44)
GOBLIN_EYE = QColor(250, 220, 80)


def draw_goblin_face(painter: QPainter, actor: Actor, transforms: dict[str, BoneTransform]) -> None:
    facing = actor.facing
    radius, scale = actor.layout.head_radius, actor.layout.scale
    center = transforms[actor.layout.head].end
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
    painter.drawEllipse(qt(center + Vec2(facing * 0.45 * radius, -0.15 * radius)), eye, eye)
    painter.setPen(pen(GOBLIN_SKIN, max(0.5, 1.2 * scale)))
    mouth = center + Vec2(facing * 0.35 * radius, 0.4 * radius)
    painter.drawLine(qt(mouth), qt(mouth + Vec2(facing * 3.0, -0.8) * scale))
