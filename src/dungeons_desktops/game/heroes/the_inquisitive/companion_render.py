"""A tiny charcoal cat: pointed ears, bright eyes, blue collar, and a curling tail."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.game.heroes.the_inquisitive.companion import CatCompanion
from dungeons_desktops.render.primitives import world_pen

FUR = QColor(62, 66, 84)
FUR_FAR = QColor(39, 43, 59)
FUR_EDGE = QColor(119, 127, 151)
CHEEK = QColor(161, 171, 193)
EAR = QColor(216, 133, 169)
EYE = QColor(165, 246, 134)
COLLAR = QColor(79, 164, 255)


def draw_cat(painter: QPainter, cat: CatCompanion) -> None:
    if cat.opacity <= 0 or cat.owner.swallowed or cat.owner.reeled is not None:
        return
    painter.save()
    painter.setOpacity(painter.opacity() * cat.opacity)
    painter.translate(cat.feet.x, cat.feet.y)
    painter.rotate(math.degrees(cat.angle))
    painter.scale(cat.facing, 1)
    draw_cat_shape(painter, cat.time, cat.phase, cat.motion)
    painter.restore()


def draw_cat_shape(painter: QPainter, time: float, phase: float = 0, motion: float = 0) -> None:
    """The shared cat silhouette, in local coordinates with its paws at the origin."""
    wave = math.tau * phase
    bob = math.cos(wave * 2) * 0.2 * motion

    # The tail stays lively while the paws settle when Iggy stops.
    sway = math.sin(time * 2.5) * 0.8
    tail = QPainterPath(QPointF(-3.2, -3.4 + bob))
    tail.cubicTo(-7.3, -4.0, -7.5 + sway, -9.3, -5.8 + sway, -9.0)
    tail.cubicTo(-4.6 + sway, -8.7, -4.7 + sway, -7.3, -5.6 + sway, -7.2)
    painter.setPen(world_pen(FUR_EDGE, 1.3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(tail)
    painter.setPen(world_pen(FUR, 0.9))
    painter.drawPath(tail)

    def legs(near: bool) -> None:
        painter.setPen(world_pen(FUR if near else FUR_FAR, 1.1 if near else 0.9))
        for index, x in enumerate((-2.6, 2.1)):
            phase = wave + index * math.pi + (0 if near else math.pi)
            step = math.sin(phase) * 1.25 * motion
            lift = max(0.0, math.cos(phase)) * 0.9 * motion
            foot = QPointF(x + step, -0.45 - lift)
            painter.drawLine(QPointF(x, -3.1 + bob), foot)
            painter.drawLine(foot, QPointF(foot.x() + 0.6, foot.y()))

    legs(False)
    painter.setPen(world_pen(FUR_EDGE, 0.35))
    painter.setBrush(FUR)
    painter.drawEllipse(QPointF(-0.3, -3.7 + bob), 3.8, 2.0)
    legs(True)
    # Round head and two clear triangular ears make the small silhouette readable.
    painter.setPen(world_pen(FUR_EDGE, 0.35))
    painter.setBrush(FUR)
    painter.drawPolygon([
        QPointF(1.6, -6.1 + bob), QPointF(1.5, -9.0 + bob), QPointF(3.7, -7.1 + bob),
        QPointF(5.0, -8.7 + bob), QPointF(5.4, -5.4 + bob),
    ])
    painter.drawEllipse(QPointF(3.6, -5.8 + bob), 2.25, 2.1)
    painter.setPen(world_pen(EAR, 0.4))
    painter.drawLine(QPointF(2.0, -8.0 + bob), QPointF(2.5, -7.2 + bob))
    painter.setPen(world_pen(COLLAR, 0.65))
    painter.drawLine(QPointF(2.2, -4.1 + bob), QPointF(4.7, -4.0 + bob))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(CHEEK)
    painter.drawEllipse(QPointF(5.2, -5.1 + bob), 0.8, 0.55)
    painter.setBrush(EYE)
    painter.drawEllipse(QPointF(4.35, -6.1 + bob), 0.55, 0.5)
    painter.setBrush(FUR_FAR)
    painter.drawEllipse(QPointF(4.5, -6.1 + bob), 0.14, 0.4)
    painter.setBrush(EAR)
    painter.drawEllipse(QPointF(5.9, -5.45 + bob), 0.25, 0.2)
