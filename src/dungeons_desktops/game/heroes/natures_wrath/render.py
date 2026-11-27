"""Natures Wrath's leafy cape, red mohawk, and quiet nature magic."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.defenders.goblins.appearance import draw_goblin_face
from dungeons_desktops.render.primitives import alpha, qt, world_pen
from dungeons_desktops.rig.skeleton import BoneTransform

MOHAWK = QColor(222, 42, 48)
MOHAWK_EDGE = QColor(112, 20, 28)
BODY_WIDTH = 5.5
LEAF = QColor(148, 216, 100)
LEAF_LIGHT = QColor(216, 236, 150)
CAPE = QColor(38, 91, 65)
CAPE_EDGE = QColor(112, 156, 88)
CAPE_FOLD = QColor(58, 117, 76)


def draw_natures_wrath_cape(
    painter: QPainter, hero: Actor, transforms: dict[str, BoneTransform]
) -> None:
    """A short forest-green cape, with a leaf-cut hem and a gentle trailing sway."""
    torso = transforms[hero.layout.torso]
    down = (torso.start - torso.end).normalized()
    back = Vec2(-down.y, down.x) * hero.facing
    radius = hero.layout.head_radius
    time = getattr(hero, "nature_time", 0.0)
    pace = min(1.0, hero.velocity.length() / 50.0) if hero.animated else 0.0
    flutter = math.sin(time * 3.5) * (0.08 + pace * 0.18) if hero.animated else 0.0
    shoulder = torso.end + back * (0.22 * radius) + down * (0.12 * radius)

    def point(trail: float, drop: float) -> Vec2:
        sway = (pace * 0.7 + flutter) * (drop / 2.5) ** 2
        return shoulder + back * ((trail + sway) * radius) + down * (drop * radius)

    cape = QPainterPath(qt(shoulder))
    cape.cubicTo(qt(point(0.8, 0.35)), qt(point(0.8, 1.65)), qt(point(1.5, 2.25)))
    for trail, drop in ((1.0, 2.18), (0.93, 2.6), (0.5, 2.35), (0.22, 2.65), (-0.1, 2.3)):
        cape.lineTo(qt(point(trail, drop)))
    cape.quadTo(qt(point(-0.15, 1.1)), qt(shoulder))
    cape.closeSubpath()
    painter.save()
    painter.setPen(world_pen(CAPE_EDGE, radius * 0.1))
    painter.setBrush(CAPE)
    painter.drawPath(cape)
    fold = QPainterPath(qt(point(0.15, 0.35)))
    fold.quadTo(qt(point(0.35, 1.3)), qt(point(0.93, 2.6)))
    painter.setPen(world_pen(CAPE_FOLD, radius * 0.18))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(fold)
    painter.restore()


def draw_nature_aura(painter: QPainter, hero: Actor, transforms: dict[str, BoneTransform]) -> None:
    """Three rising leaves and a faint glow; no particles, RNG, or gameplay effects."""
    if not hero.animated:
        return
    time = getattr(hero, "nature_time", 0.0)
    center = transforms[hero.layout.torso].start
    radius = hero.layout.head_radius
    draw_nature_magic(painter, center, time, radius)


def draw_nature_magic(
    painter: QPainter,
    center: Vec2,
    time: float,
    radius: float,
    *,
    x_spread: float = 1.0,
    y_spread: float = 1.0,
    leaves: int = 3,
    leaf_scale: float = 1.0,
    front: bool | None = None,
) -> None:
    """Share the same leaves and glow across forms, with independently sized orbits."""
    painter.save()
    if front is not True:
        painter.save()
        painter.translate(center.x, center.y)
        painter.scale(x_spread, y_spread)
        glow = QRadialGradient(0, 0, radius * 4.5)
        glow.setColorAt(0.0, QColor(132, 206, 94, 20))
        glow.setColorAt(0.45, QColor(132, 206, 94, 9))
        glow.setColorAt(1.0, QColor(132, 206, 94, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(qt(Vec2(0, 0)), radius * 4.5, radius * 4.5)
        painter.restore()
    for index in range(leaves):
        progress = (time / 3.8 + index / leaves) % 1.0
        fade = math.sin(math.pi * progress) ** 2
        swirl = time * 1.3 + index * math.tau / leaves
        if front is not None and (math.sin(swirl) >= 0) != front:
            continue
        position = center + Vec2(
            math.cos(swirl) * radius * (2.4 + 0.3 * math.sin(time + index)) * x_spread,
            radius * (2.0 - 7.0 * progress) * y_spread,
        )
        direction = Vec2.from_angle(-0.7 + 0.65 * math.sin(swirl))
        across = Vec2(-direction.y, direction.x)
        length = radius * 0.65 * leaf_scale
        start, tip = position - direction * length, position + direction * length
        leaf = QPainterPath(qt(start))
        leaf.quadTo(qt(position + across * length * 0.85), qt(tip))
        leaf.quadTo(qt(position - across * length * 0.85), qt(start))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(LEAF, 155 * fade))
        painter.drawPath(leaf)
        painter.setPen(world_pen(alpha(LEAF_LIGHT, 110 * fade), 0.22))
        painter.drawLine(qt(start), qt(tip))
    painter.restore()


def draw_natures_wrath_head(
    painter: QPainter, hero: Actor, transforms: dict[str, BoneTransform]
) -> None:
    draw_goblin_face(painter, hero, transforms)
    head = transforms[hero.layout.head]
    radius = hero.layout.head_radius
    up = Vec2.from_angle(head.angle)
    forward = Vec2(-up.y, up.x) * hero.facing
    crest = (
        (-0.85, 0.45),
        (-0.9, 1.22),
        (-0.55, 1.0),
        (-0.45, 1.72),
        (-0.15, 1.18),
        (0.05, 1.9),
        (0.25, 1.2),
        (0.6, 1.65),
        (0.65, 0.75),
        (0.85, 0.5),
        (0.25, 0.85),
        (-0.35, 0.85),
    )
    painter.setPen(world_pen(MOHAWK_EDGE, 0.8 * hero.layout.scale))
    painter.setBrush(MOHAWK)
    painter.drawPolygon(
        [qt(head.end + forward * (x * radius) + up * (y * radius)) for x, y in crest]
    )
