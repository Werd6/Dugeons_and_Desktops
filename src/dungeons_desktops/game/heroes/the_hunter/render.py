"""Cowboy gear, gun tracers, and a brief fan-shaped shotgun blast."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainterPath, QRadialGradient

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.the_hunter.combat import (
    SHOTGUN_BLAST_TIME,
    SHOTGUN_HALF_ANGLE,
    SHOTGUN_RANGE,
    TRACER_TIME,
    Gun,
)
from dungeons_desktops.game.heroes.the_hunter.weapon import shotgun_strokes
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import alpha, qt, world_pen
from dungeons_desktops.rig.equipment import Stroke

BODY_WIDTH = 4.6
HAT = QColor(142, 94, 55)
HAT_EDGE = QColor(76, 46, 27)
HAT_BAND = QColor(82, 50, 30)
LEATHER = QColor(117, 73, 40)
LEATHER_EDGE = QColor(63, 43, 30)


def draw_hat(painter, actor, transforms) -> None:
    head = transforms[actor.layout.head]
    up = Vec2.from_angle(head.angle)
    forward = Vec2(-up.y, up.x) * actor.facing
    r = actor.layout.head_radius

    def at(x, y):
        return qt(head.end + (forward * x + up * y) * r)

    crown = QPainterPath(at(-1.0, 0.65))
    crown.lineTo(at(-0.85, 1.8))
    crown.quadTo(at(-0.55, 2.05), at(-0.12, 1.8))
    crown.quadTo(at(0.22, 1.65), at(0.6, 1.93))
    crown.quadTo(at(0.9, 1.9), at(0.96, 1.53))
    crown.lineTo(at(1.05, 0.65))
    crown.closeSubpath()
    painter.setPen(world_pen(HAT_EDGE, 0.65))
    painter.setBrush(HAT)
    painter.drawPath(crown)
    painter.setPen(world_pen(HAT_BAND, r * 0.26))
    painter.drawLine(at(-0.95, 0.95), at(1, 0.95))
    brim = QPainterPath(at(-1.9, 1.05))
    brim.quadTo(at(-1.65, 0.35), at(-0.9, 0.6))
    brim.quadTo(at(0.2, 0.45), at(1.35, 0.56))
    brim.quadTo(at(1.85, 0.58), at(2.0, 0.95))
    brim.quadTo(at(1.5, 0.76), at(0.8, 0.8))
    brim.lineTo(at(-1.05, 0.85))
    brim.closeSubpath()
    painter.setPen(world_pen(HAT_EDGE, 0.55))
    painter.setBrush(HAT)
    painter.drawPath(brim)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def draw_back(painter, actor, transforms) -> None:
    s, facing = actor.layout.scale, actor.facing
    torso = transforms[actor.layout.torso]
    up = (torso.end - torso.start).normalized()
    direction = up.rotated(-facing * 0.32)
    grip = torso.start - Vec2(-up.y, up.x) * facing * 5 * s
    if actor.weapon.hanging:
        direction = direction * -1

    if actor.weapon.gun is not Gun.SHOTGUN:
        draw_strokes(painter, shotgun_strokes(grip, direction, facing, s))
    if actor.weapon.gun is not Gun.SNIPER:
        draw_strokes(painter, actor.weapon.slung_sniper(transforms, facing))
    draw_pistol(painter, actor, transforms, far=True)


def draw_pistol(painter, actor, transforms, far=False) -> None:
    s, facing = actor.layout.scale, actor.facing
    pelvis = transforms[actor.layout.pelvis]
    up = (pelvis.end - pelvis.start).normalized()
    right = Vec2(-up.y, up.x) * facing
    origin = pelvis.start + right * ((-4.5 if far else 5.0) * s) + up * (1.0 * s)

    def at(x, y):
        return origin + (right * x - up * y) * s

    painter.setPen(world_pen(LEATHER_EDGE, 0.7 * s))
    painter.setBrush(LEATHER.darker(125) if far else LEATHER)
    painter.drawPolygon([qt(at(x, y)) for x, y in ((-2, 1), (2, 1), (1.5, 9), (-1.3, 8))])
    if actor.weapon.gun is not Gun.PISTOLS or not actor.weapon_held:
        draw_strokes(painter, [
            Stroke(at(0, -0.8), at(0, 4.0), 1.7 * s, "metal"),
            Stroke(at(-1, 0), at(1, 0), 2.8 * s, "gunmetal"),
            Stroke(at(-0.5, -0.4), at(-3.3, -2.6), 2.2 * s, "wood"),
            Stroke(at(-1.5, -1.5), at(-3.5, -1.5), 0.8 * s, "metal"),
        ])
    painter.setBrush(Qt.BrushStyle.NoBrush)


def draw_shot(painter, actor) -> None:
    blast = actor.shotgun_blast
    if blast is not None:
        fade = 1 - blast.age / SHOTGUN_BLAST_TIME
        path = QPainterPath(qt(blast.origin))
        for index in range(17):
            angle = SHOTGUN_HALF_ANGLE * (index / 8 - 1)
            path.lineTo(qt(blast.origin + blast.direction.rotated(angle) * SHOTGUN_RANGE))
        path.closeSubpath()
        gradient = QRadialGradient(qt(blast.origin), SHOTGUN_RANGE)
        gradient.setColorAt(0, QColor(255, 246, 199, round(190 * fade)))
        gradient.setColorAt(0.45, QColor(255, 186, 83, round(70 * fade)))
        gradient.setColorAt(1, QColor(245, 145, 49, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(world_pen(QColor(255, 218, 140, round(190 * fade)), 0.6))
        for index in range(9):
            direction = blast.direction.rotated(SHOTGUN_HALF_ANGLE * (index / 4 - 1))
            distance = SHOTGUN_RANGE * min(1, 0.42 + blast.age / SHOTGUN_BLAST_TIME)
            distance *= 0.85 + 0.15 * math.cos(index * 2.4)
            painter.drawLine(qt(blast.origin + direction * (distance * 0.55)),
                             qt(blast.origin + direction * distance))
    for tracer in actor.tracers:
        color = QColor(255, 199, 110) if tracer.gun is Gun.SHOTGUN else QColor(255, 241, 192)
        width = 1.3 if tracer.gun is Gun.SNIPER else 0.7
        painter.setPen(world_pen(alpha(color, 230 * (1 - tracer.age / TRACER_TIME)), width))
        painter.drawLine(qt(tracer.start), qt(tracer.end))
