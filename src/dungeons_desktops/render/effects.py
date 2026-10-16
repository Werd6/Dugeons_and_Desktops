"""Shared fire and transient-effect rendering."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.game.effects.flames import FLAME_LIFE, Flame
from dungeons_desktops.render.primitives import alpha, mix, qt

FLAME_HOT = QColor(255, 244, 170)
FLAME_MID = QColor(255, 150, 40)
FLAME_SMOKE = QColor(110, 60, 40)
FLAME_RED = QColor(225, 60, 25)


def draw_fire(painter: QPainter, flames: Iterable[Flame]) -> None:
    """Draw flames fading from a white core through orange into smoke."""
    painter.setPen(Qt.PenStyle.NoPen)
    for flame in flames:
        age = flame.age / FLAME_LIFE
        radius = flame.radius
        if age < 0.55:
            color = mix(FLAME_HOT, FLAME_MID, age / 0.55)
        else:
            color = mix(FLAME_MID, FLAME_SMOKE, (age - 0.55) / 0.45)
        painter.setBrush(alpha(color, 230 * (1.0 - age) ** 0.8))
        painter.drawEllipse(qt(flame.position), radius, radius)
        if age < 0.35:
            painter.setBrush(alpha(FLAME_HOT, 200 * (1.0 - age / 0.35)))
            painter.drawEllipse(qt(flame.position), radius * 0.45, radius * 0.45)
