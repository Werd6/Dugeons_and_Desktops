"""Orange fire and literal blue-and-yellow lightning for the hero druid."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.heroes.natures_wrath.spells import (
    ARC_TIME,
    BLAST_TIME,
    CAST_RELEASE,
    FIREBALL_RADIUS,
    ORB_RADIUS,
    Ability,
)
from dungeons_desktops.render.primitives import alpha, qt, world_pen

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman

FIRE = QColor(255, 112, 22)
FLAME = QColor(255, 190, 48)
CORE = QColor(255, 250, 206)
EMBER = QColor(232, 55, 12)
LIGHTNING_BLUE = QColor(56, 154, 255)
LIGHTNING_YELLOW = QColor(255, 238, 96)
LIGHTNING_CORE = QColor(255, 255, 222)


def _lightning(
    painter: QPainter, start: Vec2, end: Vec2, seed: int, age: float, strength: float = 1.0
) -> None:
    """Angular, forking bolts with a blue corona and hot yellow-white center."""
    offset = end - start
    distance = offset.length()
    if distance < 0.1:
        return
    side = Vec2(-offset.y, offset.x).normalized()
    rng = random.Random(seed + int(age * 35))  # Stable per frame; no gameplay RNG.
    segments = max(4, min(32, int(distance / 9)))
    jitter = min(8.0, distance * 0.16)
    points = [start]
    for index in range(1, segments):
        points.append(start.lerp(end, index / segments) + side * rng.uniform(-jitter, jitter))
    points.append(end)
    path = QPainterPath(qt(start))
    for point in points[1:]:
        path.lineTo(qt(point))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for color, width, opacity in (
        (LIGHTNING_BLUE, 8.0, 45),
        (LIGHTNING_BLUE, 3.8, 235),
        (LIGHTNING_YELLOW, 1.65, 255),
        (LIGHTNING_CORE, 0.55, 255),
    ):
        painter.setPen(world_pen(alpha(color, opacity * strength), width))
        painter.drawPath(path)
    for index in range(2, len(points) - 1, 4):
        base = points[index]
        tip = base + offset.normalized() * rng.uniform(5, 15)
        tip += side * rng.choice((-1, 1)) * min(20, distance * 0.14)
        fork = QPainterPath(qt(base))
        fork.lineTo(qt(base.lerp(tip, 0.45) + side * rng.uniform(-4, 4)))
        fork.lineTo(qt(tip))
        painter.setPen(world_pen(alpha(LIGHTNING_BLUE, 190 * strength), 1.6))
        painter.drawPath(fork)
        painter.setPen(world_pen(alpha(LIGHTNING_YELLOW, 200 * strength), 0.5))
        painter.drawPath(fork)


def _electric_sparks(painter: QPainter, point: Vec2, time: float, strength: float) -> None:
    _glow(painter, point, 12, LIGHTNING_BLUE, 100 * strength)
    for index in range(7):
        angle = index * math.tau / 7 + time * 5
        direction = Vec2.from_angle(angle)
        start = point + direction * 2
        end = point + direction * (6 + 4 * math.sin(time * 24 + index) ** 2)
        painter.setPen(world_pen(alpha(LIGHTNING_YELLOW, 220 * strength), 0.8))
        painter.drawLine(qt(start), qt(end))


def _glow(painter: QPainter, point: Vec2, radius: float, color: QColor, opacity: float) -> None:
    glow = QRadialGradient(qt(point), max(0.1, radius))
    glow.setColorAt(0, alpha(color, opacity))
    glow.setColorAt(0.45, alpha(color, opacity * 0.55))
    glow.setColorAt(1, alpha(color, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(qt(point), radius, radius)


def _fireball(painter: QPainter, point: Vec2, velocity: Vec2, age: float, radius: float) -> None:
    back = velocity.normalized() * -1 if velocity.length() > 1 else Vec2(0, -1)
    side = Vec2(-back.y, back.x)
    _glow(painter, point, radius * 3, FIRE, 140)
    for index in range(5):
        across = (index - 2) * radius * 0.35
        length = radius * (3.0 + 0.8 * math.sin(age * 22 + index * 1.7))
        base = point + side * across
        tip = base + back * length + side * (math.sin(age * 17 + index) * radius * 0.5)
        flame = QPainterPath(qt(base + side * radius * 0.45))
        flame.quadTo(qt(base + back * length * 0.6 + side * radius * 0.5), qt(tip))
        flame.quadTo(
            qt(base + back * length * 0.4 - side * radius * 0.3), qt(base - side * radius * 0.45)
        )
        painter.setBrush(alpha(FIRE if index % 2 else EMBER, 190))
        painter.drawPath(flame)
    painter.setBrush(FIRE)
    painter.drawEllipse(qt(point), radius, radius * 0.9)
    painter.setBrush(FLAME)
    painter.drawEllipse(qt(point), radius * 0.72, radius * 0.67)
    painter.setBrush(CORE)
    painter.drawEllipse(qt(point - back * radius * 0.15), radius * 0.38, radius * 0.38)
    for index in range(4):
        ember = point + back * (radius * (2.5 + index * 0.8))
        ember += side * (math.sin(age * 15 + index * 2.3) * radius * 1.2)
        painter.setBrush(alpha(FLAME, 150 - index * 25))
        painter.drawEllipse(qt(ember), 0.7, 0.7)


def draw_nature_spells(painter: QPainter, heroes: Iterable[Stickman]) -> None:
    """Draw above actors in both the preview and desktop overlay."""
    painter.save()
    for hero in heroes:
        if hero.variant != "hero_druid":
            continue
        spells = getattr(hero, "spells", None)
        if spells is None:
            continue
        if hero.animated and hero.casting is not None and not hero.cast_released:
            charge = clamp(hero.cast_time / CAST_RELEASE, 0, 1)
            if hero.casting is Ability.FIREBALL:
                _fireball(
                    painter,
                    hero.flame_point(),
                    Vec2(0, 0),
                    hero.nature_time,
                    ORB_RADIUS * (0.2 + 0.8 * smoothstep(charge)),
                )
            elif hero.casting is Ability.CHAIN_LIGHTNING:
                point = hero.flame_point()
                start = hero.transforms()[hero.layout.arms[1].bones[0]].start
                tip = point + Vec2(hero.facing * 4, -3)
                _lightning(painter, start, tip, 17, hero.nature_time, 0.35 + charge * 0.65)
                _electric_sparks(painter, point, hero.nature_time, charge)
            else:
                _glow(painter, hero.center(), 28 * charge + 6, FIRE, 150 * charge)
        for arc in spells.arcs:
            if not arc.struck:
                continue
            fade = 1 - smoothstep(clamp(arc.age / ARC_TIME, 0, 1))
            _lightning(painter, arc.start, arc.end, arc.seed, arc.age, fade)
            _electric_sparks(painter, arc.end, arc.age, fade)
        for ball in spells.fireballs:
            _fireball(painter, ball.position, ball.velocity, ball.age, ORB_RADIUS)
        for blast in spells.blasts:
            grow = smoothstep(clamp(blast.age / 0.2, 0, 1))
            fade = 1 - smoothstep(clamp((blast.age / BLAST_TIME - 0.2) / 0.8, 0, 1))
            radius = FIREBALL_RADIUS * (0.25 + 0.75 * grow)
            _glow(painter, blast.center, radius * 1.15, FIRE, 160 * fade)
            _glow(painter, blast.center, radius * 0.65, FLAME, 210 * fade)
            _glow(painter, blast.center, radius * 0.3, CORE, 240 * fade)
            for index in range(12):
                angle = index * math.tau / 12 + math.sin(index * 8.3) * 0.15
                direction = Vec2.from_angle(angle)
                side = Vec2(-direction.y, direction.x)
                tip = blast.center + direction * radius * (0.85 + 0.15 * math.sin(index * 3.7))
                base = blast.center + direction * radius * 0.35
                flame = QPainterPath(qt(base + side * radius * 0.09))
                flame.quadTo(qt(base.lerp(tip, 0.6) + side * radius * 0.1), qt(tip))
                flame.quadTo(qt(base.lerp(tip, 0.5)), qt(base - side * radius * 0.09))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(alpha(FIRE if index % 2 else FLAME, 160 * fade))
                painter.drawPath(flame)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(alpha(FLAME, 110 * fade), 1.5))
            painter.drawEllipse(qt(blast.center), radius, radius)
    painter.restore()
