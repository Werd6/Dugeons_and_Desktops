"""Drawing the dragons' poison, lightning, acid and frost breath (fire is in `draw`), what
it leaves behind, and the deaths it deals: choking, electrocution, melting, freezing."""

from __future__ import annotations

import math
from collections.abc import Iterable
from random import Random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.rig.skeleton import BoneTransform
from dungeons_desktops.systems.breath import BREATHS, Demise, Mote
from dungeons_desktops.systems.dragon import Dragon
from dungeons_desktops.systems.flames import FLAME_LIFE, Flame

GAS_YOUNG = QColor(214, 236, 104)
GAS = QColor(120, 184, 60)
GAS_OLD = QColor(74, 122, 52)
BOLT_GLOW = QColor(70, 140, 255)
BOLT_CORE = QColor(236, 250, 255)
ACID = QColor(176, 232, 40)
ACID_DARK = QColor(84, 132, 16)
ACID_HAZE = QColor(150, 210, 50)
FROST = QColor(226, 240, 255)
FROST_EDGE = QColor(140, 190, 240)
ICE = QColor(200, 230, 255)
ICE_EDGE = QColor(110, 166, 222)
STEAM = QColor(226, 232, 226)
SMOKE = QColor(64, 60, 58)
SPARK = QColor(200, 240, 255)

SICKLY = QColor(128, 176, 64)
SICKLY_FAR = QColor(88, 124, 46)
SICKLY_HEAD = QColor(52, 74, 30)
SHOCK_FLASH = QColor(236, 250, 255)
CHARRED = QColor(34, 28, 26)
CHARRED_FAR = QColor(22, 18, 17)
ACID_BODY = QColor(168, 200, 60)
ACID_BODY_FAR = QColor(116, 150, 40)
FROZEN = QColor(176, 214, 246)
FROZEN_FAR = QColor(130, 170, 214)
FROZEN_HEAD = QColor(214, 236, 255)


def qt(point: Vec2) -> QPointF:
    return QPointF(point.x, point.y)


def world_pen(color: QColor, width: float) -> QPen:
    return QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)


def alpha(color: QColor, value: float) -> QColor:
    result = QColor(color)
    result.setAlpha(int(clamp(value, 0.0, 255.0)))
    return result


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = clamp(t, 0.0, 1.0)
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _seed(flame: Flame) -> int:
    """Stable for a particle's whole flight, so its puffs and drops don't jump about."""
    return (id(flame) >> 4) % 9973


# ----- breath ---------------------------------------------------------------------


def draw_breath(painter: QPainter, dragon: Dragon) -> None:
    """The breath of a dragon that doesn't breathe fire, plus what it leaves behind."""
    breath = BREATHS.get(dragon.variant, "fire")
    draw_motes(painter, dragon.wisps)
    if breath == "poison":
        _draw_poison(painter, dragon.flames)
    elif breath == "lightning":
        _draw_lightning(painter, dragon)
    elif breath == "acid":
        _draw_acid(painter, dragon.flames)
    elif breath == "cold":
        _draw_cold(painter, dragon.flames)


def _draw_poison(painter: QPainter, flames: Iterable[Flame]) -> None:
    """Billowing balls of green gas."""
    painter.setPen(Qt.PenStyle.NoPen)
    for flame in flames:
        t = flame.age / FLAME_LIFE
        seed = _seed(flame)
        color = mix(GAS_YOUNG, GAS, t / 0.5) if t < 0.5 else mix(GAS, GAS_OLD, (t - 0.5) / 0.5)
        radius = flame.radius * 1.15
        fade = (1.0 - t) ** 0.6
        for k in range(3):
            turn = seed * 2.4 + k * 2.1 + t * 1.5
            spot = flame.position + Vec2.from_angle(turn, radius * 0.45)
            r = radius * (0.55 + 0.12 * k)
            painter.setBrush(alpha(color.darker(115), 110 * fade))
            painter.drawEllipse(qt(spot), r, r)
            painter.setBrush(alpha(color.lighter(118), 90 * fade))
            painter.drawEllipse(qt(spot + Vec2(-0.25, -0.3) * r), r * 0.55, r * 0.55)


def _draw_lightning(painter: QPainter, dragon: Dragon) -> None:
    """Forked bolts sprayed from the jaws across the stream, redrawn every few frames."""
    flames = dragon.flames
    if not flames:
        return
    random = Random(int(dragon.clock * 18.0) * 7919 + len(dragon.wisps))
    painter.setPen(Qt.PenStyle.NoPen)
    for flame in flames:
        t = flame.age / FLAME_LIFE
        r = flame.radius * 0.55
        painter.setBrush(alpha(BOLT_GLOW, 70 * (1.0 - t)))
        painter.drawEllipse(qt(flame.position), r, r)
    young = [f for f in flames if f.age < 0.5 * FLAME_LIFE]
    if not young:
        return
    breathing = dragon.fire_time > 0.0 and not dragon.dead
    start = dragon.mouth if breathing else min(young, key=lambda f: f.age).position
    ends = random.sample(young, min(7, len(young)))
    flicker = random.choice((1.0, 1.0, 0.55))
    for flame in ends:
        path = _bolt(start, flame.position, random)
        _stroke_bolt(painter, path, flicker)
        if len(path) > 3 and random.random() < 0.7:
            k = random.randrange(1, len(path) - 2)
            along = path[-1] - path[k]
            fork_end = path[k] + along.rotated(random.choice((-1, 1)) * 0.6) * 0.45
            _stroke_bolt(painter, _bolt(path[k], fork_end, random), flicker * 0.7)


def _bolt(start: Vec2, end: Vec2, random: Random) -> list[Vec2]:
    span = end - start
    length = span.length()
    steps = max(2, int(length / 9.0))
    side = Vec2(-span.y, span.x).normalized()
    points = [start]
    for i in range(1, steps):
        jag = random.gauss(0.0, min(5.0, 0.07 * length))
        points.append(start + span * (i / steps) + side * jag)
    points.append(end)
    return points


def _stroke_bolt(painter: QPainter, path: list[Vec2], strength: float) -> None:
    points = [qt(p) for p in path]
    painter.setPen(world_pen(alpha(BOLT_GLOW, 150 * strength), 3.6))
    painter.drawPolyline(points)
    painter.setPen(world_pen(alpha(BOLT_CORE, 255 * strength), 1.3))
    painter.drawPolyline(points)


def draw_acid(painter: QPainter, flames: Iterable[Flame]) -> None:
    """A spray of acid on its own (the desert hydra's)."""
    _draw_acid(painter, flames)


def _draw_acid(painter: QPainter, flames: Iterable[Flame]) -> None:
    """A spray of acid droplets streaking out of the jaws through a thin haze."""
    for flame in flames:
        t = flame.age / FLAME_LIFE
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(ACID_HAZE, 45 * (1.0 - t)))
        painter.drawEllipse(qt(flame.position), flame.radius * 0.7, flame.radius * 0.7)
    for flame in flames:
        t = flame.age / FLAME_LIFE
        seed = _seed(flame)
        streak = flame.velocity * 0.035
        for k in range(2):
            offset = Vec2.from_angle(seed * 1.7 + k * 3.1, flame.radius * 0.4 * (k + 0.5))
            spot = flame.position + offset
            size = 1.1 + 0.25 * ((seed >> k) % 4)
            painter.setPen(world_pen(alpha(ACID_DARK, 200 * (1.0 - 0.5 * t)), size * 1.5))
            painter.drawLine(qt(spot - streak), qt(spot))
            painter.setPen(world_pen(alpha(ACID, 255 * (1.0 - 0.4 * t)), size))
            painter.drawLine(qt(spot - streak * 0.6), qt(spot))


def _draw_cold(painter: QPainter, flames: Iterable[Flame]) -> None:
    """A frosty blue-white cone of mist glittering with ice crystals."""
    painter.setPen(Qt.PenStyle.NoPen)
    flames = list(flames)
    for flame in flames:
        t = flame.age / FLAME_LIFE
        fade = (1.0 - t) ** 0.7
        r = flame.radius * 1.05
        painter.setBrush(alpha(FROST_EDGE, 95 * fade))
        painter.drawEllipse(qt(flame.position), r, r)
        painter.setBrush(alpha(FROST, 150 * fade))
        painter.drawEllipse(qt(flame.position), r * 0.65, r * 0.65)
    for flame in flames:
        seed = _seed(flame)
        if seed % 2:
            continue
        t = flame.age / FLAME_LIFE
        offset = Vec2.from_angle(seed * 0.9, flame.radius * 0.5)
        _snowflake(
            painter, flame.position + offset, 1.8 + flame.radius * 0.25, seed + t * 4.0, 1.0 - t
        )


def _snowflake(painter: QPainter, center: Vec2, size: float, turn: float, strength: float) -> None:
    painter.setPen(world_pen(alpha(FROST_EDGE.darker(115), 240 * strength), 1.1))
    for k in range(3):
        arm = Vec2.from_angle(turn + k * math.pi / 3, size)
        painter.drawLine(qt(center - arm), qt(center + arm))
    painter.setPen(world_pen(alpha(QColor(255, 255, 255), 255 * strength), 0.45))
    for k in range(3):
        arm = Vec2.from_angle(turn + k * math.pi / 3, size * 0.8)
        painter.drawLine(qt(center - arm), qt(center + arm))


# ----- particles ------------------------------------------------------------------


def draw_motes(painter: QPainter, motes: Iterable[Mote]) -> None:
    for mote in motes:
        _draw_mote(painter, mote)


def _draw_mote(painter: QPainter, mote: Mote) -> None:
    t = mote.t
    kind, at, size = mote.kind, mote.position, mote.size
    painter.setPen(Qt.PenStyle.NoPen)
    if kind in ("cloud", "fume"):
        r = size * (1.0 + (0.5 if kind == "cloud" else 1.2) * t)
        color = mix(GAS, GAS_OLD, t)
        painter.setBrush(alpha(color, (65 if kind == "cloud" else 150) * (1.0 - t) ** 0.8))
        painter.drawEllipse(qt(at), r, r * 0.85)
    elif kind in ("mist", "steam", "smoke"):
        r = size * (1.0 + 1.0 * t)
        color = {"mist": FROST, "steam": STEAM, "smoke": SMOKE}[kind]
        painter.setBrush(alpha(color, (110 if kind == "smoke" else 90) * (1.0 - t)))
        painter.drawEllipse(qt(at), r, r)
    elif kind == "spark":
        tail = at - mote.velocity * 0.02
        painter.setPen(world_pen(alpha(BOLT_GLOW, 150 * (1.0 - t)), size * 1.2))
        painter.drawLine(qt(tail), qt(at))
        painter.setPen(world_pen(alpha(SPARK, 255 * (1.0 - t)), size * 0.5))
        painter.drawLine(qt(tail), qt(at))
    elif kind == "drip":
        tail = at - mote.velocity * 0.02
        painter.setPen(world_pen(ACID_DARK, size * 1.4))
        painter.drawLine(qt(tail), qt(at))
        painter.setPen(world_pen(ACID, size))
        painter.drawLine(qt(tail), qt(at))
    elif kind == "sizzle":
        w = size * (1.0 + 0.6 * t)
        painter.setBrush(alpha(ACID_DARK, 200 * (1.0 - t)))
        painter.drawEllipse(qt(at), w, w * 0.35)
        painter.setBrush(alpha(ACID, 230 * (1.0 - t)))
        painter.drawEllipse(qt(at + Vec2(0.0, -0.2)), w * 0.6, w * 0.22)
        painter.setPen(world_pen(alpha(ACID, 220 * (1.0 - t)), 0.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bubble = 0.4 + 0.4 * math.sin(mote.age * 30.0) ** 2
        painter.drawEllipse(qt(at + Vec2(w * 0.3, -0.6)), bubble, bubble)
    elif kind == "bubble":
        r = size * (0.6 + 0.6 * t)
        painter.setPen(world_pen(alpha(ACID, 230 * (1.0 - t * t)), 0.45))
        painter.setBrush(alpha(ACID_HAZE, 90 * (1.0 - t)))
        painter.drawEllipse(qt(at), r, r)
    elif kind == "shard":
        fade = clamp((1.0 - t) / 0.35, 0.0, 1.0)
        tip = Vec2.from_angle(mote.angle, size)
        side = Vec2.from_angle(mote.angle + 2.3, size * 0.45)
        back = Vec2.from_angle(mote.angle - 2.5, size * 0.55)
        painter.setPen(world_pen(alpha(ICE_EDGE, 230 * fade), 0.45))
        painter.setBrush(alpha(ICE, 210 * fade))
        painter.drawPolygon([qt(at + tip), qt(at + side), qt(at + back)])
    elif kind == "glint":
        strength = math.sin(math.pi * t)
        _snowflake(painter, at, size, mote.age * 3.0, strength)


# ----- deaths ---------------------------------------------------------------------


def demise_colors(
    demise: Demise, near: QColor, far: QColor, head: QColor
) -> tuple[QColor, QColor, QColor]:
    """A dying stickman's limb and head colours."""
    tint = demise.tint
    kind = demise.kind
    if kind == "poison":
        return mix(near, SICKLY, tint), mix(far, SICKLY_FAR, tint), mix(head, SICKLY_HEAD, tint)
    if kind == "lightning":
        if demise.flashing:
            return SHOCK_FLASH, SHOCK_FLASH, QColor(30, 40, 60)
        return mix(near, CHARRED, tint), mix(far, CHARRED_FAR, tint), mix(head, CHARRED, tint)
    if kind == "acid":
        return mix(near, ACID_BODY, tint), mix(far, ACID_BODY_FAR, tint), mix(head, ACID_DARK, tint)
    return mix(near, FROZEN, tint), mix(far, FROZEN_FAR, tint), mix(head, FROZEN_HEAD, tint)


def melted(transforms: dict[str, BoneTransform], melt: float) -> dict[str, BoneTransform]:
    """The body slumped and spread toward its lowest point as it melts."""
    if melt <= 0.0:
        return transforms
    points = [p for t in transforms.values() for p in (t.start, t.end)]
    rest = max(p.y for p in points)
    middle = sum(p.x for p in points) / len(points)

    def sag(p: Vec2) -> Vec2:
        return Vec2(
            middle + (p.x - middle) * (1.0 + 0.4 * melt), rest - (rest - p.y) * (1.0 - melt)
        )

    result = {}
    for name, t in transforms.items():
        start, end = sag(t.start), sag(t.end)
        result[name] = BoneTransform(start, end, (end - start).angle() if end != start else t.angle)
    return result


def draw_demise_under(
    painter: QPainter, demise: Demise, transforms: dict[str, BoneTransform]
) -> None:
    """What goes behind the body: the ice shell's back face."""
    if demise.kind == "cold" and not demise.shattered and demise.frost > 0.0:
        _draw_ice(painter, transforms, demise.frost, back=True)


def _draw_melting_head(
    painter: QPainter, demise: Demise, transforms: dict[str, BoneTransform], head_radius: float
) -> None:
    """The head slumping into a flattening blob."""
    head = transforms.get("head")
    if head is None:
        return
    melt, tint = demise.melt, demise.tint
    rx = head_radius * (1.0 + 0.3 * melt)
    ry = head_radius * (1.0 - 0.85 * melt)
    center = head.end + Vec2(0.0, head_radius - ry)
    painter.setPen(world_pen(mix(QColor(236, 230, 214), ACID_BODY, tint), 1.5))
    painter.setBrush(mix(QColor(24, 26, 33), ACID_DARK, tint))
    painter.drawEllipse(qt(center), rx, ry)


def _draw_puddle(
    painter: QPainter, demise: Demise, transforms: dict[str, BoneTransform], head_radius: float
) -> None:
    """The bubbling acid pool he sinks into, spreading as he melts."""
    points = [p for t in transforms.values() for p in (t.start, t.end)]
    rest = max(p.y for p in points)
    middle = Vec2(sum(p.x for p in points) / len(points), rest)
    melt = demise.melt
    grow = clamp((demise.time - 0.2) / 1.0, 0.0, 1.0)
    if grow <= 0.0:
        return
    width = head_radius * (1.2 + 1.6 * melt) * grow
    depth = head_radius * (0.25 + 0.55 * melt)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(alpha(ACID_DARK, 225))
    painter.drawEllipse(qt(middle), width, depth)
    painter.setBrush(alpha(ACID, 215))
    painter.drawEllipse(qt(middle + Vec2(-0.1, -0.25) * depth), width * 0.75, depth * 0.6)
    painter.setBrush(alpha(QColor(236, 255, 160), 160))
    painter.drawEllipse(qt(middle + Vec2(-0.35 * width, -0.4 * depth)), width * 0.18, depth * 0.2)


def draw_demise_over(
    painter: QPainter, demise: Demise, transforms: dict[str, BoneTransform], head_radius: float
) -> None:
    """What goes over the body: the skeleton flashing through, the ice shell, and the
    fumes, sparks, smoke, bubbles or shards."""
    if demise.kind == "lightning" and demise.flashing:
        _draw_skeleton(painter, transforms, head_radius)
    if demise.kind == "acid":
        _draw_melting_head(painter, demise, transforms, head_radius)
        _draw_puddle(painter, demise, transforms, head_radius)
    if demise.kind == "cold" and not demise.shattered and demise.frost > 0.0:
        _draw_ice(painter, transforms, demise.frost, head_radius)
    draw_motes(painter, demise.motes)


def _draw_skeleton(
    painter: QPainter, transforms: dict[str, BoneTransform], head_radius: float
) -> None:
    """The bones lit up through the body as the current runs through it."""
    painter.setPen(world_pen(alpha(BOLT_GLOW, 140), 3.2))
    for t in transforms.values():
        painter.drawLine(qt(t.start), qt(t.end))
    painter.setPen(world_pen(QColor(30, 40, 60), 0.6))
    for t in transforms.values():
        painter.drawLine(qt(t.start.lerp(t.end, 0.15)), qt(t.start.lerp(t.end, 0.85)))
    head = transforms.get("head")
    if head is not None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 40, 60))
        for side in (-0.4, 0.4):
            painter.drawEllipse(qt(head.end + Vec2(side * head_radius, -0.1)), 0.7, 0.8)


def _draw_ice(
    painter: QPainter,
    transforms: dict[str, BoneTransform],
    frost: float,
    head_radius: float = 4.5,
    back: bool = False,
) -> None:
    """A translucent block of ice closing over the body from the feet up: the `back`
    face goes behind the body, the glassy front face with its glints over it."""
    points = [p for t in transforms.values() for p in (t.start, t.end)]
    pad = head_radius * 0.6 + 1.0
    left = min(p.x for p in points) - pad
    right = max(p.x for p in points) + pad
    top = min(p.y for p in points) - head_radius - 1.0
    bottom = max(p.y for p in points) + 0.5
    top = bottom - (bottom - top) * frost
    w, h = right - left, bottom - top
    shell = [
        Vec2(left, bottom),
        Vec2(left - 0.6, top + h * 0.45),
        Vec2(left + w * 0.15, top),
        Vec2(left + w * 0.65, top - 0.8),
        Vec2(right, top + h * 0.2),
        Vec2(right + 0.6, top + h * 0.7),
        Vec2(right, bottom),
    ]
    if back:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(ICE, 110))
        painter.drawPolygon([qt(p) for p in shell])
        return
    painter.setPen(world_pen(alpha(ICE_EDGE, 230), 0.7))
    painter.setBrush(alpha(ICE, 55))
    painter.drawPolygon([qt(p) for p in shell])
    painter.setPen(world_pen(alpha(QColor(255, 255, 255), 200), 0.6))
    painter.drawLine(qt(Vec2(left + w * 0.2, top + 1.0)), qt(Vec2(left + w * 0.08, top + h * 0.5)))
    painter.drawLine(qt(Vec2(left + w * 0.32, top + 1.2)), qt(Vec2(left + w * 0.26, top + h * 0.3)))
    painter.setPen(world_pen(alpha(ICE_EDGE, 160), 0.4))
    painter.drawLine(
        qt(Vec2(right - w * 0.2, top + h * 0.3)), qt(Vec2(right - w * 0.4, top + h * 0.6))
    )
