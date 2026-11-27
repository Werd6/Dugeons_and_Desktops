"""Iggy's chromatic beams, curling missile trails, summon shimmer, and shared doors."""

import math
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.defenders.lich.render import draw_dimension_door
from dungeons_desktops.game.heroes.the_inquisitive.spells import CAST_RELEASE, RAY_FADE, RAY_TIME
from dungeons_desktops.render.primitives import alpha, qt, world_pen

MAGIC = QColor(141, 156, 255)
CORE = QColor(227, 243, 255)


def draw_iggy_spells(painter: QPainter, actors: Iterable[Stickman]) -> None:
    painter.save()
    for actor in actors:
        if actor.variant != "hero_wizard":
            continue
        if actor.door is not None:
            draw_dimension_door(painter, actor.door, scale=0.6)
        if actor.animated and actor.casting is not None:
            charge = min(1.0, actor.cast_time / CAST_RELEASE)
            tip = actor.wand_tip()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(alpha(MAGIC, 64 + 51 * charge))
            painter.drawEllipse(qt(tip), 2 + charge * 2, 2 + charge * 2)
            painter.setBrush(CORE)
            painter.drawEllipse(qt(tip), 0.5 + charge, 0.5 + charge)
        for ray in actor.spells.rays:
            fade = min(1.0, max(0.0, (RAY_TIME + RAY_FADE - ray.age) / RAY_FADE))
            color = QColor(*ray.color)
            # A brief colored afterimage makes the motion readable without filling the cone.
            for index, end in enumerate(ray.trail[:-1]):
                painter.setPen(world_pen(alpha(color, fade * (index + 1) * 6), 2.5))
                painter.drawLine(qt(ray.start), qt(end))
            pulse = 0.4 * math.sin(ray.age * 22)
            for width, ink in ((10 + pulse, alpha(color, fade * 42)),
                               (4.5 + pulse, alpha(color, fade * 230)),
                               (1.1, alpha(CORE, fade * 255))):
                painter.setPen(world_pen(ink, width))
                painter.drawLine(qt(ray.start), qt(ray.end))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(alpha(color, fade * 110))
            painter.drawEllipse(qt(ray.start), 4, 4)
            painter.setBrush(alpha(CORE, fade * 255))
            painter.drawEllipse(qt(ray.start), 1.7, 1.7)
        for missile in actor.spells.missiles:
            path = QPainterPath(qt(missile.trail[0]))
            for point in missile.trail[1:]:
                path.lineTo(qt(point))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(alpha(MAGIC, 64), 4.5))
            painter.drawPath(path)
            painter.setPen(world_pen(MAGIC, 1.8))
            painter.drawPath(path)
            painter.setPen(world_pen(CORE, 0.55))
            painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(CORE)
            painter.drawEllipse(qt(missile.trail[-1]), 1.6, 1.6)
        for spark in actor.spells.sparks:
            t = spark.age / 0.5
            color = alpha(QColor(*spark.color), 255 * (1 - t))
            painter.setPen(world_pen(color, 0.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = spark.radius * t
            painter.drawEllipse(qt(spark.point), radius, radius)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            for index in range(7):
                angle = index * math.tau / 7 + t
                point = spark.point + Vec2.from_angle(angle, radius)
                painter.drawEllipse(qt(point), 1 - t * 0.6, 1 - t * 0.6)
    painter.restore()
