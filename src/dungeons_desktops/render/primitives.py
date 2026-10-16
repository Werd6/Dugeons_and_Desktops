"""Small Qt drawing primitives shared by feature renderers."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from dungeons_desktops.core.geometry import Vec2, clamp


def qt(point: Vec2) -> QPointF:
    return QPointF(point.x, point.y)


def pen(color: QColor, width: float, style=Qt.PenStyle.SolidLine) -> QPen:
    """Create a cosmetic pen whose width is measured in screen pixels."""
    result = QPen(color, width, style, Qt.PenCapStyle.RoundCap)
    result.setCosmetic(True)
    return result


def world_pen(color: QColor, width: float) -> QPen:
    """Create a pen whose width scales in world coordinates."""
    return QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)


def alpha(color: QColor, opacity: float) -> QColor:
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(opacity))))
    return result


def mix(a: QColor, b: QColor, amount: float) -> QColor:
    amount = clamp(amount, 0.0, 1.0)
    return QColor(
        int(a.red() + (b.red() - a.red()) * amount),
        int(a.green() + (b.green() - a.green()) * amount),
        int(a.blue() + (b.blue() - a.blue()) * amount),
        int(a.alpha() + (b.alpha() - a.alpha()) * amount),
    )
