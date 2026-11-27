"""Drawing the kobold drake riders: a little chromatic drake in its dragon colours
(the same horns and head, at drake size) with a kobold archer of its colour in the
saddle, and their arrows, breath bolts and the blasts they burst in."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.game.defenders.dragon.render import (
    DRAGON_PALETTES,
    OUTLINE,
    DragonPalette,
    _draw_dragon_head,
)
from dungeons_desktops.game.defenders.drakes.drake import BLAST_TIME, Drake, DrakeLeg, Missile
from dungeons_desktops.game.defenders.drakes.kobold import Kobold, Traps
from dungeons_desktops.game.effects.render import (
    ACID,
    ACID_DARK,
    BOLT_CORE,
    BOLT_GLOW,
    FROST,
    FROST_EDGE,
    GAS,
    GAS_YOUNG,
)
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.effects import FLAME_HOT, FLAME_MID
from dungeons_desktops.render.primitives import qt, world_pen

HEAD_SCALE = 0.84
SADDLE = QColor(120, 72, 40)
BOW = QColor(120, 80, 44)
STRING = QColor(230, 226, 210)
SHAFT = QColor(170, 130, 85)
STEEL = QColor(205, 210, 220)
FLETCH = QColor(220, 70, 60)
GOLD_SHAFT = QColor(196, 148, 42)
GOLD_FLETCH = QColor(255, 230, 140)
GOLD_TIP = QColor(255, 214, 74)
TRAP_IRON = QColor(90, 92, 100)
TRAP_STEEL = QColor(170, 176, 186)
BOLT_COLOURS = {
    "red": (FLAME_MID, FLAME_HOT),
    "green": (GAS, GAS_YOUNG),
    "blue": (BOLT_GLOW, BOLT_CORE),
    "black": (ACID_DARK, ACID),
    "white": (FROST_EDGE, FROST),
}
"""Each breath's bolt and blast: outer glow, hot core."""
KOBOLD_EYE = QColor(250, 220, 90)
LEGENDARY_GOLD = QColor(255, 210, 82)
CHROMATIC_SHEEN = QColor(230, 220, 255)


def draw_drakes(painter: QPainter, drakes: Iterable[Drake], outline: QColor | None = None) -> None:
    for drake in drakes:
        draw_drake(painter, drake, outline)


@chromatic_appearance
def draw_drake(painter: QPainter, drake: Drake, outline: QColor | None = None) -> None:
    """Far wing and leg, tail, body, neck and head, the kobold, near leg, near wing."""
    p = DRAGON_PALETTES.get(drake.variant, DRAGON_PALETTES["red"])
    tail = drake.tail
    widths = [3.6 * (1.0 - i / len(tail)) + 0.7 for i in range(len(tail))]
    near = next(leg for leg in drake.legs if leg.near)
    far = next(leg for leg in drake.legs if not leg.near)
    rider = None if drake.dead else _Kobold(drake)
    scale = getattr(drake, "size", 1.0)
    painter.save()
    if abs(scale - 1.0) > 1e-6:
        origin = qt(drake.body)
        painter.translate(origin)
        painter.scale(scale, scale)
        painter.translate(-origin.x(), -origin.y())

    _draw_wing(painter, drake, p, near=False)
    if outline is not None:
        for leg in (far, near):
            _leg_strokes(painter, drake, leg, outline, 1.6)
        for i in range(len(tail) - 1):
            painter.setPen(world_pen(outline, widths[i] + 1.6))
            painter.drawLine(qt(tail[i]), qt(tail[i + 1]))
        painter.setPen(world_pen(outline, 8.0 + 1.6))
        painter.drawLine(qt(drake.hip), qt(drake.chest))
        painter.setPen(world_pen(outline, 3.4 + 1.6))
        painter.drawLine(qt(drake.neck_base), qt(drake.head))
        if rider is not None:
            rider.strokes(painter, outline, 1.4)

    _leg_strokes(painter, drake, far, p.far, 0.0)
    for i in range(len(tail) - 1):
        painter.setPen(world_pen(p.skin, widths[i]))
        painter.drawLine(qt(tail[i]), qt(tail[i + 1]))
    tip, before = tail[-1], tail[-2]
    along = (tip - before).normalized()
    across = Vec2(-along.y, along.x) * 1.8
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(p.skin)
    painter.drawPolygon([qt(tip + across), qt(tip + along * 3.5), qt(tip - across)])

    painter.setPen(world_pen(p.skin, 8.0))
    painter.drawLine(qt(drake.hip), qt(drake.chest))
    belly = drake.local(Vec2(0.0, 2.2))
    painter.setPen(world_pen(p.belly, 3.0))
    painter.drawLine(qt(drake.hip + belly + drake.forward * 1.5), qt(drake.chest + belly))
    painter.setPen(world_pen(p.far, 0.8))
    for k in range(1, 4):
        spine = drake.hip.lerp(drake.chest, k / 4.0) + drake.local(Vec2(0.0, -3.6))
        painter.drawLine(qt(spine), qt(spine + drake.local(Vec2(-0.8, -1.4))))
    painter.setPen(world_pen(p.skin, 3.4))
    painter.drawLine(qt(drake.neck_base), qt(drake.head))
    _draw_dragon_head(painter, drake, HEAD_SCALE)
    if outline is None and getattr(drake, "legendary", False):
        shimmer = 0.55 + 0.45 * math.sin(drake.clock * 3.2 + drake.slot)
        painter.setPen(world_pen(QColor(230, 220, 255, int(150 * shimmer)), 1.0))
        painter.drawLine(qt(drake.hip + drake.local(Vec2(0.0, -3.2))), qt(drake.chest))
        painter.setPen(world_pen(QColor(255, 185, 90, int(110 * shimmer)), 0.7))
        painter.drawLine(qt(drake.neck_base), qt(drake.head))

    if rider is not None:
        rider.draw(painter, p)
    _leg_strokes(painter, drake, near, p.skin, 0.0)
    _draw_feet(painter, drake, near, p)
    _draw_wing(painter, drake, p, near=True)
    if rider is not None:
        rider.draw_bow(painter, p)
    painter.restore()
    draw_missiles(painter, drake)


def draw_kobolds(
    painter: QPainter, kobolds: Iterable[Kobold], outline: QColor | None = None
) -> None:
    for kobold in kobolds:
        draw_kobold(painter, kobold, outline)


@chromatic_appearance
def draw_kobold(painter: QPainter, kobold: Kobold, outline: QColor | None = None) -> None:
    """A kobold on foot: the rider's body, standing on his own two legs."""
    p = DRAGON_PALETTES.get(kobold.variant, DRAGON_PALETTES["red"])
    figure = _Kobold(kobold)
    if outline is not None:
        figure.strokes(painter, outline, 1.4)
    figure.draw(painter, p)
    figure.draw_bow(painter, p)
    draw_arrows(painter, kobold.arrows, gold=True)


def draw_arrows(
    painter: QPainter, arrows: Iterable[Missile], *, gold: bool = False
) -> None:
    shaft, fletch, tip = (
        (GOLD_SHAFT, GOLD_FLETCH, GOLD_TIP) if gold else (SHAFT, FLETCH, STEEL)
    )
    for arrow in arrows:
        along = arrow.velocity.normalized()
        tail = arrow.position - along * 6.0
        painter.setPen(world_pen(shaft, 0.7))
        painter.drawLine(qt(tail), qt(arrow.position))
        painter.setPen(world_pen(fletch, 0.9))
        painter.drawLine(qt(tail), qt(tail + along * 1.5))
        painter.setPen(world_pen(tip, 1.0))
        painter.drawLine(qt(arrow.position), qt(arrow.position + along * 1.2))


def draw_traps(painter: QPainter, traps: Traps, outline: QColor | None = None) -> None:
    """Toothed jaw traps: open and flat on the ground, or snapped shut."""
    for trap in traps.traps:
        base = trap.position
        shut = trap.sprung is not None
        if outline is not None:
            painter.setPen(world_pen(outline, 2.6))
            painter.drawLine(qt(base + Vec2(-4.0, -0.6)), qt(base + Vec2(4.0, -0.6)))
        painter.setPen(world_pen(TRAP_IRON, 1.0))
        painter.drawLine(qt(base + Vec2(-3.5, -0.5)), qt(base + Vec2(3.5, -0.5)))
        painter.setPen(world_pen(TRAP_STEEL, 0.6))
        if shut:
            painter.drawLine(qt(base + Vec2(0.0, -0.5)), qt(base + Vec2(0.0, -4.0)))
            for x in (-1.0, 0.0, 1.0):
                painter.drawLine(qt(base + Vec2(x, -2.0)), qt(base + Vec2(x * 1.6, -3.0)))
            continue
        for side in (-1.0, 1.0):
            painter.drawLine(qt(base + Vec2(side * 3.5, -0.5)), qt(base + Vec2(side * 4.2, -1.8)))
            for k in range(3):
                tooth = base + Vec2(side * (1.0 + k * 1.1), -0.6)
                painter.drawLine(qt(tooth), qt(tooth + Vec2(0.0, -1.2)))
        if not trap.armed:
            continue
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(DRAGON_PALETTES.get(trap.variant, DRAGON_PALETTES["red"]).skin)
        painter.drawEllipse(qt(base + Vec2(0.0, -0.8)), 0.8, 0.8)


def draw_missiles(painter: QPainter, drake: Drake) -> None:
    """Its kobold's arrows, its breath bolts and their blasts."""
    draw_arrows(painter, drake.arrows)
    glow, core = BOLT_COLOURS.get(drake.variant, BOLT_COLOURS["red"])
    painter.setPen(Qt.PenStyle.NoPen)
    for bolt in drake.bolts:
        along = bolt.velocity.normalized()
        for k in range(4, 0, -1):
            trail = QColor(glow)
            trail.setAlpha(int(150 * (1.0 - k / 5)))
            painter.setBrush(trail)
            painter.drawEllipse(qt(bolt.position - along * (2.2 * k)), 2.4 - 0.3 * k, 2.4 - 0.3 * k)
        painter.setBrush(glow)
        painter.drawEllipse(qt(bolt.position), 2.6, 2.6)
        painter.setBrush(core)
        painter.drawEllipse(qt(bolt.position), 1.3, 1.3)
    for blast in drake.blasts:
        t = blast.age / BLAST_TIME
        fade = 1.0 - t
        radius = blast.radius * (0.35 + 0.65 * smoothstep(min(1.0, t * 2.2)))
        outer = QColor(glow)
        outer.setAlpha(int(170 * fade))
        inner = QColor(core)
        inner.setAlpha(int(230 * fade * fade))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outer)
        painter.drawEllipse(qt(blast.center), radius, radius)
        painter.setBrush(inner)
        painter.drawEllipse(qt(blast.center), radius * 0.55, radius * 0.55)
        painter.setPen(world_pen(outer, 1.5))
        for k in range(8):
            ray = Vec2.from_angle(0.3 + k * 0.785, 1.0)
            painter.drawLine(
                qt(blast.center + ray * radius * 0.9),
                qt(blast.center + ray * radius * (1.1 + 0.4 * t)),
            )


def _leg_strokes(
    painter: QPainter, drake: Drake, leg: DrakeLeg, color: QColor, grow: float
) -> None:
    """A meaty drumstick from the hip to the hock, a thin shank down to the foot."""
    painter.setPen(world_pen(color, 3.4 + grow))
    painter.drawLine(qt(leg.root), qt(leg.root.lerp(leg.hock, 0.6)))
    painter.setPen(world_pen(color, 2.2 + grow))
    painter.drawLine(qt(leg.root), qt(leg.hock))
    painter.setPen(world_pen(color, 1.3 + grow))
    painter.drawLine(qt(leg.hock), qt(leg.foot))
    if grow > 0.0 or not leg.near:
        for base, tip in _toes(drake, leg):
            painter.setPen(world_pen(color, 0.9 + grow))
            painter.drawLine(qt(base), qt(tip))


def _toes(drake: Drake, leg: DrakeLeg) -> list[tuple[Vec2, Vec2]]:
    """Three toes forward, one back, flat on the ground and curling up as it lifts."""
    curl = leg.lift
    ahead = Vec2(float(drake.facing), 0.0)
    toes = []
    for spread, length in ((-0.25, 2.6), (0.15, 2.2)):
        direction = ahead.rotated(drake.facing * (spread + 1.1 * curl))
        toes.append((leg.foot, leg.foot + direction * length))
    back = (-ahead).rotated(-drake.facing * (0.3 + 0.6 * curl))
    toes.append((leg.foot, leg.foot + back * 1.4))
    return toes


def _draw_feet(painter: QPainter, drake: Drake, leg: DrakeLeg, p: DragonPalette) -> None:
    for base, tip in _toes(drake, leg):
        painter.setPen(world_pen(p.skin, 0.9))
        painter.drawLine(qt(base), qt(tip))
        painter.setPen(world_pen(p.talon, 0.6))
        painter.drawLine(qt(tip), qt(tip + (tip - base).normalized() * 0.7))


def _draw_wing(painter: QPainter, drake: Drake, p: DragonPalette, near: bool) -> None:
    s = (0.62 if drake.flying else 0.5) * (1.0 if near else 0.85)
    root = drake.chest + drake.local(Vec2(-2.0 if near else -1.0, -3.4))
    if drake.flying:
        beat = drake.flap + (0.0 if near else 0.25)
        arm = 0.35 + 1.05 * math.cos(beat)
        hand = 0.35 + 1.25 * math.cos(beat - 0.9)
        sweep = -2.0 * math.sin(beat)
        elbow = root + drake.local(Vec2(1.0 + sweep, -16.0 * math.sin(arm)) * s)
        tip = elbow + drake.local(Vec2(-12.0 + 2.0 * sweep, -24.0 * math.sin(hand)) * s)
        trailing = elbow + drake.local(Vec2(-21.0, -13.0 * math.sin(hand)) * s)
        back = root + drake.local(Vec2(-17.0, 2.0) * s)
    else:
        root = drake.chest + drake.local(Vec2(-1.5, -1.0))
        elbow = root + drake.local(Vec2(-2.0, -3.0) * s)
        tip = root + drake.local(Vec2(-17.0, 0.5) * s)
        trailing = root + drake.local(Vec2(-12.0, 3.5) * s)
        back = root + drake.local(Vec2(-5.0, 3.5) * s)

    def notch(a: Vec2, b: Vec2) -> Vec2:
        return a.lerp(b, 0.5).lerp(elbow, 0.22)

    painter.setPen(world_pen(p.far if near else OUTLINE, 0.7))
    painter.setBrush(p.wing if near else p.wing_far)
    outline = [root, elbow, tip, notch(tip, trailing), trailing, notch(trailing, back), back]
    painter.drawPolygon([qt(point) for point in outline])
    painter.setPen(world_pen(p.skin if near else p.far, 1.1))
    painter.drawPolyline([qt(root), qt(elbow), qt(tip)])


class _Kobold:
    """The rider, posed from the drake's saddle and the kobold's lean: a little scaly
    biped the size of a goblin, with a snout, two back-swept horns and a tail, a
    shortbow held out along his aim and the string drawn back to his chest."""

    def __init__(self, drake: Drake | Kobold) -> None:
        self.drake = drake
        up = drake.rider_up
        self.up = up
        self.ahead = up.rotated(drake.facing * math.pi / 2)
        self.down = -up
        self.seat = drake.seat
        self.shoulder = drake.rider_shoulder
        self.head = drake.rider_head
        ahead, down = self.ahead, self.down
        if isinstance(drake, Kobold):
            self.legs = drake.legs()
        else:
            knee = self.seat + ahead * 2.2 + down * 1.4
            self.legs = [(knee, knee + down * 2.6 - ahead * 0.8)]
        aim = drake.aim if not drake.dead else ahead.rotated(drake.facing * 0.9)
        self.aim = aim
        self.hand = self.shoulder + aim * 3.2
        across = aim.rotated(math.pi / 2)
        bend = 1.4
        self.bow = [
            self.hand + across * 3.6 - aim * 1.0,
            self.hand + across * 2.0 + aim * (bend * 0.7),
            self.hand + aim * bend,
            self.hand - across * 2.0 + aim * (bend * 0.7),
            self.hand - across * 3.6 - aim * 1.0,
        ]
        self.nock = self.hand - aim * (1.0 + 2.4 * drake.bow_draw)
        self.tail = [
            self.seat - ahead * 1.0,
            self.seat - ahead * 2.6 + down * 1.6,
            self.seat - ahead * 3.4 + down * 3.6,
        ]

    def strokes(self, painter: QPainter, color: QColor, grow: float) -> None:
        painter.setPen(world_pen(color, 0.9 + grow))
        painter.drawPolyline([qt(p) for p in self.bow])
        painter.setPen(world_pen(color, 1.2 + grow))
        painter.drawPolyline([qt(p) for p in self.tail])
        painter.setPen(world_pen(color, 2.6 + grow))
        painter.drawLine(qt(self.seat), qt(self.shoulder))
        painter.setPen(world_pen(color, 1.4 + grow))
        for knee, foot in self.legs:
            painter.drawPolyline([qt(self.seat), qt(knee), qt(foot)])
        painter.drawLine(qt(self.shoulder), qt(self.hand))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        radius = 1.9 + grow / 2
        painter.drawEllipse(qt(self.head), radius, radius)
        painter.drawEllipse(
            qt(self.head + self.ahead * 2.0 + self.down * 0.3), 1.3 + grow / 2, 1.0 + grow / 2
        )

    def draw(self, painter: QPainter, p: DragonPalette) -> None:
        skin = p.skin.lighter(112)
        ahead, down, up = self.ahead, self.down, self.up
        painter.setPen(world_pen(skin.darker(125), 1.3))
        for knee, foot in self.legs[1:]:
            painter.drawPolyline([qt(self.seat), qt(knee), qt(foot)])
        painter.setPen(world_pen(skin.darker(115), 1.2))
        painter.drawPolyline([qt(pt) for pt in self.tail])
        painter.setPen(world_pen(SADDLE, 1.6))
        painter.drawLine(
            qt(self.seat - ahead * 1.6 + down * 0.8), qt(self.seat + ahead * 1.4 + down * 0.8)
        )

        painter.setPen(world_pen(skin, 2.6))
        painter.drawLine(qt(self.seat), qt(self.shoulder))
        painter.setPen(world_pen(p.belly, 1.0))
        painter.drawLine(
            qt(self.seat + ahead * 0.8 - up * 0.2), qt(self.shoulder + ahead * 0.8 + down * 0.6)
        )
        painter.setPen(world_pen(SADDLE, 0.8))
        painter.drawLine(qt(self.shoulder - ahead * 1.0), qt(self.seat + ahead * 1.0 + up * 1.2))
        if getattr(self.drake, "legendary", False):
            painter.setPen(world_pen(LEGENDARY_GOLD, 0.75))
            painter.drawLine(
                qt(self.shoulder - ahead * 1.1 + up * 0.3),
                qt(self.seat + ahead * 1.0 + up * 1.2),
            )

        head = self.head
        painter.setPen(world_pen(p.horn, 0.8))
        for lift, length in ((0.9, 2.4), (0.2, 2.0)):
            base = head - ahead * 0.6 + up * lift
            painter.drawLine(qt(base), qt(base - ahead * length + up * 1.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(skin)
        painter.drawEllipse(qt(head), 1.9, 1.9)
        snout = [
            head + up * 1.0,
            head + ahead * 3.2 + up * 0.1,
            head + ahead * 3.2 + down * 0.5,
            head + down * 0.6,
        ]
        painter.drawPolygon([qt(pt) for pt in snout])
        painter.setBrush(p.belly)
        jaw = [head + down * 0.6, head + ahead * 2.8 + down * 0.6, head + ahead * 0.6 + down * 1.5]
        painter.drawPolygon([qt(pt) for pt in jaw])
        painter.setBrush(KOBOLD_EYE)
        painter.drawEllipse(qt(head + ahead * 0.6 + up * 0.5), 0.55, 0.55)
        painter.setBrush(OUTLINE)
        painter.drawEllipse(qt(head + ahead * 0.75 + up * 0.5), 0.25, 0.25)
        if getattr(self.drake, "legendary", False):
            painter.setBrush(LEGENDARY_GOLD)
            painter.drawEllipse(qt(head - ahead * 0.2 + up * 1.6), 0.7, 0.45)

        knee, foot = self.legs[0]
        painter.setPen(world_pen(skin, 1.4))
        painter.drawPolyline([qt(self.seat), qt(knee), qt(foot)])

    def draw_bow(self, painter: QPainter, p: DragonPalette) -> None:
        """Over the near wing: the bow arm, the bow, the string and a nocked arrow,
        and the drawing hand at the nock."""
        skin = p.skin.lighter(112)
        drake = self.drake
        painter.setPen(world_pen(STRING, 0.35))
        painter.drawPolyline([qt(self.bow[0]), qt(self.nock), qt(self.bow[-1])])
        if drake.bow_draw > 0.15:
            painter.setPen(world_pen(SHAFT, 0.6))
            tip = self.nock + self.aim * 6.5
            painter.drawLine(qt(self.nock), qt(tip))
            painter.setPen(world_pen(STEEL, 0.9))
            painter.drawLine(qt(tip), qt(tip + self.aim * 1.0))
        painter.setPen(world_pen(BOW, 0.9))
        painter.drawPolyline([qt(pt) for pt in self.bow])
        painter.setPen(world_pen(skin, 1.1))
        painter.drawLine(qt(self.shoulder), qt(self.hand))
        painter.drawLine(qt(self.shoulder), qt(self.nock))
