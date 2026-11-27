"""White-gold halo, sun glow, and a clearly divine ambient aura."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.heroes.hero_cleric.judgement import PRAYER_TIME
from dungeons_desktops.render.primitives import alpha, qt, world_pen

BODY_WIDTH = 4.8
GOLD = QColor(255, 205, 80)
PALE_GOLD = QColor(255, 238, 164)
WHITE = QColor(255, 253, 232)
SOUL = QColor(212, 239, 255)
SOUL_EDGE = QColor(116, 198, 255)


def draw_divine_judgements(painter: QPainter, heroes) -> None:
    """Draw the gathering light and every active column of sunlight."""
    painter.save()
    for hero in heroes:
        judgement = getattr(hero, "judgement", None)
        if judgement is None or not hero.animated:
            continue
        point = judgement.point
        ceiling = getattr(hero.world, "ceiling", None)
        top_y = 0.0 if ceiling is None else ceiling
        top = Vec2(point.x, top_y)
        pulse = 0.5 + 0.5 * math.sin(hero.divine_time * 15.0)

        if not judgement.active:
            gathered = clamp(judgement.age / PRAYER_TIME, 0.0, 1.0)
            painter.setPen(world_pen(alpha(GOLD, 35 + 75 * gathered), 1.0 + gathered))
            for offset in (-18.0, 0.0, 18.0):
                painter.drawLine(qt(top + Vec2(offset, 0)), qt(point))
            continue

        painter.setPen(world_pen(alpha(GOLD, 32 + 12 * pulse), 34.0 + 5.0 * pulse))
        painter.drawLine(qt(top), qt(point))
        painter.setPen(world_pen(alpha(PALE_GOLD, 105 + 25 * pulse), 19.0 + 3.0 * pulse))
        painter.drawLine(qt(top), qt(point))
        painter.setPen(world_pen(alpha(WHITE, 225), 7.0 + 1.5 * pulse))
        painter.drawLine(qt(top), qt(point))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(GOLD, 58 + 30 * pulse))
        painter.drawEllipse(qt(point + Vec2(0, 2)), 27.0 + 4.0 * pulse, 7.0 + pulse)
        painter.setBrush(alpha(WHITE, 190))
        painter.drawEllipse(qt(point), 8.0 + 2.0 * pulse, 3.0 + 0.5 * pulse)
        for index in range(8):
            direction = Vec2.from_angle(index * math.tau / 8 + hero.divine_time * 0.5)
            painter.setPen(world_pen(alpha(PALE_GOLD, 130), 1.2))
            painter.drawLine(qt(point + direction * 10.0), qt(point + direction * 24.0))
    painter.restore()


def draw_prayer_glow(painter: QPainter, actor, transforms) -> None:
    """A compact sun sigil makes a participating ally's prayer readable."""
    if actor.divine_prayer <= 0.0 or not actor.animated:
        return
    torso = transforms[actor.layout.torso]
    center = torso.start.lerp(torso.end, 0.65)
    strength = clamp(actor.divine_prayer / PRAYER_TIME, 0.0, 1.0)
    radius = (5.0 + math.sin(actor.divine_prayer * 18.0)) * actor.layout.scale
    painter.save()
    painter.setPen(world_pen(alpha(GOLD, 165 * strength), 1.25))
    painter.setBrush(alpha(WHITE, 100 * strength))
    painter.drawEllipse(qt(center), radius, radius)
    for index in range(4):
        direction = Vec2.from_angle(index * math.pi / 2)
        painter.drawLine(qt(center + direction * radius), qt(center + direction * radius * 1.8))
    painter.restore()


def draw_souls(painter: QPainter, hero) -> None:
    if not hero.animated:
        return
    painter.save()
    for soul in hero.souls:
        for index, (start, end) in enumerate(zip(soul.trail, soul.trail[1:], strict=False)):
            strength = (index + 1) / max(1, len(soul.trail))
            painter.setPen(world_pen(alpha(SOUL_EDGE, 90 * strength), 0.5 + strength))
            painter.drawLine(qt(start), qt(end))
        point = soul.point
        bob = 0.8 * math.sin(hero.divine_time * 5 + soul.angle)
        head = point + Vec2(0, -3.8 + bob)
        painter.setPen(world_pen(alpha(SOUL_EDGE, 185), 0.7))
        painter.setBrush(alpha(SOUL, 205))
        painter.drawEllipse(qt(head), 2.3, 2.3)
        body = QPainterPath(qt(point + Vec2(-2.4, -1.2 + bob)))
        body.quadTo(qt(point + Vec2(-3.0, 4.0)), qt(point + Vec2(-0.5, 8.0)))
        body.quadTo(qt(point + Vec2(0.6, 5.7)), qt(point + Vec2(2.6, 7.5)))
        body.quadTo(qt(point + Vec2(2.4, 2.0)), qt(point + Vec2(2.4, -1.2 + bob)))
        body.closeSubpath()
        painter.drawPath(body)
        painter.setPen(world_pen(alpha(WHITE, 165), 0.65))
        painter.drawLine(qt(point + Vec2(-1.8, 1.0)), qt(point + Vec2(-4.2, 3.0)))
        painter.drawLine(qt(point + Vec2(1.8, 1.0)), qt(point + Vec2(4.2, 3.0)))
    painter.restore()


def draw_divine_aura(painter: QPainter, hero, transforms) -> None:
    if not hero.animated:
        return
    center = transforms[hero.layout.torso].start - Vec2(0, hero.layout.head_radius * 0.2)
    radius = hero.layout.head_radius
    time = hero.divine_time
    pulse = 0.5 + 0.5 * math.sin(time * 2.4)
    painter.save()
    glow = QRadialGradient(qt(center), radius * 7.2)
    glow.setColorAt(0.0, alpha(WHITE, 34 + 12 * pulse))
    glow.setColorAt(0.42, alpha(GOLD, 20 + 8 * pulse))
    glow.setColorAt(1.0, alpha(GOLD, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(qt(center), radius * 7.2, radius * 7.2)

    feet = hero.contact()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(alpha(GOLD, 58 + 20 * pulse), 1.0))
    painter.drawEllipse(qt(feet - Vec2(0, 1)), radius * 4.5, radius * 0.75)
    painter.setPen(world_pen(alpha(WHITE, 48 + 15 * pulse), 0.45))
    painter.drawEllipse(qt(feet - Vec2(0, 1)), radius * 3.6, radius * 0.52)

    for index in range(6):
        progress = (time / 3.0 + index / 6) % 1.0
        phase = time * 1.15 + index * math.tau / 6
        fade = math.sin(math.pi * progress) ** 2
        point = center + Vec2(
            math.cos(phase) * radius * (2.5 + 0.4 * math.sin(phase * 2)),
            radius * (2.8 - 6.6 * progress),
        )
        mote_radius = radius * (0.11 + 0.07 * fade)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(WHITE, 210 * fade))
        painter.drawEllipse(qt(point), mote_radius, mote_radius)
        painter.setPen(world_pen(alpha(GOLD, 115 * fade), 0.55))
        painter.drawLine(qt(point + Vec2(0, radius * 0.4)), qt(point + Vec2(0, radius * 1.0)))
    painter.restore()


def draw_resurrection_flash(painter: QPainter, hero) -> None:
    if hero.resurrection_flash <= 0:
        return
    strength = hero.resurrection_flash / 0.75
    center = hero.center()
    radius = hero.layout.head_radius
    painter.save()
    glow = QRadialGradient(qt(center), radius * 8)
    glow.setColorAt(0, alpha(WHITE, 170 * strength))
    glow.setColorAt(0.35, alpha(GOLD, 85 * strength))
    glow.setColorAt(1, alpha(GOLD, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(qt(center), radius * 8, radius * 8)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for index in range(8):
        direction = Vec2.from_angle(index * math.tau / 8 + hero.divine_time * 0.2)
        painter.setPen(world_pen(alpha(WHITE, 150 * strength), 0.7))
        painter.drawLine(
            qt(center + direction * radius * 2.0),
            qt(center + direction * radius * (5.0 + 2.0 * (1 - strength))),
        )
    painter.restore()


def draw_staff_glow(painter: QPainter, hero, transforms) -> None:
    if not hero.animated:
        return
    center = hero.weapon.sun_center(transforms, hero.facing)
    radius = hero.layout.head_radius
    pulse = 0.5 + 0.5 * math.sin(hero.divine_time * 4.0)
    painter.save()
    glow = QRadialGradient(qt(center), radius * (2.5 + 0.2 * pulse))
    glow.setColorAt(0, alpha(WHITE, 115 + 45 * pulse))
    glow.setColorAt(0.25, alpha(GOLD, 75 + 30 * pulse))
    glow.setColorAt(1, alpha(GOLD, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(qt(center), radius * 2.7, radius * 2.7)
    painter.restore()


def draw_halo(painter: QPainter, hero, transforms) -> None:
    head = transforms[hero.layout.head]
    radius = hero.layout.head_radius
    up = Vec2.from_angle(head.angle)
    center = head.end + up * (radius + 4.5)
    rotation = math.degrees(up.angle() + math.pi / 2)
    pulse = 0.5 + 0.5 * math.sin(hero.divine_time * 3.0)
    painter.save()
    painter.translate(center.x, center.y)
    painter.rotate(rotation)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(alpha(GOLD, 65 + 35 * pulse), 5.2))
    painter.drawEllipse(qt(Vec2(0, 0)), radius * 1.35, radius * 0.38)
    painter.setPen(world_pen(GOLD, 1.45))
    painter.drawEllipse(qt(Vec2(0, 0)), radius * 1.35, radius * 0.38)
    painter.setPen(world_pen(WHITE, 0.55))
    painter.drawEllipse(qt(Vec2(0, 0)), radius * 1.12, radius * 0.28)
    painter.restore()
