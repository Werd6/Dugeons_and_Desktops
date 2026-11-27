"""Shared skull art used by the Lich's skeletons and skull-bearing heroes."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.render.primitives import pen, qt

BONE = QColor(226, 220, 196)
FAR = QColor(160, 154, 134)
SOCKET = QColor(22, 18, 24)
EYE = QColor(140, 255, 140)


def draw_skeleton_skull(
    painter: QPainter,
    center: Vec2,
    radius: float,
    facing: int,
    dead: bool = False,
    outline: QColor | None = None,
) -> None:
    """Draw the established Lich-skeleton skull at any center and scale."""
    if outline is not None:
        painter.setPen(pen(outline, 3.6))
        painter.setBrush(outline)
        painter.drawEllipse(qt(center), radius + 1.2, radius + 1.2)

    f = float(facing)
    painter.setPen(pen(FAR, 0.7))
    painter.setBrush(BONE)
    painter.drawEllipse(
        qt(center + Vec2(-0.1 * f * radius, -0.05 * radius)),
        radius,
        radius * 0.95,
    )
    jaw = QRectF(
        center.x + f * 0.05 * radius - 0.55 * radius,
        center.y + 0.55 * radius,
        1.1 * radius,
        0.55 * radius,
    )
    painter.drawRoundedRect(jaw, 1.0, 1.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(SOCKET)
    eye = center + Vec2(f * 0.42 * radius, -0.05 * radius)
    painter.drawEllipse(qt(eye), 0.32 * radius, 0.36 * radius)
    painter.drawEllipse(qt(eye + Vec2(-f * 0.55 * radius, 0.0)), 0.22 * radius, 0.32 * radius)
    painter.drawEllipse(
        qt(center + Vec2(f * 0.62 * radius, 0.38 * radius)),
        0.12 * radius,
        0.16 * radius,
    )
    painter.setPen(pen(SOCKET, 0.5))
    for index in range(3):
        x = center.x + f * (0.05 + 0.22 * index) * radius
        painter.drawLine(
            QPointF(x, center.y + 0.6 * radius),
            QPointF(x, center.y + 1.0 * radius),
        )
    if dead:
        return
    glow = QRadialGradient(qt(eye), radius * 0.9)
    glow.setColorAt(0.0, QColor(110, 255, 140, 150))
    glow.setColorAt(1.0, QColor(110, 255, 140, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(qt(eye), radius * 0.9, radius * 0.9)
    painter.setBrush(EYE)
    painter.drawEllipse(qt(eye), 0.13 * radius + 0.3, 0.13 * radius + 0.3)
