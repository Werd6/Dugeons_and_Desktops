"""A mouth bandana and a flowing cape, drawn directly from the rogue's pose."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.heroes.the_slayer.assassinate import Phase
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import alpha, qt, world_pen
from dungeons_desktops.rig.skeleton import BoneTransform

BODY = QColor(92, 97, 106)
BODY_FAR = QColor(60, 64, 72)
BODY_WIDTH = 5.5
CAPE = QColor(77, 30, 46)
CAPE_EDGE = QColor(133, 55, 67)
CAPE_FOLD = QColor(104, 38, 55)
BANDANA = QColor(170, 53, 63)
BANDANA_EDGE = QColor(91, 29, 42)
BANDANA_FOLD = QColor(220, 91, 91)
SHADOW = QColor(116, 102, 155)
SHADOW_FAR = QColor(62, 53, 87)
SHADOW_DARK = QColor(36, 29, 53)


def draw_slayer_effects(painter: QPainter, heroes) -> None:
    """Draw after all defenders, so embedded blades and spins stay visible on a dragon."""
    for hero in heroes:
        if hero.variant == "hero_rogue" and not getattr(hero, "is_shadow_clone", False):
            draw_assassinate(painter, hero)


def draw_assassinate(painter: QPainter, hero: Actor, outline: QColor | None = None) -> bool:
    """Draw the flying/embedded dagger, or replace the hero with a whirling silhouette."""
    ability = hero.assassinate
    if not hero.animated:
        return False
    painter.save()
    for dagger in ability.daggers:
        _draw_thrown_dagger(painter, hero, dagger.point, dagger.direction, trail=True)
    if ability.phase in (Phase.FLIGHT, Phase.EMBEDDED):
        _draw_thrown_dagger(
            painter, hero, ability.point, ability.direction, trail=ability.phase is Phase.FLIGHT,
        )
    if ability.flash > 0:
        for center in (ability.departure, ability.point):
            if center is None:
                continue
            size = 5 + 15 * (1 - ability.flash / 0.3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(alpha(BANDANA, 200 * ability.flash / 0.3), 2.0))
            painter.drawEllipse(qt(center), size, size * 0.7)
    if not ability.spinning:
        painter.restore()
        return False
    center = ability.point
    radius = hero.layout.head_radius
    angle = ability.age * math.tau * 4
    painter.setPen(world_pen(outline or BODY_FAR, 1.0))
    painter.setBrush(QColor(38, 36, 47, 220))
    painter.drawEllipse(qt(center), radius * 1.4, radius * 1.8)
    for index in range(3):
        phase = angle + index * math.tau / 3
        path = QPainterPath()
        for step in range(13):
            t = phase + step / 12 * math.pi * 1.25
            reach = radius * (1.2 + step / 12 * 2.2)
            point = center + Vec2(math.cos(t) * reach, math.sin(t) * reach * 0.55)
            if step == 0:
                path.moveTo(qt(point))
            else:
                path.lineTo(qt(point))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(world_pen(alpha(CAPE_EDGE, 180), radius * 0.6))
        painter.drawPath(path)
        painter.setPen(world_pen(QColor(221, 229, 241, 205), radius * 0.16))
        painter.drawPath(path)
    for phase in (angle, angle + math.pi):
        grip = center + Vec2(math.cos(phase) * radius * 1.8, math.sin(phase) * radius)
        direction = Vec2.from_angle(phase + math.pi / 2)
        draw_strokes(painter, hero.weapon._dagger(grip, direction))
    painter.restore()
    return True


def _draw_thrown_dagger(
    painter: QPainter, hero: Actor, point: Vec2, direction: Vec2, *, trail: bool,
) -> None:
    grip = point - direction * (hero.weapon.blade * 0.7)
    if trail:
        painter.setPen(world_pen(QColor(185, 197, 220, 110), 1.2))
        painter.drawLine(qt(grip - direction * 16), qt(grip))
    draw_strokes(painter, hero.weapon._dagger(grip, direction))


def draw_slayer_shadow(
    painter: QPainter, hero: Actor, transforms: dict[str, BoneTransform]
) -> None:
    """Three drifting shadow wisps; no spawned particles or cached ghost bodies."""
    if not (getattr(hero, "stealthed", False) or getattr(hero, "is_shadow_clone", False)):
        return
    center = transforms[hero.layout.torso].start
    radius = hero.layout.head_radius
    time = hero.cape_time
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for index in range(3):
        phase = time * 1.8 + index * math.tau / 3
        y = center.y + radius * (0.9 - index * 0.8)
        x = center.x + math.sin(phase) * radius * 0.6
        wisp = QPainterPath(qt(Vec2(x - radius * 1.5, y)))
        wisp.cubicTo(
            qt(Vec2(x - radius * 0.5, y - radius * 0.65)),
            qt(Vec2(x + radius * 0.7, y + radius * 0.6)),
            qt(Vec2(x + radius * 1.5, y - radius * 0.2)),
        )
        painter.setPen(world_pen(QColor(72, 61, 102, 155), radius * 0.65))
        painter.drawPath(wisp)
        painter.setPen(world_pen(QColor(119, 109, 151, 165), radius * 0.13))
        painter.drawPath(wisp)
    painter.restore()


def draw_slayer_cape(
    painter: QPainter, hero: Actor, transforms: dict[str, BoneTransform]
) -> None:
    torso = transforms[hero.layout.torso]
    down = (torso.start - torso.end).normalized()
    back = Vec2(-down.y, down.x) * hero.facing
    radius = hero.layout.head_radius
    pace = min(1.0, hero.velocity.length() / 75.0) if hero.animated else 0.0
    flutter = (
        math.sin(getattr(hero, "cape_time", 0.0) * 6.0) * (0.1 + 0.2 * pace)
        if hero.animated else 0.0
    )
    shoulder = torso.end + back * (0.2 * radius)

    def at(trail: float, drop: float) -> Vec2:
        trailing = (2.3 * pace + flutter) * (drop / 3.0) ** 2
        return shoulder + back * ((trail + trailing) * radius) + down * (
            drop * (1 - pace * 0.23) * radius
        )

    cape = QPainterPath(qt(shoulder))
    cape.cubicTo(qt(at(0.85, 0.15)), qt(at(0.65, 1.8)), qt(at(1.7, 2.65)))
    cape.lineTo(qt(at(0.9, 2.55)))
    cape.lineTo(qt(at(0.6, 3.05)))
    cape.lineTo(qt(at(-0.15, 2.6)))
    cape.quadTo(qt(at(-0.25, 1.25)), qt(shoulder))
    cape.closeSubpath()
    shadow = getattr(hero, "is_shadow_clone", False)
    painter.save()
    painter.setPen(world_pen(SHADOW if shadow else CAPE_EDGE, radius * 0.1))
    painter.setBrush(SHADOW_DARK if shadow else CAPE)
    painter.drawPath(cape)
    fold = QPainterPath(qt(at(0.15, 0.3)))
    fold.quadTo(qt(at(0.1, 1.5)), qt(at(0.6, 3.05)))
    painter.setPen(world_pen(SHADOW_FAR if shadow else CAPE_FOLD, radius * 0.18))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(fold)
    painter.restore()


def draw_slayer_bandana(
    painter: QPainter, hero: Actor, transforms: dict[str, BoneTransform]
) -> None:
    head = transforms[hero.layout.head]
    up = Vec2.from_angle(head.angle)
    forward = Vec2(-up.y, up.x) * hero.facing
    radius = hero.layout.head_radius

    def at(front: float, drop: float) -> Vec2:
        return head.end + (forward * front - up * drop) * radius

    shadow = getattr(hero, "is_shadow_clone", False)
    painter.save()
    painter.setPen(world_pen(SHADOW_DARK if shadow else BANDANA_EDGE, radius * 0.1))
    painter.setBrush(SHADOW_FAR if shadow else BANDANA)
    tails = QPainterPath(qt(at(-0.85, 0.2)))
    for x, y in ((-1.9, 0.3), (-1.55, 0.58), (-2.0, 0.92), (-1.2, 0.78)):
        tails.lineTo(qt(at(x, y)))
    tails.closeSubpath()
    painter.drawPath(tails)
    mask = QPainterPath(qt(at(-0.96, 0.05)))
    mask.quadTo(qt(at(0.15, 0.2)), qt(at(1.01, -0.08)))
    mask.quadTo(qt(at(1.05, 0.65)), qt(at(0.2, 1.08)))
    mask.quadTo(qt(at(-0.85, 0.85)), qt(at(-0.96, 0.05)))
    mask.closeSubpath()
    painter.drawPath(mask)
    painter.setPen(world_pen(SHADOW if shadow else BANDANA_FOLD, radius * 0.1))
    painter.drawLine(qt(at(-0.5, 0.35)), qt(at(0.65, 0.25)))
    painter.restore()
