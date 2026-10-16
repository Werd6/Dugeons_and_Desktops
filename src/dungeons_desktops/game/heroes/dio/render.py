"""Dio charge, mark, thrown-trident, and spectral-shield effects."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.dio.weapon import HeroTridentAndShield
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import alpha, qt, world_pen

HERO_SILVER = QColor(214, 226, 234)

def draw_dio_effects(
    painter: QPainter, heroes: Iterable[Stickman], outline: QColor | None = None
) -> None:
    """Hero effects that must remain visible above monsters and ordinary actors."""
    for hero in heroes:
        if hero.variant != "hero_fighter" or not hero.animated:
            continue
        weapon = hero.weapon
        if not isinstance(weapon, HeroTridentAndShield):
            continue
        phase = getattr(getattr(hero, "phase", None), "value", "")
        if phase == "throw_charge":
            charge = getattr(hero, "trident_charge", 0.0)
            center = weapon.trident_center(hero.transforms(), hero.facing)
            pulse = 1.0 + 0.12 * math.sin(charge * math.tau * 3.0)
            painter.setPen(world_pen(alpha(HERO_SILVER, int(80 + 100 * charge)), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(center), 7.0 * pulse, 7.0 * pulse)
        thrown = getattr(hero, "thrown_trident", None)
        if thrown is not None:
            draw_strokes(
                painter,
                weapon.trident_strokes(thrown.position, thrown.direction, 1.65),
            )
            painter.setPen(world_pen(alpha(HERO_SILVER, 120), 1.1))
            painter.drawLine(qt(thrown.position - thrown.direction * 28.0), qt(thrown.position))

        marked = getattr(hero, "marked", None)
        if marked is None and phase == "mark_cast":
            marked = getattr(hero, "target", None)
        point = hero.world.locate(marked) if marked is not None else None
        if point is not None:
            pulse = 1.0 + 0.12 * math.sin(getattr(hero, "mark_time", 0.0) * 10.0)
            radius = 7.0 * pulse
            center = point - Vec2(0.0, 16.0)
            painter.setPen(world_pen(alpha(HERO_SILVER, 220), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(center), radius, radius * 0.45)
            painter.drawLine(qt(center - Vec2(0.0, 5.0)), qt(center + Vec2(0.0, 5.0)))
            painter.drawLine(qt(center - Vec2(3.5, 0.0)), qt(center + Vec2(3.5, 0.0)))

        shield = getattr(hero, "spectral_shield", None)
        if shield is not None:
            _draw_spectral_shield(painter, shield.position, outline)

        flash = getattr(hero, "attack_flash", None)
        if flash is not None:
            direction = Vec2(float(hero.facing), 0.0)
            across = Vec2(0.0, 1.0)
            start = hero.center() + direction * 5.0 - across * 2.0
            tip = start + direction * (20.0 if flash == "shield" else 25.0)
            painter.setPen(world_pen(QColor(218, 234, 248, 75), 4.0))
            painter.drawLine(qt(start), qt(tip))
            painter.setPen(world_pen(QColor(246, 252, 255, 220), 1.2))
            painter.drawLine(qt(start), qt(tip))
            painter.drawLine(qt(tip - direction * 5.0 + across * 3.0), qt(tip))
            painter.drawLine(qt(tip - direction * 5.0 - across * 3.0), qt(tip))


def _draw_spectral_shield(
    painter: QPainter, center: Vec2, outline: QColor | None = None
) -> None:
    shape = (
        center + Vec2(-5.2, -6.2),
        center + Vec2(5.2, -6.2),
        center + Vec2(4.8, 1.0),
        center + Vec2(0.0, 7.4),
        center + Vec2(-4.8, 1.0),
    )
    edge = outline or QColor(96, 126, 146, 190)
    painter.setPen(world_pen(edge, 1.4))
    painter.setBrush(QColor(210, 232, 248, 105))
    painter.drawPolygon([qt(point) for point in shape])
    painter.setPen(world_pen(QColor(250, 255, 255, 210), 1.0))
    painter.drawPolygon(
        [
            qt(center + Vec2(0.0, -2.4)),
            qt(center + Vec2(1.4, -0.2)),
            qt(center + Vec2(0.0, 2.2)),
            qt(center + Vec2(-1.4, -0.2)),
        ]
    )


