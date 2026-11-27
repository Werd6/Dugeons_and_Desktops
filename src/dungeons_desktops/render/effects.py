"""Shared fire and transient-effect rendering."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.game.effects.flames import Flame
from dungeons_desktops.render.primitives import alpha, mix, qt

FLAME_HOT = QColor(255, 244, 170)
FLAME_MID = QColor(255, 150, 40)
FLAME_SMOKE = QColor(110, 60, 40)
FLAME_RED = QColor(225, 60, 25)

# Blue / white-hot (Primal chimera goat).
FLAME_BLUE_HOT = QColor(245, 250, 255)
FLAME_BLUE_MID = QColor(90, 170, 255)
FLAME_BLUE_SMOKE = QColor(40, 70, 140)

# Green (Primal chimera serpent).
FLAME_GREEN_HOT = QColor(220, 255, 170)
FLAME_GREEN_MID = QColor(70, 210, 70)
FLAME_GREEN_SMOKE = QColor(28, 90, 36)

_FIRE_PALETTES = {
    "": (FLAME_HOT, FLAME_MID, FLAME_SMOKE),
    "orange": (FLAME_HOT, FLAME_MID, FLAME_SMOKE),
    "lion": (FLAME_HOT, FLAME_MID, FLAME_SMOKE),
    "blue": (FLAME_BLUE_HOT, FLAME_BLUE_MID, FLAME_BLUE_SMOKE),
    "goat": (FLAME_BLUE_HOT, FLAME_BLUE_MID, FLAME_BLUE_SMOKE),
    "green": (FLAME_GREEN_HOT, FLAME_GREEN_MID, FLAME_GREEN_SMOKE),
    "snake": (FLAME_GREEN_HOT, FLAME_GREEN_MID, FLAME_GREEN_SMOKE),
}


def draw_fire(painter: QPainter, flames: Iterable[Flame]) -> None:
    """Draw flames fading from a white core through mid-color into smoke.

    Flame.`palette` picks the tint: empty/orange (default), blue/goat, or green/snake.
    """
    painter.setPen(Qt.PenStyle.NoPen)
    for flame in flames:
        span = max(flame.life, 1e-3)
        age = min(1.0, flame.age / span)
        radius = flame.radius
        hot, mid, smoke = _FIRE_PALETTES.get(getattr(flame, "palette", ""), _FIRE_PALETTES[""])
        if age < 0.55:
            color = mix(hot, mid, age / 0.55)
        else:
            color = mix(mid, smoke, (age - 0.55) / 0.45)
        painter.setBrush(alpha(color, 230 * (1.0 - age) ** 0.8))
        painter.drawEllipse(qt(flame.position), radius, radius)
        if age < 0.35:
            painter.setBrush(alpha(hot, 200 * (1.0 - age / 0.35)))
            painter.drawEllipse(qt(flame.position), radius * 0.45, radius * 0.45)
