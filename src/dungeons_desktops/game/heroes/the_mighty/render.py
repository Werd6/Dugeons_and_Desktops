"""Stone, ground fractures, and the red-eyed, steaming rage of The Mighty."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.the_mighty.combat import IMPACT_TIME, Attack
from dungeons_desktops.render.primitives import alpha, qt, world_pen

RAGE = QColor(204, 55, 36)
STEAM = QColor(236, 236, 242)
STONE = QColor(120, 111, 98)
STONE_LIGHT = QColor(185, 171, 146)
STONE_EDGE = QColor(65, 58, 52)


def draw_rock(painter: QPainter, center: Vec2, radius: float, spin: float = 0) -> None:
    points = [
        center + Vec2.from_angle(spin + i * math.tau / 9, radius * (1 if i % 2 else 0.85))
        for i in range(9)
    ]
    painter.setPen(world_pen(STONE_EDGE, max(0.7, radius * 0.1)))
    painter.setBrush(STONE)
    painter.drawPolygon([qt(p) for p in points])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(STONE_LIGHT)
    painter.drawPolygon(
        [qt(points[4]), qt(points[5]), qt(points[6]), qt(center + Vec2(-0.2, -0.25) * radius)]
    )


def draw_mighty_details(painter: QPainter, hero, transforms, hidden=()) -> None:
    if hero.weapon.busy and hero.weapon.action is Attack.BOULDER and not hero._struck:
        hand_name = hero.weapon.hand_chain.bones[-1]
        if hand_name not in hidden:
            hand = transforms[hand_name].end
            radius = 8 * hero.size_multiplier
            draw_rock(painter, hand - Vec2(0, radius * 0.65), radius, -0.3)
    if hero.fury < 0.02 or not hero.animated or hero.layout.head in hidden:
        return
    radius = hero.layout.head_radius
    head = transforms[hero.layout.head].end
    eye = head + Vec2(hero.facing * radius * 0.4, -radius * 0.12)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(alpha(QColor(255, 75, 30), 90 * hero.fury))
    painter.drawEllipse(qt(eye), radius * 0.6, radius * 0.42)
    painter.setBrush(alpha(QColor(255, 100, 38), 255 * hero.fury))
    painter.drawEllipse(qt(eye), radius * 0.3, radius * 0.17)
    nose = head + Vec2(hero.facing * radius * 0.9, radius * 0.3)
    for index in range(3):
        age = (hero.time * 1.6 + index / 3) % 1
        drift = Vec2(hero.facing * (0.25 + age), 0.2 - age * 0.7) * radius
        puff = radius * (0.15 + age * 0.35)
        painter.setBrush(alpha(STEAM, 170 * hero.fury * (1 - age)))
        painter.drawEllipse(qt(nose + drift), puff, puff * 0.8)


def draw_mighty_effects(painter: QPainter, heroes) -> None:
    for hero in heroes:
        if hero.variant != "hero_barbarian":
            continue
        for rock in hero.combat.boulders:
            draw_rock(painter, rock.position, 8 * rock.size, rock.age * 6)
        for impact in hero.combat.impacts:
            age = impact.age / IMPACT_TIME
            radius = impact.radius * min(1, age * 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(alpha(STONE_LIGHT, 220 * (1 - age)), 2 * (1 - age) + 0.5))
            painter.drawEllipse(
                qt(impact.center), radius, radius * (0.22 if impact.ground else 0.6)
            )
            for index in range(9):
                angle = index * math.tau / 9
                direction = Vec2(math.cos(angle), math.sin(angle) * 0.25)
                start = impact.center + direction * (radius * 0.2)
                bend = impact.center + direction * (radius * 0.55) + Vec2(3, -2)
                end = impact.center + direction * radius
                painter.drawPolyline([qt(start), qt(bend), qt(end)])
                debris = impact.center + Vec2(
                    math.cos(angle) * radius * age, -math.sin(math.pi * age) * (12 + index * 2)
                )
                painter.setBrush(alpha(STONE, 220 * (1 - age)))
                painter.drawEllipse(qt(debris), 2.3, 1.6)
                painter.setBrush(Qt.BrushStyle.NoBrush)
