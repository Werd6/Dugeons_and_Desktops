"""The dragon's scalloped membrane geometry, shared by folded-wing creatures."""

from collections.abc import Callable

from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.render.primitives import qt, world_pen


def folded_wing(root: Vec2, local: Callable[[Vec2], Vec2], scale: float) -> tuple[Vec2, ...]:
    return (
        root,
        *(
            root + local(p * scale)
            for p in (Vec2(-5, -7), Vec2(-19, -4), Vec2(-15, -1), Vec2(-9, 0))
        ),
    )


def draw_wing(
    painter: QPainter,
    points: tuple[Vec2, ...],
    scale: float,
    membrane: QColor,
    edge: QColor,
    bone: QColor,
    rib: QColor,
) -> None:
    root, elbow, tip, trailing, back = points

    def notch(a: Vec2, b: Vec2) -> Vec2:
        return a.lerp(b, 0.5).lerp(elbow, 0.22)

    painter.setPen(world_pen(edge, 1.2 * scale))
    painter.setBrush(membrane)
    outline = [root, elbow, tip, notch(tip, trailing), trailing, notch(trailing, back), back]
    painter.drawPolygon([qt(point) for point in outline])
    painter.setPen(world_pen(bone, 2.0 * scale))
    painter.drawPolyline([qt(root), qt(elbow), qt(tip)])
    painter.setPen(world_pen(rib, 0.8 * scale))
    painter.drawLine(qt(elbow), qt(trailing))
