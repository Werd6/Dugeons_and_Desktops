"""A faint aura boundary, golden ally halos, and three sweeping divine hammers."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.heroes.hero_paladin.aura import AURA_RADIUS
from dungeons_desktops.game.heroes.hero_paladin.smite import (
    HAMMER_COUNT,
    HAMMER_INTERVAL,
    SMITE_TIME,
)
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import alpha, qt, world_pen

GOLD = QColor(255, 214, 101)
LIGHT = QColor(255, 249, 212)


def draw_aura(painter: QPainter, hero) -> None:
    if not getattr(hero, "aura_active", False):
        return
    painter.save()
    painter.setOpacity(1.0)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(alpha(GOLD, 25 + 55 * hero.heal_flash), 0.7))
    painter.drawEllipse(qt(hero.center()), AURA_RADIUS, AURA_RADIUS)
    painter.restore()


def draw_halo(painter: QPainter, ally) -> None:
    if ally.protector is None:
        return
    radius = ally.layout.head_radius
    head = ally.transforms()[ally.layout.head].end
    lift = radius + 3.5
    if ally.variant in ("wizard", "hero_wizard"):
        lift = 23.0  # Sit above the full-size pointed hat, including Iggy's.
    center = head - Vec2(0, lift)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(alpha(GOLD, 65), 3.4))
    painter.drawEllipse(qt(center), radius * 1.1, radius * 0.35)
    painter.setPen(world_pen(GOLD, 1.1))
    painter.drawEllipse(qt(center), radius * 1.1, radius * 0.35)
    painter.setPen(world_pen(LIGHT, 0.45))
    painter.drawEllipse(qt(center), radius * 1.1, radius * 0.35)
    painter.restore()


def draw_paladin_effects(painter: QPainter, heroes) -> None:
    for hero in heroes:
        if hero.variant != "hero_paladin":
            continue
        _draw_hammer_throw(painter, hero)
        if hero.smite is None:
            continue
        smite = hero.smite
        painter.save()
        fade = clamp((SMITE_TIME - smite.age) / 0.25, 0, 1)
        for index in range(HAMMER_COUNT):
            hit_time = hero.weapon.hit_time + index * HAMMER_INTERVAL
            approach = smoothstep(clamp(smite.age / hit_time, 0, 1))
            angle = -math.pi / 2 + index * math.tau / HAMMER_COUNT
            reach = 30 - 24 * approach
            head = smite.point + Vec2.from_angle(angle, reach)
            direction = Vec2.from_angle(angle + math.pi * (0.2 + 0.8 * approach))
            across = direction.rotated(math.pi / 2)
            grip = head - direction * 12
            painter.setPen(world_pen(alpha(GOLD, 60 * fade), 5))
            painter.drawLine(qt(grip), qt(head))
            painter.setPen(world_pen(alpha(GOLD, 240 * fade), 1.8))
            painter.drawLine(qt(grip), qt(head))
            corners = [
                head + direction * y + across * x
                for x, y in ((-5, -2), (5, -2), (5, 2), (-5, 2))
            ]
            painter.setBrush(alpha(LIGHT, 240 * fade))
            painter.setPen(world_pen(alpha(GOLD, 250 * fade), 1))
            painter.drawPolygon([qt(point) for point in corners])
        if smite.confirmed:
            ring = 4 + 18 * clamp((smite.age - hero.weapon.hit_time) / 0.4, 0, 1)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(alpha(GOLD, 170 * fade), 1.3))
            painter.drawEllipse(qt(smite.point), ring, ring * 0.6)
        painter.restore()


def _draw_hammer_throw(painter: QPainter, hero) -> None:
    hammer = hero.hammer_throw
    if not hammer.flying:
        return
    painter.save()
    for index, (start, end) in enumerate(zip(hammer.trail, hammer.trail[1:], strict=False)):
        strength = (index + 1) / len(hammer.trail)
        painter.setPen(world_pen(alpha(GOLD, 145 * strength), 1 + 2 * strength))
        painter.drawLine(qt(start), qt(end))
    direction = Vec2.from_angle(hammer.angle)
    butt = hammer.point - direction * (hero.weapon.haft * 0.5)
    draw_strokes(painter, hero.weapon._hammer(butt, direction))
    painter.restore()
