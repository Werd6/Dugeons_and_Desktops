"""Drawing the drow lizard riders, in the dragon's flat style: a teal wall lizard
(its body bending along the displacer's spine, its four legs from the IK rig) with
a cloaked drow on its back holding a hand crossbow; the drow on foot with his two
scimitars; and the drow's bolts, orbs and globes of darkness, with the faerie fire
that outlines everyone caught inside one."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF, QRadialGradient

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.defenders.displacer.actor import along
from dungeons_desktops.game.defenders.displacer.render import _ik, _smooth, _tapered
from dungeons_desktops.game.defenders.drakes.drake import Missile
from dungeons_desktops.game.defenders.drow.actor import (
    BODY_Y,
    CAST_TIME,
    HEAD,
    HIP_Y,
    LEG_X,
    LIZARD_LEGS,
    RIDER_HEAD,
    Drow,
    Lizard,
)
from dungeons_desktops.game.defenders.drow.darkness import GLOBE_RADIUS, GROW_TIME, Darkness
from dungeons_desktops.render.draw import draw_body, draw_strokes, qt, world_pen

SCALES = QColor(44, 112, 118)
SCALES_DARK = QColor(26, 72, 80)
SCALES_FAR = QColor(30, 78, 86)
BELLY = QColor(120, 172, 150)
LIZARD_EYE = QColor(250, 190, 60)
MOUTH = QColor(70, 16, 24)
TONGUE = QColor(214, 70, 96)
BLANKET = QColor(92, 36, 104)
STRAP = QColor(34, 26, 34)
DROW_SKIN = QColor(108, 96, 132)
HAIR = QColor(238, 238, 248)
DROW_EYE = QColor(255, 60, 70)
ARMOR = QColor(46, 38, 60)
LEATHERS = QColor(104, 86, 138)
LEATHERS_FAR = QColor(64, 52, 88)
CLOAK = QColor(48, 26, 68)
CROSSBOW = QColor(150, 98, 58)
CROSSBOW_DARK = QColor(28, 20, 22)
STRING = QColor(214, 210, 200)
STEEL = QColor(196, 204, 222)
DARK = QColor(4, 2, 10)
DARK_RIM = QColor(70, 30, 110)
FAERIE = QColor(206, 130, 255)
FAERIE_CORE = QColor(246, 222, 255)
SWOOSH = QColor(226, 214, 255)

BODY_XS = (-11.0, -8.0, -4.0, 0.0, 4.0, 8.0, 11.0, 14.5)
BODY_HALF = (3.2, 4.0, 4.5, 4.6, 4.5, 4.2, 3.6, 2.8)
"""Its body's half thickness (back to belly) at each of `BODY_XS`."""
TAIL_SEGMENTS = 10
TAIL_SEGMENT = 2.8
SPINES = (-10.0, -7.5, 4.5, 7.0, 9.5, 12.0)
"""Spine ticks along its back, clear of the saddle."""
SADDLE_SPAN = (-5.5, 2.5)


def draw_lizards(
    painter: QPainter, lizards: Iterable[Lizard], outline: QColor | None = None
) -> None:
    for lizard in lizards:
        draw_lizard(painter, lizard, outline)


def draw_drow(painter: QPainter, drow: Iterable[Drow], outline: QColor | None = None) -> None:
    for elf in drow:
        draw_drow_on_foot(painter, elf, outline)


# ----- the lizard ------------------------------------------------------------------------


class _Frame:
    """Its body frame as drawn: rolled belly up as it lies dead."""

    def __init__(self, lizard: Lizard) -> None:
        self.lizard = lizard
        self.roll = smoothstep(clamp(lizard.slump, 0.0, 1.0)) if lizard.dead else 0.0
        self.facing = 1 if lizard.turn >= 0.0 else -1

    def at(self, x: float, y: float) -> Vec2:
        y += (2.0 * BODY_Y + 2.0 - 2.0 * y) * self.roll
        return self.lizard.to_world(Vec2(x, y))

    def up(self, x: float) -> Vec2:
        up = self.lizard.frame_at(x)[1]
        return up if self.roll < 0.5 else -up


def draw_lizard(painter: QPainter, lizard: Lizard, outline: QColor | None = None) -> None:
    """Tail, far legs, body, saddle, near legs, head; then the rider."""
    frame = _Frame(lizard)
    tail = _tail(frame)
    widths = [6.4 * (1.0 - i / len(tail)) + 0.8 for i in range(len(tail))]
    legs = _legs(frame)
    body = _body_path(frame)
    head = _Head(frame)
    rider = _Rider(lizard) if lizard.mounted and not lizard.dead else None

    if outline is not None:
        grow = 1.6
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outline)
        painter.drawPath(_tapered(tail, widths, grow))
        for points, leg_widths, _, _ in legs:
            painter.drawPath(_tapered(points, leg_widths, grow))
        painter.setPen(world_pen(outline, grow))
        painter.drawPath(body)
        painter.drawPath(head.path())
        if rider is not None:
            rider.strokes(painter, outline, 1.4)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(SCALES)
    painter.drawPath(_tapered(tail, widths))
    for points, leg_widths, near, ground in legs:
        if not near:
            _paint_leg(painter, points, leg_widths, ground, SCALES_FAR)
    _paint_body(painter, frame, body)
    _paint_saddle(painter, frame)
    for points, leg_widths, near, ground in legs:
        if near:
            _paint_leg(painter, points, leg_widths, ground, SCALES)
    head.paint(painter)
    if rider is not None:
        rider.paint(painter)
    draw_bolts(painter, lizard.bolts)


def _tail(frame: _Frame) -> list[Vec2]:
    lizard = frame.lizard
    moving = clamp(lizard.speed / 60.0, 0.0, 1.0)
    points = []
    for i in range(TAIL_SEGMENTS + 1):
        u = i / TAIL_SEGMENTS
        sway = math.sin(lizard.time * (2.0 + 4.0 * moving) - i * 0.5) * (0.4 + moving) * u
        points.append(frame.at(-10.0 - i * TAIL_SEGMENT, BODY_Y - 0.4 + 2.4 * u * u + sway))
    return points


def _body_path(frame: _Frame) -> QPainterPath:
    top = [frame.at(x, BODY_Y - h) for x, h in zip(BODY_XS, BODY_HALF, strict=True)]
    belly = [frame.at(x, BODY_Y + h * 0.9) for x, h in zip(BODY_XS, BODY_HALF, strict=True)]
    return _smooth([*top, *reversed(belly)])


def _paint_body(painter: QPainter, frame: _Frame, body: QPainterPath) -> None:
    """Flat scales, a pale belly, and dark spine ticks down its back."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(SCALES)
    painter.drawPath(body)
    painter.save()
    painter.setClipPath(body, Qt.ClipOperation.IntersectClip)
    belly = [frame.at(x, BODY_Y + h * 0.95) for x, h in zip(BODY_XS, BODY_HALF, strict=True)]
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(BELLY, 3.0))
    painter.drawPath(_smooth(belly, closed=False))
    painter.restore()
    painter.setPen(world_pen(SCALES_DARK, 0.8))
    for x in SPINES:
        base = frame.at(x, BODY_Y - _half_at(x) + 0.4)
        up = frame.up(x)
        tip = base + up * 1.8 - along(up) * (frame.facing * 0.8)
        painter.drawLine(qt(base), qt(tip))


def _half_at(x: float) -> float:
    for i in range(len(BODY_XS) - 1):
        if BODY_XS[i] <= x <= BODY_XS[i + 1]:
            t = (x - BODY_XS[i]) / (BODY_XS[i + 1] - BODY_XS[i])
            return BODY_HALF[i] + (BODY_HALF[i + 1] - BODY_HALF[i]) * t
    return BODY_HALF[0] if x < BODY_XS[0] else BODY_HALF[-1]


def _paint_saddle(painter: QPainter, frame: _Frame) -> None:
    if frame.roll > 0.5:
        return
    low, high = SADDLE_SPAN
    xs = [low + (high - low) * k / 4 for k in range(5)]
    top = [frame.at(x, BODY_Y - _half_at(x) - 0.2) for x in xs]
    hem = [frame.at(x, BODY_Y + 0.8) for x in xs]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(BLANKET)
    painter.drawPolygon([qt(p) for p in [*top, *reversed(hem)]])
    painter.setPen(world_pen(STRAP, 0.9))
    painter.drawLine(qt(frame.at(0.5, BODY_Y - 4.4)), qt(frame.at(0.8, BODY_Y + 4.0)))


def _legs(frame: _Frame) -> list[tuple[list[Vec2], list[float], bool, Vec2 | None]]:
    """Hip, knee, foot (and the widths along them) for each leg, and the way up of what
    its foot stands on; dead, they curl up off its upturned belly."""
    lizard = frame.lizard
    shape = LIZARD_LEGS
    legs = []
    for leg in lizard.rig.legs:
        hip, knee, foot = leg.hip, leg.knee, leg.foot
        ground = leg.up if leg.planted or leg.stepping else None
        if frame.roll > 0.0:
            ground = None
            x = LEG_X[leg.outer] + (0.0 if leg.near else 1.5)
            twitch = 0.6 * math.sin(lizard.time * 9.0 + x) * max(0.0, 1.0 - lizard.down_time / 3.0)
            curled_hip = frame.at(x, HIP_Y)
            curled_foot = frame.at(x + (3.0 if leg.outer else -3.0), HIP_Y + 8.0 + twitch)
            bend = -frame.facing if leg.outer else frame.facing
            curled_knee, curled_foot = _ik(curled_hip, curled_foot, shape.upper, shape.lower, bend)
            hip = hip.lerp(curled_hip, frame.roll)
            knee = knee.lerp(curled_knee, frame.roll)
            foot = foot.lerp(curled_foot, frame.roll)
        legs.append(([hip, knee, foot], [3.4, 2.2, 1.4], leg.near, ground))
    return legs


def _paint_leg(
    painter: QPainter,
    points: list[Vec2],
    widths: list[float],
    ground: Vec2 | None,
    color: QColor,
) -> None:
    hip, knee, foot = points
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(_tapered(points, widths))
    if ground is None:
        down = (foot - knee).normalized()
        side = Vec2(-down.y, down.x)
        toes = [(down + side * spread).normalized() for spread in (-0.8, 0.0, 0.8)]
    else:
        side = along(ground)
        if side.dot(foot - knee) < 0.0:
            side = -side
        toes = [(side * spread + ground * 0.2).normalized() for spread in (-0.8, 0.4, 1.0)]
    painter.setPen(world_pen(color, 0.9))
    for toe in toes:
        painter.drawLine(qt(foot), qt(foot + toe * 2.2))


class _Head:
    """A flat wedge of a head like the dragon's: a pale lower jaw that drops open as it
    bites, a bright eye, a flicking tongue."""

    UPPER = ((-3.6, -0.8), (-1.8, -3.0), (2.0, -2.6), (6.6, -0.6), (6.4, 0.8), (-2.6, 1.2))
    LOWER = ((-3.0, 1.0), (6.0, 0.9), (5.4, 2.0), (-2.6, 2.5))

    def __init__(self, frame: _Frame) -> None:
        lizard = frame.lizard
        self.lizard = lizard
        origin = frame.at(HEAD.x + 3.5 * lizard.biting, HEAD.y)
        ax = (origin - frame.at(HEAD.x - 5.0, HEAD.y + 0.3)).normalized()
        down = -frame.up(HEAD.x)
        self.origin, self.ax = origin, ax
        self.down = (down - ax * down.dot(ax)).normalized()
        self.gape = 0.6 * lizard.biting + (0.25 if lizard.dead else 0.0)
        self.spin = 1.0 if ax.cross(self.down) > 0.0 else -1.0

    def at(self, u: float, v: float) -> Vec2:
        return self.origin + self.ax * u + self.down * v

    def jaw(self, u: float, v: float) -> Vec2:
        hinge = Vec2(-2.4, 0.9)
        p = (Vec2(u, v) - hinge).rotated(self.gape * self.spin) + hinge
        return self.at(p.x, p.y)

    def path(self) -> QPainterPath:
        path = QPainterPath()
        path.addPolygon(QPolygonF([qt(self.at(u, v)) for u, v in self.UPPER]))
        path.addPolygon(QPolygonF([qt(self.jaw(u, v)) for u, v in self.LOWER]))
        return path.simplified()

    def paint(self, painter: QPainter) -> None:
        lizard = self.lizard
        at, jaw = self.at, self.jaw
        painter.setPen(Qt.PenStyle.NoPen)
        if self.gape > 0.05:
            painter.setBrush(MOUTH)
            painter.drawPolygon([qt(at(-2.4, 0.9)), qt(at(6.4, 0.8)), qt(jaw(6.0, 0.9))])
        if lizard.dead or (lizard.flick > 0.0 and self.gape <= 0.05):
            out = 3.0 if lizard.dead else 6.5 * math.sin(math.pi * lizard.flick)
            if out > 0.3:
                base = at(6.0, 0.9)
                tip = base + self.ax * out + self.down * (2.0 if lizard.dead else 0.4)
                painter.setPen(world_pen(TONGUE, 0.6))
                painter.drawLine(qt(base), qt(tip))
                for fork in (-0.5, 0.5):
                    painter.drawLine(qt(tip), qt(tip + (self.ax + self.down * fork) * 1.1))
                painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BELLY)
        painter.drawPolygon([qt(jaw(u, v)) for u, v in self.LOWER])
        painter.setBrush(SCALES)
        painter.drawPolygon([qt(at(u, v)) for u, v in self.UPPER])
        painter.setPen(world_pen(SCALES_DARK, 0.7))
        for u in (-2.0, -3.2):
            base = at(u, -2.2 if u > -3.0 else -1.2)
            painter.drawLine(qt(base), qt(base - self.ax * 2.2 - self.down * 1.0))
        eye = at(0.6, -1.3)
        if lizard.dead:
            painter.setPen(world_pen(SCALES_DARK, 0.5))
            painter.drawLine(qt(eye - self.ax * 0.7), qt(eye + self.ax * 0.7))
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(LIZARD_EYE)
        painter.drawEllipse(qt(eye), 0.75, 0.75)


# ----- the rider ---------------------------------------------------------------------------


class _Rider:
    """The drow in the saddle, sitting up off its back whatever it's climbing: a cloak
    hanging toward the ground, white hair, crossbow out on his aim. Stickman proportions
    (same torso, head and limb lengths as an adventurer)."""

    def __init__(self, lizard: Lizard) -> None:
        self.lizard = lizard
        facing = 1 if lizard.turn >= 0.0 else -1
        up = lizard.rider_up
        self.up, self.down = up, -up
        self.ahead = along(up) * facing
        self.seat = lizard.seat
        self.shoulder = lizard.rider_shoulder
        self.head = lizard.rider_head
        ahead, down = self.ahead, self.down
        self.knee = self.seat + ahead * 4.5 + down * 2.5
        self.foot = self.knee + down * 5.5 - ahead * 0.6
        self.aim = lizard.aim
        self.hand = lizard.crossbow
        self.elbow = self.shoulder.lerp(self.hand, 0.5) + down * 1.2
        casting = smoothstep(lizard.cast / CAST_TIME) if lizard.cast > 0.0 else 0.0
        self.casting = casting
        rest = self.shoulder + ahead * 3.5 + down * 4.5
        throw = self.shoulder + (lizard.aim + up * 0.6).normalized() * 7.5
        self.off_hand = rest.lerp(throw, casting)

    def strokes(self, painter: QPainter, color: QColor, grow: float) -> None:
        painter.setPen(world_pen(color, 1.5 + grow))
        painter.drawLine(qt(self.seat), qt(self.shoulder))
        painter.drawPolyline([qt(self.seat), qt(self.knee), qt(self.foot)])
        painter.drawPolyline([qt(self.shoulder), qt(self.elbow), qt(self.hand)])
        painter.drawLine(qt(self.shoulder), qt(self.off_hand))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(qt(self.head), RIDER_HEAD + grow / 2, RIDER_HEAD + grow / 2)

    def paint(self, painter: QPainter) -> None:
        self._cloak(painter)
        painter.setPen(world_pen(ARMOR, 1.5))
        painter.drawLine(qt(self.seat), qt(self.shoulder))
        painter.drawPolyline([qt(self.seat), qt(self.knee), qt(self.foot)])
        self._head(painter)
        painter.setPen(world_pen(DROW_SKIN, 1.5))
        painter.drawLine(qt(self.shoulder), qt(self.off_hand))
        if self.casting > 0.0:
            _orb(painter, self.off_hand + self.up * 0.8, 1.0 + 1.2 * self.casting, [])
        self._crossbow(painter, self.lizard.crossbow_draw)
        painter.setPen(world_pen(DROW_SKIN, 1.5))
        painter.drawPolyline([qt(self.shoulder), qt(self.elbow), qt(self.hand)])

    def _cloak(self, painter: QPainter) -> None:
        """Pinned at his shoulders, falling toward the ground and streaming out behind
        him the faster his lizard runs."""
        lizard = self.lizard
        back = -self.ahead
        stream = clamp(lizard.speed / 120.0, 0.0, 1.0)
        fall = (Vec2(0.0, 1.0) * (1.0 - 0.75 * stream) + back * (0.2 + 1.0 * stream)).normalized()
        across = Vec2(-fall.y, fall.x)
        fold = across * (0.7 * math.sin(lizard.time * (2.4 + 1.6 * stream)))
        top_back = self.shoulder + back * 1.2
        top_front = self.shoulder + self.ahead * 0.5
        length = 11.0 + 2.0 * stream
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(CLOAK)
        painter.drawPolygon(
            [
                qt(top_front),
                qt(top_back),
                qt(top_back + fall * length + back * (1.5 + 2.0 * stream) + fold),
                qt(top_front + fall * (length * 0.9) + fold * 0.4),
            ]
        )

    def _head(self, painter: QPainter) -> None:
        head, ahead, up = self.head, self.ahead, self.up
        back = -ahead
        r = RIDER_HEAD
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(DROW_SKIN)
        painter.drawEllipse(qt(head), r, r)
        painter.setBrush(HAIR)
        cap = r * 1.05
        painter.drawChord(
            QRectF(head.x - cap, head.y - cap, 2 * cap, 2 * cap),
            self._cap_start(),
            int(150 * 16),
        )
        painter.setBrush(DROW_SKIN)
        ear = head + back * 0.1 * r - up * 0.05 * r
        painter.drawPolygon(
            [
                qt(ear - up * 0.3 * r),
                qt(ear + back * 1.05 * r + up * 0.7 * r),
                qt(ear + up * 0.25 * r),
            ]
        )
        painter.setBrush(DROW_EYE)
        painter.drawEllipse(qt(head + ahead * 0.5 * r + up * 0.05 * r), 0.5, 0.5)

    @property
    def _side(self) -> float:
        return 1.0 if self.ahead.x >= 0.0 else -1.0

    def _cap_start(self) -> int:
        """The hair over the top and back of his head: Qt chord angles start at 3
        o'clock and run anticlockwise (on screen), 150 degrees of it."""
        up_angle = math.degrees(math.atan2(-self.up.y, self.up.x))
        start = up_angle - 40.0 if self._side > 0 else up_angle - 110.0
        return int(start * 16)

    def _crossbow(self, painter: QPainter, draw: float) -> None:
        """A hand crossbow in pale wood and steel: a stock along his aim, a steel bow
        across its front (flexed back as it's spanned), the string and a loaded bolt.
        A dark rim keeps it readable over the lizard and the dark cloak."""
        aim, hand = self.aim, self.hand
        across = Vec2(-aim.y, aim.x)
        butt = hand - aim * 2.6
        front = hand + aim * 4.2
        flex = 0.4 + 1.0 * draw
        tips = (front + across * 3.4 - aim * flex, front - across * 3.4 - aim * flex)
        nock = front - aim * (0.4 + 2.4 * draw)
        painter.setPen(world_pen(CROSSBOW_DARK, 2.6))
        painter.drawLine(qt(butt), qt(front))
        painter.setPen(world_pen(CROSSBOW_DARK, 1.8))
        painter.drawPolyline([qt(tips[0]), qt(front), qt(tips[1])])
        painter.setPen(world_pen(STRING, 0.45))
        painter.drawPolyline([qt(tips[0]), qt(nock), qt(tips[1])])
        painter.setPen(world_pen(CROSSBOW, 1.6))
        painter.drawLine(qt(butt), qt(front))
        painter.setPen(world_pen(STEEL, 1.0))
        painter.drawPolyline([qt(tips[0]), qt(front), qt(tips[1])])
        if draw >= 1.0:
            painter.setPen(world_pen(STEEL, 0.6))
            painter.drawLine(qt(nock), qt(front + aim * 1.2))


# ----- the drow on foot ----------------------------------------------------------------


def draw_drow_on_foot(painter: QPainter, drow: Drow, outline: QColor | None = None) -> None:
    """A flowing cape behind him, a stickman-built elf body in dark leathers with white
    hair, a pointed ear and red eye, and his scimitars (a swoosh behind each cut)."""
    facing = drow.facing
    transforms = drow.transforms()
    layout = drow.layout
    head = transforms[layout.head].end
    radius = layout.head_radius
    shoulder = transforms[layout.torso].end
    hip = transforms[layout.torso].start
    weapon = drow.weapon
    strokes = weapon.strokes(transforms, facing)
    held = weapon.held

    _foot_cape(painter, drow, shoulder, hip)
    if not held:
        draw_strokes(painter, strokes)

    def face(_transforms) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(HAIR)
        r = radius * 1.05
        start = 60 if facing > 0 else -30
        painter.drawChord(QRectF(head.x - r, head.y - r, 2 * r, 2 * r), start * 16, 150 * 16)
        painter.setBrush(DROW_SKIN)
        ear = head + Vec2(-facing * 0.1 * radius, 0.05 * radius)
        painter.drawPolygon(
            [
                qt(ear + Vec2(0.0, 0.3 * radius)),
                qt(ear + Vec2(-facing * 1.05 * radius, -0.7 * radius)),
                qt(ear + Vec2(0.0, -0.25 * radius)),
            ]
        )
        painter.setBrush(DROW_EYE)
        painter.drawEllipse(qt(head + Vec2(facing * 0.5 * radius, -0.05 * radius)), 0.5, 0.5)
        if held:
            draw_strokes(painter, strokes)

    draw_body(painter, drow, LEATHERS, LEATHERS_FAR, DROW_SKIN, face, outline=outline)
    if weapon.trail_active:
        _swoosh(painter, drow, transforms)


def _foot_cape(painter: QPainter, drow: Drow, shoulder: Vec2, hip: Vec2) -> None:
    """A long cape from both shoulders: hangs at rest, streams back when he runs, with
    a slow fold so it reads as cloth rather than a frantic flap."""
    facing = drow.facing
    back = Vec2(-facing, 0.0)
    down = Vec2(0.0, 1.0)
    speed = clamp(abs(drow.velocity.x) / 140.0, 0.0, 1.0)
    # Keep a real hang even at full speed so the cape stays a shape, not a ribbon.
    fall = (down * (1.0 - 0.45 * speed) + back * (0.2 + 1.35 * speed)).normalized()
    across = Vec2(-fall.y, fall.x)
    torso = max(6.0, shoulder.distance_to(hip))
    length = torso * (1.85 + 0.4 * speed)
    sway = 0.7 * math.sin(drow.time * (2.0 + 1.2 * speed))
    wave = 1.1 * math.sin(drow.time * (2.6 + 1.5 * speed) + 1.1)
    pin_front = shoulder - back * 0.6 + down * 0.3
    pin_back = shoulder + back * 1.6
    # Fan the hem open so the cape has width along `across` as well as length.
    hem_front = (
        pin_front + fall * (length * 0.88) + across * (-1.2 + 0.4 * sway) + back * (0.5 * speed)
    )
    hem_mid = (
        pin_front.lerp(pin_back, 0.55)
        + fall * (length * 1.02)
        + across * (0.3 * wave)
        + back * (1.5 * speed)
    )
    hem_back = (
        pin_back
        + fall * length
        + across * (1.6 + 0.5 * sway)
        + back * (2.5 * speed)
        + across * (0.4 * wave)
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(CLOAK)
    painter.drawPolygon([qt(pin_front), qt(pin_back), qt(hem_back), qt(hem_mid), qt(hem_front)])
    painter.setBrush(QColor(36, 18, 52))
    painter.drawPolygon(
        [
            qt(pin_front.lerp(pin_back, 0.45)),
            qt(pin_back),
            qt(hem_back.lerp(hem_mid, 0.25)),
            qt(hem_mid),
        ]
    )


def _swoosh(painter: QPainter, drow: Drow, transforms) -> None:
    """A pale arc trailing each blade tip back along its cut."""
    facing = drow.facing
    shoulder = transforms[drow.layout.torso].end
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for tip in drow.weapon.tips(transforms, facing):
        arm = tip - shoulder
        points = [shoulder + arm.rotated(-facing * 0.16 * k) for k in range(6)]
        for k in range(len(points) - 1):
            fade = 1.0 - k / (len(points) - 1)
            painter.setPen(world_pen(_alpha(SWOOSH, 150 * fade), 0.4 + 1.0 * fade))
            painter.drawLine(qt(points[k]), qt(points[k + 1]))


# ----- bolts, darkness and faerie fire -----------------------------------------------------


def draw_bolts(painter: QPainter, bolts: Iterable[Missile]) -> None:
    for bolt in bolts:
        way = bolt.velocity.normalized()
        tail = bolt.position - way * 4.5
        painter.setPen(world_pen(CROSSBOW, 0.7))
        painter.drawLine(qt(tail), qt(bolt.position))
        painter.setPen(world_pen(STEEL, 1.0))
        painter.drawLine(qt(bolt.position), qt(bolt.position + way * 1.0))


def draw_darkness(painter: QPainter, darkness: Darkness, stickmen: Iterable[Stickman] = ()) -> None:
    """The globes (black, soft at the edge, with a violet ring as one bursts), the
    orbs in flight, and faerie fire on everyone caught in one."""
    painter.save()
    for globe in darkness.globes:
        radius = max(1.0, globe.radius)
        strength = globe.strength
        gradient = QRadialGradient(qt(globe.center), radius)
        gradient.setColorAt(0.0, _alpha(DARK, 240 * strength))
        gradient.setColorAt(0.8, _alpha(DARK, 228 * strength))
        gradient.setColorAt(1.0, _alpha(DARK, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(qt(globe.center), radius, radius)
        if globe.age < GROW_TIME * 2.0:
            burst = globe.age / (GROW_TIME * 2.0)
            ring = GLOBE_RADIUS * (0.3 + 0.8 * burst)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(_alpha(FAERIE, 160 * (1.0 - burst)), 1.5))
            painter.drawEllipse(qt(globe.center), ring, ring)
    for orb in darkness.orbs:
        _orb(painter, orb.position, 3.0, orb.trail or [])
    painter.restore()
    draw_faerie_fire(painter, stickmen, darkness.time)


def _orb(painter: QPainter, center: Vec2, radius: float, trail: list[Vec2]) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    for k, point in enumerate(trail[:-1]):
        fade = (k + 1) / len(trail)
        painter.setBrush(_alpha(DARK_RIM, 100 * fade))
        painter.drawEllipse(qt(point), radius * 0.7 * fade, radius * 0.7 * fade)
    painter.setBrush(DARK)
    painter.setPen(world_pen(DARK_RIM, 0.6))
    painter.drawEllipse(qt(center), radius, radius)


def draw_faerie_fire(painter: QPainter, stickmen: Iterable[Stickman], t: float = 0.0) -> None:
    """A flickering violet outline round everyone lit up, and a few motes drifting off."""
    for stickman in stickmen:
        if stickman.faerie <= 0.0:
            continue
        glow = clamp(stickman.faerie / 0.3, 0.0, 1.0) * (0.85 + 0.15 * math.sin(t * 14.0))
        transforms = stickman.transforms()
        layout = stickman.layout
        head = transforms[layout.head].end
        radius = layout.head_radius
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for width, alpha, color in ((2.6, 110, FAERIE), (0.8, 230, FAERIE_CORE)):
            painter.setPen(world_pen(_alpha(color, alpha * glow), width))
            for name, bone in transforms.items():
                if name != layout.head:
                    painter.drawLine(qt(bone.start), qt(bone.end))
            painter.drawEllipse(qt(head), radius, radius)
        center = stickman.center()
        painter.setPen(Qt.PenStyle.NoPen)
        for k in range(3):
            phase = (t * 0.7 + k / 3) % 1.0
            drift = Vec2(5.0 * math.sin(k * 2.3 + t * 1.7), 4.0 - 14.0 * phase)
            painter.setBrush(_alpha(FAERIE_CORE, 200 * glow * math.sin(math.pi * phase)))
            painter.drawEllipse(QPointF(center.x + drift.x, center.y + drift.y), 0.7, 0.7)


def _alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(alpha))))
    return result
