"""Flat procedural drawing for the soft-bodied ooze and its dissolved remains."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.ooze.actor import Ooze

BODY = QColor(116, 170, 66, 218)
BODY_DARK = QColor(58, 104, 42)
OUTLINE = QColor(34, 66, 30)
EYE = QColor(214, 232, 112)
BONE = QColor(222, 222, 188)
BONE_OUTLINE = QColor(72, 82, 58)


def _qt(point: Vec2) -> QPointF:
    return QPointF(point.x, point.y)


def _body_curve(points: list[Vec2], underside: list[Vec2]) -> QPainterPath:
    """Smooth the upper silhouette, then follow the supporting surface underneath."""
    path = QPainterPath(_qt(points[0]))
    count = len(points)
    for index in range(count - 1):
        before = points[index - 1] if index else points[index]
        start = points[index]
        end = points[index + 1]
        after = points[index + 2] if index + 2 < count else end
        first = start + (end - before) / 6.0
        second = end - (after - start) / 6.0
        path.cubicTo(_qt(first), _qt(second), _qt(end))
    for point in underside:
        path.lineTo(_qt(point))
    path.lineTo(_qt(points[0]))
    path.closeSubpath()
    return path


def _draw_skeletons(painter: QPainter, ooze: Ooze) -> None:
    for skeleton in ooze.skeletons:
        painter.save()
        painter.setOpacity((1.0 - ooze.fade) * (1.0 - skeleton.fade))
        painter.translate(_qt(ooze.to_world(skeleton.offset)))
        side, _ = ooze.local_frame(skeleton.offset.x)
        painter.rotate(math.degrees(side.angle()))
        painter.scale(float(skeleton.facing), 1.0)
        painter.setPen(
            QPen(BONE_OUTLINE, 3.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.setBrush(BONE)
        painter.drawEllipse(QPointF(0.0, -13.0), 5.5, 5.5)
        painter.drawLine(QPointF(0.0, -7.0), QPointF(0.0, 5.0))
        painter.drawLine(QPointF(-6.0, -3.0), QPointF(6.0, -3.0))
        painter.drawLine(QPointF(-5.0, 1.0), QPointF(5.0, 1.0))
        painter.drawLine(QPointF(0.0, 4.0), QPointF(-5.0, 12.0))
        painter.drawLine(QPointF(0.0, 4.0), QPointF(6.0, 11.0))
        painter.restore()


def draw_ooze(painter: QPainter, ooze: Ooze, outline: QColor | None = None) -> None:
    painter.save()
    painter.setOpacity(1.0 - ooze.fade)

    _draw_skeletons(painter, ooze)

    spine = list(ooze.rig.points())
    upper = [
        Vec2(-42.0, 0.0),
        Vec2(-43.0, -4.0),
        *spine,
        Vec2(43.0, -10.0),
        Vec2(41.0, -6.0),
        Vec2(40.0, 0.0),
    ]
    body = [ooze.to_world(point) for point in upper]
    underside = [ooze.to_world(Vec2(x, 0.0)) for x in range(36, -43, -4)]
    painter.setPen(
        QPen(
            outline or OUTLINE,
            1.5,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.setBrush(BODY)
    painter.drawPath(_body_curve(body, underside))

    eye = spine[-3] + Vec2(-1.0, 9.0)
    eye_world = ooze.to_world(eye)
    side, _ = ooze.local_frame(eye.x)
    painter.save()
    painter.translate(_qt(eye_world))
    painter.rotate(math.degrees(side.angle()))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(BODY_DARK)
    painter.drawEllipse(QPointF(0.0, 0.0), 8.5, 10.0)
    painter.setBrush(EYE)
    painter.drawEllipse(QPointF(2.5, -0.5), 2.7, 4.8)
    painter.restore()
    painter.restore()


def draw_oozes(
    painter: QPainter, oozes: Iterable[Ooze], outline: QColor | None = None
) -> None:
    for ooze in oozes:
        draw_ooze(painter, ooze, outline)
