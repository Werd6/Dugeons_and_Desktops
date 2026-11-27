"""Charcoal scales split by glowing magma, on the original dragon's animated rig."""

import math

from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.dragon.actor import SCALE
from dungeons_desktops.game.defenders.dragon.render import (
    DragonPalette,
    _dragon_limb,
    draw_dragon,
)
from dungeons_desktops.game.heroes.natures_wrath.dragon import MagmaDragon
from dungeons_desktops.render.primitives import qt, world_pen

MAGMA = DragonPalette(
    skin=QColor(49, 45, 46),
    far=QColor(27, 25, 29),
    belly=QColor(79, 52, 43),
    wing=QColor(44, 38, 42, 245),
    wing_far=QColor(29, 25, 31, 240),
    horn=QColor(105, 91, 82),
    talon=QColor(21, 19, 22),
    eye=QColor(255, 235, 97),
    wing_bone=QColor(225, 87, 25),
)


def draw_magma_dragon(
    painter: QPainter, dragon: MagmaDragon, outline: QColor | None = None
) -> None:
    def cracks() -> None:
        s = SCALE * dragon.size
        pulse = 0.8 + 0.2 * math.sin(dragon.clock * 3)

        def seam(points: list[Vec2]) -> None:
            path = QPainterPath(qt(points[0]))
            for point in points[1:]:
                path.lineTo(qt(point))
            for color, width in (
                (QColor(255, 68, 9, int(65 * pulse)), 2.8 * s),
                (QColor(255, 103, 18, int(245 * pulse)), 1.0 * s),
                (QColor(255, 215, 91, int(240 * pulse)), 0.34 * s),
            ):
                painter.setPen(world_pen(color, width))
                painter.drawPath(path)

        def split(start: Vec2, end: Vec2, width: float) -> None:
            side = (end - start).normalized().rotated(math.pi / 2)
            points = [start]
            for i, offset in enumerate((0.55, -0.3, 0.7, -0.45), 1):
                points.append(start.lerp(end, i / 5) + side * width * offset)
            points.append(end)
            seam(points)
            seam([points[2], points[2] + side * width, points[3] + side * width * 1.4])

        split(dragon.hip, dragon.shoulder, 3.5 * s)
        split(dragon.neck_base, dragon.head, 1.8 * s)
        for leg in dragon.legs:
            if leg.near:
                joints = _dragon_limb(dragon, leg).joints
                split(joints[0], joints[1], 1.5 * s)
                seam(joints[1:])
        for i in range(0, len(dragon.tail) - 1, 2):
            split(dragon.tail[i], dragon.tail[i + 1], 0.7 * s)

    painter.save()
    draw_dragon(painter, dragon, outline, palette=MAGMA, details=cracks)
    painter.restore()
