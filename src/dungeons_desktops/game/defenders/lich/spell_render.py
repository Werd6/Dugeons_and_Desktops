"""The lich's spells: fireball bursts and scorches, the power word's rune and the soul
it pulls out, homing magic missiles, chain lightning, and black tentacles.

`draw_scorches` goes under the actors, `draw_necromancy` over them.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.defenders.lich.spells import (
    ARC_TIME,
    BLAST_TIME,
    FIREBALL_RADIUS,
    SCORCH_TIME,
    SMITE_DROP,
    SMITE_FADE,
    SMITE_HANG,
    SMITE_LINGER,
    WISP_TIME,
    WORD_DELAY,
    WORD_TIME,
    Arc,
    Blast,
    Dart,
    Fireball,
    Necromancy,
    Smite,
    Tentacle,
    Tentacles,
    Wisp,
    Word,
)
from dungeons_desktops.game.defenders.minotaur.render import _alpha, _pen, _qt, _smooth, _taper

GLOW = QColor(90, 255, 140)
GOLD = QColor(255, 206, 84)
GOLD_DEEP = QColor(206, 140, 36)
HOLY = QColor(255, 250, 226)
CORE = QColor(236, 255, 220)
EMBER = QColor(255, 150, 40)
FIRE_CORE = QColor(255, 236, 150)
SCORCH = QColor(20, 16, 14)
RUNE = QColor(22, 8, 30)
RUNE_EDGE = QColor(150, 255, 150)
SOUL = QColor(196, 255, 214)
MISSILE = QColor(186, 120, 255)
BOLT = QColor(170, 255, 225)
TENTACLE = QColor(12, 10, 16)
TENTACLE_SHEEN = QColor(80, 52, 104)
POOL = QColor(18, 6, 26)
TENTACLE_RIM = QColor(128, 84, 176)
SOCKET_DARK = QColor(20, 40, 30)


def _ease(t: float) -> float:
    return smoothstep(clamp(t, 0.0, 1.0))


def _glow(painter: QPainter, center: Vec2, radius: float, inner: QColor, outer: QColor) -> None:
    gradient = QRadialGradient(_qt(center), radius)
    gradient.setColorAt(0.0, inner)
    gradient.setColorAt(1.0, _alpha(outer, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(_qt(center), radius, radius)


# ----- under the actors --------------------------------------------------------------


def draw_scorches(painter: QPainter, necromancy: Necromancy) -> None:
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for scorch in necromancy.scorches:
        fade = 1.0 - _ease((scorch.age - SCORCH_TIME * 0.6) / (SCORCH_TIME * 0.4))
        p = scorch.point
        painter.setBrush(_alpha(SCORCH, 170 * fade))
        painter.drawEllipse(_qt(p + Vec2(0.0, -1.0)), 46.0, 4.0)
        painter.setBrush(_alpha(SCORCH, 120 * fade))
        painter.drawEllipse(_qt(p + Vec2(0.0, -1.5)), 30.0, 6.0)
        embers = random.Random(int(p.x * 7 + p.y))
        for _ in range(6):
            x = embers.uniform(-38.0, 38.0)
            flicker = 0.5 + 0.5 * math.sin(scorch.age * 9.0 + x)
            color = GLOW if embers.random() < 0.5 else EMBER
            painter.setBrush(_alpha(color, 200 * fade * flicker))
            painter.drawEllipse(_qt(p + Vec2(x, -1.5)), 1.1, 0.8)
    painter.restore()


# ----- over the actors --------------------------------------------------------------


def draw_necromancy(painter: QPainter, necromancy: Necromancy) -> None:
    painter.save()
    for patch in necromancy.tentacles:
        _tentacles(painter, patch)
    for word in necromancy.words:
        _word(painter, word)
    for wisp in necromancy.wisps:
        _wisp(painter, wisp)
    for ball in necromancy.fireballs:
        _fireball(painter, ball)
    for blast in necromancy.blasts:
        _blast(painter, blast)
    for dart in necromancy.darts:
        _dart(painter, dart)
    for arc in necromancy.arcs:
        _arc(painter, arc)
    for smite in necromancy.smites:
        _smite(painter, smite)
    painter.restore()


def _fireball(painter: QPainter, ball: Fireball) -> None:
    back = ball.velocity.normalized() * -1.0
    for i in range(1, 6):
        spark = ball.position + back * (i * 3.2) + Vec2(math.sin(ball.age * 30 + i) * 0.8, 0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_alpha(GLOW if i % 2 else EMBER, 180 - 30 * i))
        painter.drawEllipse(_qt(spark), 2.2 - 0.3 * i, 2.2 - 0.3 * i)
    _glow(painter, ball.position, 9.0, _alpha(GLOW, 150), GLOW)
    _glow(painter, ball.position, 4.5, FIRE_CORE, EMBER)
    painter.setBrush(CORE)
    painter.drawEllipse(_qt(ball.position), 1.6, 1.6)


def _blast(painter: QPainter, blast: Blast) -> None:
    t = blast.age / BLAST_TIME
    grow = _ease(blast.age / 0.2)
    fade = 1.0 - _ease((t - 0.25) / 0.75)
    radius = FIREBALL_RADIUS * (0.35 + 0.65 * grow)
    center = blast.center
    _glow(painter, center, radius * 1.15, _alpha(GLOW, 150 * fade), GLOW)
    _glow(painter, center, radius * 0.85, _alpha(EMBER, 220 * fade), EMBER)
    _glow(painter, center, radius * 0.45 * (1.0 - 0.5 * t), _alpha(FIRE_CORE, 255 * fade), EMBER)
    tongues = random.Random(int(center.x * 13 + center.y))
    painter.setPen(Qt.PenStyle.NoPen)
    for _ in range(11):
        angle = tongues.uniform(0.0, 2 * math.pi)
        length = radius * tongues.uniform(0.7, 1.05)
        tip = center + Vec2.from_angle(angle, length)
        base = center + Vec2.from_angle(angle, length * 0.35)
        side = Vec2.from_angle(angle + math.pi / 2, length * 0.13)
        path = QPainterPath(_qt(base + side))
        path.quadTo(_qt(center + Vec2.from_angle(angle, length * 0.75) + side * 0.6), _qt(tip))
        path.quadTo(
            _qt(center + Vec2.from_angle(angle, length * 0.75) - side * 0.6), _qt(base - side)
        )
        painter.setBrush(_alpha(EMBER if tongues.random() < 0.6 else GLOW, 190 * fade))
        painter.drawPath(path)
    ring = FIREBALL_RADIUS * _ease(blast.age / 0.35)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(_alpha(GLOW, 160 * (1.0 - _ease(blast.age / 0.4))), 2.0))
    painter.drawEllipse(_qt(center), ring, ring)


def _head(word_target) -> Vec2:
    return word_target.transforms()[word_target.layout.head].end


def _word(painter: QPainter, word: Word) -> None:
    t = word.age
    appear = _ease(t / 0.18)
    fade = 1.0 - _ease((t - WORD_DELAY - 0.1) / (WORD_TIME - WORD_DELAY - 0.1))
    if fade <= 0.0:
        return
    center = _head(word.target) + Vec2(0.0, -20.0 - 4.0 * appear)
    size = 9.0 * (0.4 + 0.6 * appear)
    if t >= WORD_DELAY:
        flash = 1.0 - _ease((t - WORD_DELAY) / 0.25)
        _glow(painter, center, 26.0, _alpha(CORE, 230 * flash), GLOW)
        size *= 1.0 + 0.4 * _ease((t - WORD_DELAY) / 0.3)
    _glow(painter, center, size * 2.2, _alpha(GLOW, 110 * fade), GLOW)
    painter.setPen(_pen(_alpha(RUNE_EDGE, 230 * fade), 1.2))
    painter.setBrush(_alpha(RUNE, 235 * fade))
    painter.drawEllipse(_qt(center), size, size)
    spin = t * 1.5
    glyph = [
        Vec2.from_angle(spin + k * 2 * math.pi / 3 - math.pi / 2, size * 0.7) for k in range(3)
    ]
    painter.setPen(_pen(_alpha(RUNE_EDGE, 255 * fade), 1.1))
    path = QPainterPath(_qt(center + glyph[0]))
    for k in (1, 2, 0):
        path.lineTo(_qt(center + glyph[k]))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.drawLine(_qt(center + Vec2(0.0, -size * 0.7)), _qt(center + Vec2(0.0, size * 0.75)))
    for k in range(3):
        tick = center + glyph[k] * 1.25
        painter.drawLine(_qt(tick), _qt(center + glyph[k] * 1.5))


def _wisp(painter: QPainter, wisp: Wisp) -> None:
    t = _ease(wisp.age / WISP_TIME)
    lift = Vec2(0.0, -40.0)
    a, b = wisp.start, wisp.end

    def at(s: float) -> Vec2:
        return a * ((1 - s) ** 2) + (a.lerp(b, 0.5) + lift) * (2 * (1 - s) * s) + b * (s * s)

    fade = 1.0 - _ease((wisp.age / WISP_TIME - 0.75) / 0.25)
    for i in range(6):
        s = max(0.0, t - i * 0.04)
        p = at(s)
        _glow(painter, p, 6.0 - i * 0.7, _alpha(SOUL, (200 - 28 * i) * fade), GLOW)
    head = at(t)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_alpha(SOCKET_DARK, 200 * fade))
    painter.drawEllipse(_qt(head + Vec2(-1.2, -0.6)), 0.7, 0.9)
    painter.drawEllipse(_qt(head + Vec2(1.2, -0.6)), 0.7, 0.9)
    painter.drawEllipse(_qt(head + Vec2(0.0, 1.4)), 0.8, 1.1)


def _dart(painter: QPainter, dart: Dart) -> None:
    if dart.delay > 0.0:
        return
    points = [*dart.trail, dart.position]
    if len(points) >= 2:
        for i, (p, q) in enumerate(zip(points, points[1:], strict=False)):
            share = (i + 1) / (len(points) - 1)
            painter.setPen(_pen(_alpha(MISSILE, 150 * share), 3.2 * share))
            painter.drawLine(_qt(p), _qt(q))
            painter.setPen(_pen(_alpha(GLOW, 200 * share), 1.0 * share))
            painter.drawLine(_qt(p), _qt(q))
    _glow(painter, dart.position, 5.5, _alpha(MISSILE, 200), MISSILE)
    ahead = dart.velocity.normalized()
    side = Vec2(-ahead.y, ahead.x)
    tip = dart.position + ahead * 3.5
    head = [tip, dart.position - ahead * 1.5 + side * 1.8, dart.position - ahead * 1.5 - side * 1.8]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(CORE)
    painter.drawPolygon([_qt(p) for p in head])


def _arc(painter: QPainter, arc: Arc) -> None:
    if not arc.struck:
        return
    fade = 1.0 - _ease(arc.age / ARC_TIME)
    flicker = int(arc.age * 30)
    jag = random.Random(arc.seed * 31 + flicker)
    a, b = arc.start, arc.end
    span = b - a
    length = span.length()
    if length < 1.0:
        return
    side = Vec2(-span.y, span.x) * (1.0 / length)
    steps = max(3, int(length / 12))
    points = [a]
    for i in range(1, steps):
        wobble = jag.uniform(-1.0, 1.0) * min(10.0, length * 0.08)
        points.append(a + span * (i / steps) + side * wobble)
    points.append(b)
    path = QPainterPath(_qt(points[0]))
    for p in points[1:]:
        path.lineTo(_qt(p))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(_alpha(GLOW, 110 * fade), 5.0))
    painter.drawPath(path)
    painter.setPen(_pen(_alpha(BOLT, 230 * fade), 2.0))
    painter.drawPath(path)
    painter.setPen(_pen(_alpha(CORE, 255 * fade), 0.9))
    painter.drawPath(path)
    _glow(painter, b, 12.0, _alpha(CORE, 200 * fade), BOLT)
    for _ in range(3):
        spark = b + Vec2(jag.uniform(-9, 9), jag.uniform(-12, 6))
        painter.setPen(_pen(_alpha(BOLT, 220 * fade), 0.8))
        painter.drawLine(_qt(b), _qt(spark))


def _tentacles(painter: QPainter, spell: Tentacles) -> None:
    strength = spell.strength
    if strength <= 0.0:
        return
    painter.setPen(Qt.PenStyle.NoPen)
    for arm in spell.arms:
        side = Vec2(-arm.normal.y, arm.normal.x)
        painter.setBrush(_alpha(POOL, 200 * strength))
        blot = arm.base + arm.normal * 0.5
        painter.drawPolygon(
            [_qt(blot + side * 7.0), _qt(blot + arm.normal * 2.5), _qt(blot - side * 7.0)]
        )
    for arm in spell.arms:
        _arm(painter, arm, spell.age, strength)
    for arm in spell.arms:
        if arm.held is not None:
            _wrap(painter, arm.held, spell.age, strength)


def _arm(painter: QPainter, arm: Tentacle, t: float, strength: float) -> None:
    """A tapered tentacle from its root on the surface, out along the surface's
    normal and curving round to its tip."""
    side = Vec2(-arm.normal.y, arm.normal.x)
    reach = arm.tip - arm.base
    bend = math.sin(t * 4.0 + arm.phase) * 5.0
    middle = arm.base + arm.normal * (reach.length() * 0.55) + side * bend
    points = []
    for i in range(7):
        u = i / 6
        points.append(arm.base * ((1 - u) ** 2) + middle * (2 * (1 - u) * u) + arm.tip * (u * u))
    widths = [4.6 * (1 - u) + 0.7 for u in (i / 6 for i in range(7))]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_alpha(TENTACLE_RIM, 190 * strength))
    painter.drawPath(_taper(points, widths, grow=0.6))
    painter.setBrush(_alpha(TENTACLE, 255 * min(1.0, strength * 1.5)))
    painter.drawPath(_taper(points, widths))
    painter.setPen(_pen(_alpha(TENTACLE_SHEEN, 190 * strength), 0.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(_smooth(points[1:-1], closed=False))
    painter.setPen(Qt.PenStyle.NoPen)


def _wrap(painter: QPainter, stickman, t: float, strength: float) -> None:
    """Coils round a gripped adventurer's body, whichever way up he is."""
    feet = stickman.contact()
    body = stickman.center()
    axis = body - feet
    if axis.length() < 1.0:
        axis = Vec2(0.0, -1.0)
    up = axis.normalized()
    across = Vec2(-up.y, up.x)
    for k, share in enumerate((0.35, 0.75, 1.15)):
        at = feet + axis * share
        width = 5.5 + 1.2 * math.sin(t * 5 + k)
        a, b = at - across * width, at + across * width
        front = at + up * 2.2
        path = QPainterPath(_qt(a))
        path.quadTo(_qt(front), _qt(b))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_pen(_alpha(TENTACLE, 240 * strength), 2.2))
        painter.drawPath(path)
        painter.setPen(_pen(_alpha(TENTACLE_RIM, 170 * strength), 0.6))
        painter.drawPath(path)


# ----- divine smite -------------------------------------------------------------------

BLADE = 92.0
TIP_BELOW = 26.0
"""How far under his middle the sword's point is driven."""


def _smite(painter: QPainter, smite: Smite) -> None:
    """A huge sword of light, point down: it fades in over him, plunges, flares on
    impact (flash, ring, shafts), stays through him a moment and breaks into motes."""
    if smite.age <= 0.0:
        return
    fade = 1.0 - clamp(smite.fizzled / SMITE_FADE, 0.0, 1.0) if smite.fizzled >= 0 else 1.0
    after = smite.age - SMITE_HANG - SMITE_DROP
    appear = smoothstep(clamp(smite.age / 0.15, 0.0, 1.0))
    dissolve = 1.0 - smoothstep(clamp((after - (SMITE_LINGER - 0.35)) / 0.35, 0.0, 1.0))
    alpha = appear * dissolve * fade
    high = smite.top + BLADE
    tip = Vec2(smite.x, high + (smite.impact + TIP_BELOW - high) * smite.drop)
    pulse = 0.85 + 0.15 * math.sin(smite.age * 30.0)
    painter.setPen(Qt.PenStyle.NoPen)
    if after < 0.0:
        beam = QRadialGradient(_qt(tip + Vec2(0.0, -BLADE * 0.6)), BLADE * 0.9)
        beam.setColorAt(0.0, _alpha(GOLD, 70 * alpha * pulse))
        beam.setColorAt(1.0, _alpha(GOLD, 0))
        painter.setBrush(beam)
        painter.drawEllipse(_qt(tip + Vec2(0.0, -BLADE * 0.6)), BLADE * 0.5, BLADE * 0.9)
        if smite.drop > 0.0:
            painter.setPen(_pen(_alpha(HOLY, 150 * alpha), 2.0))
            for dx in (-7.0, 0.0, 7.0):
                painter.drawLine(_qt(tip + Vec2(dx, -BLADE - 40.0)), _qt(tip + Vec2(dx, -BLADE)))
            painter.setPen(Qt.PenStyle.NoPen)
    if after >= 0.0:
        _impact(painter, tip + Vec2(0.0, -TIP_BELOW), smite.impact + 30.0, after, fade)
    _sword(painter, tip, alpha * (pulse if after < 0.0 else 1.0))
    if after > SMITE_LINGER - 0.4:
        _motes(painter, tip, after - (SMITE_LINGER - 0.4), fade)


def _sword(painter: QPainter, tip: Vec2, alpha: float) -> None:
    if alpha <= 0.01:
        return

    def at(x: float, y: float) -> Vec2:
        return tip + Vec2(x, -y)

    glow = QRadialGradient(_qt(at(0.0, BLADE * 0.5)), BLADE * 0.6)
    glow.setColorAt(0.0, _alpha(GOLD, 120 * alpha))
    glow.setColorAt(1.0, _alpha(GOLD, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(_qt(at(0.0, BLADE * 0.5)), BLADE * 0.32, BLADE * 0.62)
    blade = [at(0, 0), at(-5.5, 14), at(-6.5, BLADE), at(6.5, BLADE), at(5.5, 14)]
    path = QPainterPath(_qt(blade[0]))
    for point in blade[1:]:
        path.lineTo(_qt(point))
    path.closeSubpath()
    painter.setPen(_pen(_alpha(GOLD, 230 * alpha), 1.4))
    painter.setBrush(_alpha(HOLY, 235 * alpha))
    painter.drawPath(path)
    painter.setPen(_pen(_alpha(GOLD, 200 * alpha), 1.2))
    painter.drawLine(_qt(at(0, 16)), _qt(at(0, BLADE - 6)))
    guard = [at(-19, BLADE + 4), at(-15, BLADE - 1), at(15, BLADE - 1), at(19, BLADE + 4)]
    guard += [at(15, BLADE + 6), at(-15, BLADE + 6)]
    path = QPainterPath(_qt(guard[0]))
    for point in guard[1:]:
        path.lineTo(_qt(point))
    path.closeSubpath()
    painter.setPen(_pen(_alpha(GOLD_DEEP, 230 * alpha), 1.0))
    painter.setBrush(_alpha(GOLD, 240 * alpha))
    painter.drawPath(path)
    painter.setPen(_pen(_alpha(GOLD_DEEP, 240 * alpha), 4.0))
    painter.drawLine(_qt(at(0, BLADE + 6)), _qt(at(0, BLADE + 22)))
    painter.setPen(_pen(_alpha(GOLD_DEEP, 230 * alpha), 1.0))
    painter.setBrush(_alpha(GOLD, 240 * alpha))
    painter.drawEllipse(_qt(at(0, BLADE + 26)), 4.0, 4.0)
    painter.setBrush(_alpha(HOLY, 255 * alpha))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(_qt(at(0, BLADE + 2.5)), 2.2, 2.2)


def _impact(painter: QPainter, center: Vec2, ground: float, after: float, fade: float) -> None:
    """The flash, a golden ring along the ground and shafts of light where it struck."""
    flash = 1.0 - clamp(after / 0.25, 0.0, 1.0)
    if flash > 0.0:
        light = QRadialGradient(_qt(center), 46.0)
        light.setColorAt(0.0, _alpha(HOLY, 255 * flash * fade))
        light.setColorAt(0.4, _alpha(GOLD, 160 * flash * fade))
        light.setColorAt(1.0, _alpha(GOLD, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(light)
        painter.drawEllipse(_qt(center), 46.0, 46.0)
    ring = clamp(after / 0.45, 0.0, 1.0)
    if ring < 1.0:
        radius = 10.0 + 70.0 * smoothstep(ring)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_pen(_alpha(GOLD, 220 * (1.0 - ring) * fade), 3.0 * (1.0 - ring) + 0.8))
        painter.drawEllipse(_qt(Vec2(center.x, ground)), radius, radius * 0.28)
    shafts = 1.0 - clamp(after / 0.5, 0.0, 1.0)
    if shafts > 0.0:
        grow = 20.0 + 40.0 * (1.0 - shafts)
        for k in range(8):
            angle = -math.pi / 2 + (k - 3.5) * 0.36
            way = Vec2(math.cos(angle), math.sin(angle))
            painter.setPen(_pen(_alpha(HOLY, 170 * shafts * fade), 2.2 * shafts + 0.6))
            painter.drawLine(_qt(center + way * 10.0), _qt(center + way * grow))


def _motes(painter: QPainter, tip: Vec2, t: float, fade: float) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    for k in range(18):
        u = clamp(t / 0.4 - (k % 6) * 0.04, 0.0, 1.0)
        if u <= 0.0 or u >= 1.0:
            continue
        start = tip + Vec2(math.sin(k * 2.3) * 5.0, -BLADE * (k / 18.0) - 4.0)
        drift = Vec2(math.sin(k * 1.7) * 14.0 * u, -28.0 * u)
        painter.setBrush(_alpha(GOLD if k % 2 else HOLY, 230 * (1.0 - u) * fade))
        painter.drawEllipse(_qt(start + drift), 1.3, 1.3)
