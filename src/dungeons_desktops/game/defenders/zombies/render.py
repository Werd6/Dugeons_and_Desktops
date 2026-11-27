"""Faceless green stick figures with thick limbs and empty, reaching arms."""

from collections.abc import Iterable

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient

from dungeons_desktops.game.adventurers.render import draw_body
from dungeons_desktops.game.defenders.zombies.actor import Zombie
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.primitives import qt

SKIN = QColor(91, 178, 65)
FAR = QColor(49, 111, 45)
HEAD = QColor(119, 186, 83)


@chromatic_appearance
def draw_zombie(painter: QPainter, zombie: Zombie, outline: QColor | None = None) -> None:
    if outline is None and getattr(zombie, "legendary", False):
        center = zombie.center()
        pulse = 0.85 + 0.15 * math.sin(zombie._shamble_phase + zombie.down_time * 3.0)
        haze = QRadialGradient(qt(center), 24.0)
        haze.setColorAt(0.0, QColor(116, 196, 66, int(62 * pulse)))
        haze.setColorAt(1.0, QColor(52, 124, 38, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(haze)
        painter.drawEllipse(qt(center), 24.0, 20.0)
    draw_body(
        painter,
        zombie,
        SKIN,
        FAR,
        HEAD,
        outline=outline,
        body_width=5.0 * zombie.layout.scale,
        head_width=3.0 * zombie.layout.scale,
        show_joints=False,
    )


def draw_zombies(
    painter: QPainter, zombies: Iterable[Zombie], outline: QColor | None = None
) -> None:
    for zombie in zombies:
        draw_zombie(painter, zombie, outline)
