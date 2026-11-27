"""Procedural segmented worm rendering."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.legendary import LEGENDARY_GOLD
from dungeons_desktops.game.defenders.worm.actor import Worm
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.primitives import qt, world_pen

WORM_SKIN = QColor(214, 128, 132)
WORM_RIDGE = QColor(160, 84, 92)
WORM_MOUTH = QColor(70, 16, 24)
WORM_TOOTH = QColor(255, 255, 255)
DEVOURER_TOOTH = LEGENDARY_GOLD
WORM_GHOST = QColor(214, 128, 132, 70)
WORM_GHOST_EDGE = QColor(120, 70, 60, 110)
WORM_HEAD_SCALE = 1.425
WORM_JAW_OPEN = 0.85
WORM_JAW_STRIKE = 0.3
WORM_TEETH_PER_JAW = 3
BURIED_WORM_VISIBLE = False


@chromatic_appearance
def draw_worm(painter: QPainter, worm: Worm, outline: QColor | None = None) -> None:
    points = worm.points
    buried = [worm.buried(point) for point in points]
    runs: list[list[Vec2]] = []
    for index in range(len(points) - 1):
        if BURIED_WORM_VISIBLE and buried[index] and buried[index + 1]:
            if not runs or runs[-1][-1] != points[index]:
                runs.append([points[index]])
            runs[-1].append(points[index + 1])
    stroker = QPainterPathStroker()
    stroker.setWidth(2.0 * worm.radius(len(points) // 3))
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(world_pen(WORM_GHOST_EDGE, 1.0))
    painter.setBrush(WORM_GHOST)
    for run in runs:
        path = QPainterPath(qt(run[0]))
        for point in run[1:]:
            path.lineTo(qt(point))
        painter.drawPath(stroker.createStroke(path).simplified())
    exposed = [
        index
        for index in range(len(points) - 1, 0, -1)
        if not (buried[index] and buried[index - 1])
    ]
    if outline is not None:
        for index in exposed:
            painter.setPen(world_pen(outline, 2.0 * worm.radius(index) + 2.0))
            painter.drawLine(qt(points[index]), qt(points[index - 1]))
    for index in exposed:
        painter.setPen(world_pen(WORM_SKIN, 2.0 * worm.radius(index)))
        painter.drawLine(qt(points[index]), qt(points[index - 1]))
    painter.setPen(world_pen(WORM_RIDGE, 0.8))
    for index in exposed:
        if index % 2 == 0:
            along = (points[index - 1] - points[index]).normalized()
            across = Vec2(-along.y, along.x) * (worm.radius(index) * 0.85)
            painter.drawLine(qt(points[index] + across), qt(points[index] - across))
    head = worm.head
    radius = worm.radius(0)
    if buried[0]:
        if not BURIED_WORM_VISIBLE:
            return
        painter.setPen(world_pen(WORM_GHOST_EDGE, 1.0))
        painter.setBrush(WORM_GHOST)
        painter.drawEllipse(qt(head + Vec2.from_angle(worm.heading, 1.5)), radius, radius)
        return
    _draw_worm_head(
        painter,
        head,
        worm.heading,
        radius * WORM_HEAD_SCALE,
        worm.mouth,
        outline,
        tooth=DEVOURER_TOOTH if getattr(worm, "legendary", False) else WORM_TOOTH,
    )


def _draw_worm_head(
    painter: QPainter,
    center: Vec2,
    heading: float,
    radius: float,
    mouth: float,
    outline: QColor | None,
    tooth: QColor = WORM_TOOTH,
) -> None:
    half = WORM_JAW_OPEN + WORM_JAW_STRIKE * mouth
    forward = Vec2.from_angle(heading)
    hinge = center - forward * (radius * 0.3)

    def rim(angle: float, scale: float = 1.0) -> Vec2:
        return center + Vec2.from_angle(angle, radius * scale)

    around = [rim(heading + half + (math.tau - 2 * half) * index / 28) for index in range(29)]
    skull = [qt(hinge), *(qt(point) for point in around)]
    if outline is not None:
        painter.setPen(world_pen(outline, 2.0))
        painter.setBrush(outline)
        painter.drawPolygon(skull)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(WORM_SKIN)
    painter.drawPolygon(skull)
    throat = [rim(heading - half + 2 * half * index / 10, 0.8) for index in range(11)]
    painter.setBrush(WORM_MOUTH)
    painter.drawPolygon([qt(hinge), *(qt(point) for point in throat)])
    painter.setPen(world_pen(WORM_MOUTH, 1.2))
    painter.drawPolyline([qt(rim(heading + half)), qt(hinge), qt(rim(heading - half))])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tooth)
    for side in (-1.0, 1.0):
        tip = rim(heading + side * half)
        edge = tip - hinge
        along = edge.normalized()
        inward = (forward - along * forward.dot(along)).normalized()
        width = edge.length() * 0.7 / WORM_TEETH_PER_JAW
        for index in range(WORM_TEETH_PER_JAW):
            base = hinge + edge * (0.3 + 0.7 * (index + 0.5) / WORM_TEETH_PER_JAW)
            length = width * (1.0 + 0.5 * index / max(1, WORM_TEETH_PER_JAW - 1))
            painter.drawPolygon(
                [
                    qt(base - along * (width / 2)),
                    qt(base + along * (width / 2)),
                    qt(base + inward * length + along * (width * 0.15)),
                ]
            )
