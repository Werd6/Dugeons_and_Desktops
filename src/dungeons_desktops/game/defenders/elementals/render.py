"""Drawing the four elementals in the dragon's flat style. Each is a torso, head and
arms rising out of a swirling column of its element that narrows to a tip on the
ground:

- water: a breaking wave hood, foam spiralling down its column and flying spray;
- earth: a hulking heap of rock with huge fists, green crystals and glowing eyes;
- air: a boxer made of wind, narrowing into a tornado as its bands spin faster;
- fire: a horned flame demon with a white-hot heart, claws and flickering edges.

All four share the earth elemental's build (`_torso`): broad hunched shoulders, the
head pushed forward, one heavy arm hanging forward and the other behind.

Everything is drawn in its own frame (facing +x, its ground point at the origin, y
down), leaned and mirrored by the sim (`Elemental.at`). Silhouette shapes are drawn
twice, first stroked in the outline colour, so only their outer edge shows it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF, QTransform

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.game.defenders.elementals.actor import (
    HEIGHT,
    MELEE_RECOVER,
    MELEE_STRIKE,
    MELEE_TIME,
    MELEE_WINDUP,
    RAISED_HAND,
    SCALE,
    ZERO,
    Elemental,
)
from dungeons_desktops.game.defenders.elementals.powers import (
    SLAM_RECOVER,
    BurningPatch,
    Caught,
    FireballShot,
    Shockwave,
    Wave,
)
from dungeons_desktops.render.effects import draw_fire
from dungeons_desktops.render.primitives import qt, world_pen

FIRE_DEEP = QColor(206, 82, 22)
FIRE = QColor(242, 146, 36)
FIRE_LIGHT = QColor(255, 206, 82)
FIRE_CORE = QColor(255, 244, 196)
EMBER = QColor(110, 30, 8)

AIR = QColor(148, 168, 188)
AIR_FAR = QColor(112, 132, 154)
AIR_DARK = QColor(92, 110, 132)
AIR_LIGHT = QColor(212, 224, 236)
DUST = QColor(190, 180, 164)

ROCK = QColor(96, 88, 78)
ROCK_FAR = QColor(66, 60, 54)
ROCK_DARK = QColor(54, 48, 44)
ROCK_LIGHT = QColor(134, 124, 108)
CRYSTAL = QColor(92, 178, 78)
CRYSTAL_LIGHT = QColor(170, 230, 140)
GLOW = QColor(240, 96, 40)

WATER = QColor(64, 132, 188)
WATER_FAR = QColor(42, 92, 142)
WATER_DARK = QColor(34, 74, 120)
WATER_LIGHT = QColor(140, 200, 236)
FOAM = QColor(230, 244, 252)

COLOURS = {"water": WATER_LIGHT, "earth": CRYSTAL, "air": AIR_LIGHT, "fire": FIRE}
"""Each one's colour for its health bar."""


@dataclass
class Look:
    """What to draw, back to front: `shapes` are (path, colour, stroke width or None to
    fill); the ones flagged `solid` get the outline."""

    shapes: list[tuple[QPainterPath, QColor, float | None, bool]] = field(default_factory=list)

    def fill(self, path: QPainterPath, color: QColor, solid: bool = True) -> None:
        self.shapes.append((path, color, None, solid))

    def stroke(self, path: QPainterPath, color: QColor, width: float) -> None:
        self.shapes.append((path, color, width, False))


def draw_elementals(
    painter: QPainter, elementals: Iterable[Elemental], outline: QColor | None = None
) -> None:
    for elemental in elementals:
        draw_elemental(painter, elemental, outline)


def draw_elemental(painter: QPainter, elemental: Elemental, outline: QColor | None = None) -> None:
    # Effects have their own lifetime, including while the owner is underground or dead.
    _effects(painter, elemental)
    if elemental.sunk >= 1.0:
        return
    look = LOOKS[elemental.kind](elemental)
    collapse = smoothstep(elemental.collapse)
    painter.save()
    if elemental.sunk > 0.0:
        painter.setClipRect(
            QRectF(-1e5, -1e5, 2e5, 1e5 + elemental.feet.y + 1.0),
            Qt.ClipOperation.IntersectClip,
        )
    painter.translate(qt(elemental.feet + Vec2(0.0, HEIGHT * 1.5 * elemental.sunk)))
    painter.rotate(math.degrees(elemental.lean * elemental.facing))
    if elemental.dash_way is not None:
        way = elemental.dash_way
        painter.rotate(math.degrees(math.atan2(way.x, -way.y)) * elemental.spin)
    shift = smoothstep(elemental.shifting)
    painter.scale(1.0 - 0.55 * shift, 1.0 - 0.95 * shift)
    painter.scale(
        SCALE * elemental.facing * (1.0 + 0.35 * collapse), SCALE * (1.0 - 0.8 * collapse)
    )
    painter.setOpacity((1.0 - 0.4 * collapse) * (1.0 - elemental.fade))
    if outline is not None:
        painter.setPen(world_pen(outline, 2.4))
        painter.setBrush(outline)
        for path, _, width, solid in look.shapes:
            if solid and width is None:
                painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    for path, color, width, _ in look.shapes:
        if width is None:
            painter.fillPath(path, color)
        else:
            painter.strokePath(path, world_pen(color, width))
    painter.restore()


# ----- shapes ----------------------------------------------------------------------------


def _smooth(points: list[Vec2], samples: int = 6) -> list[Vec2]:
    """A Catmull-Rom curve through `points`."""
    out = []
    padded = [points[0], *points, points[-1]]
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for k in range(samples):
            t = k / samples
            t2, t3 = t * t, t * t * t
            out.append(
                (
                    p1 * 2.0
                    + (p2 - p0) * t
                    + (p0 * 2.0 - p1 * 5.0 + p2 * 4.0 - p3) * t2
                    + (p1 * 3.0 - p0 - p2 * 3.0 + p3) * t3
                )
                * 0.5
            )
    out.append(points[-1])
    return out


def _polygon(points: list[Vec2]) -> QPainterPath:
    path = QPainterPath()
    path.addPolygon(QPolygonF([qt(p) for p in points]))
    path.closeSubpath()
    return path


def _line(points: list[Vec2]) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(qt(points[0]))
    for p in points[1:]:
        path.lineTo(qt(p))
    return path


def _tube(points: list[Vec2], widths: list[float], caps: bool = True) -> QPainterPath:
    """A band of `widths` along the polyline `points`, rounded at its ends."""
    left, right = [], []
    n = len(points)
    for i, p in enumerate(points):
        d = points[min(n - 1, i + 1)] - points[max(0, i - 1)]
        d = d.normalized() if d.length() > 1e-9 else Vec2(0.0, -1.0)
        side = Vec2(-d.y, d.x) * (widths[i] / 2)
        left.append(p + side)
        right.append(p - side)
    path = _polygon(left + right[::-1])
    if caps:
        for i in (0, n - 1):
            cap = QPainterPath()
            cap.addEllipse(qt(points[i]), widths[i] / 2, widths[i] / 2)
            path = path.united(cap)
    return path


def _limb(joints: list[Vec2], widths: list[float]) -> QPainterPath:
    return _tube(_smooth(joints, 5), _spread(widths, (len(joints) - 1) * 5 + 1))


def _spread(widths: list[float], count: int) -> list[float]:
    """`widths` (at evenly spaced stations) interpolated out to `count` stations."""
    out = []
    for i in range(count):
        u = i / (count - 1) * (len(widths) - 1)
        k = min(int(u), len(widths) - 2)
        out.append(widths[k] + (widths[k + 1] - widths[k]) * (u - k))
    return out


def _blob(center: Vec2, rx: float, ry: float, edge=None, count: int = 36) -> QPainterPath:
    """An ellipse whose radius at angle `a` is scaled by `edge(a)`."""
    points = []
    for k in range(count):
        a = math.tau * k / count
        s = edge(a) if edge is not None else 1.0
        points.append(center + Vec2(math.cos(a) * rx * s, math.sin(a) * ry * s))
    return _polygon(points)


def _column(
    elemental: Elemental, waist: Vec2, sway: float, swirl: float, base: float, top: float
) -> tuple[list[Vec2], list[float]]:
    """Its column from the tip on the ground up to `waist`: weaving `sway` either side
    as the swirl climbs at `swirl`, trailing behind as it moves, `base` wide at the
    tip and `top` wide at the waist."""
    t = elemental.clock
    trail = 12.0 * elemental.trail
    points, widths = [], []
    count = 12
    for k in range(count + 1):
        u = k / count
        wave = math.sin(u * 4.0 - t * swirl) * sway * math.sin(math.pi * u)
        x = waist.x * u + wave - trail * (1.0 - u) ** 1.6
        points.append(Vec2(x, waist.y * u))
        widths.append(base + (top - base) * u**0.8)
    return points, widths


def _body_frame(elemental: Elemental, bob_rate: float, bob: float) -> tuple[Vec2, Vec2, Vec2]:
    """Waist, chest and head, bobbing gently."""
    rise = math.sin(elemental.clock * bob_rate) * bob
    return Vec2(-1.0, -24.0 + rise), Vec2(1.0, -36.0 + rise), Vec2(6.0, -46.0 + rise)


def _torso(waist: Vec2, chest: Vec2, edge=None) -> QPainterPath:
    """The earth elemental's build, rounded off: broad shoulders hunched forward,
    narrowing into the column at the waist. `edge(i)` pushes outline point `i` out."""
    points = [
        waist + Vec2(-8.0, 2.0),
        chest + Vec2(-12.0, 3.0),
        chest + Vec2(-12.0, -6.0),
        chest + Vec2(-6.0, -12.0),
        chest + Vec2(4.0, -13.0),
        chest + Vec2(10.0, -8.0),
        chest + Vec2(12.0, 1.0),
        chest + Vec2(7.0, 8.0),
        waist + Vec2(7.0, 2.0),
    ]
    if edge is not None:
        points = [p + (p - chest).normalized() * edge(i) for i, p in enumerate(points)]
    return _polygon(_smooth([*points, points[0]], 4))


def _punch(e: Elemental) -> Vec2:
    """How far a punch has moved its near fist: drawn back through the windup, thrown
    forward in the strike, then brought home."""
    t = e.swing * MELEE_TIME
    if t <= 0.0:
        return ZERO
    back, out = Vec2(-6.0, -3.0), Vec2(11.0, -3.0)
    if t < MELEE_WINDUP:
        return back * smoothstep(t / MELEE_WINDUP)
    t -= MELEE_WINDUP
    if t < MELEE_STRIKE:
        return back.lerp(out, smoothstep(t / MELEE_STRIKE))
    return out * (1.0 - smoothstep((t - MELEE_STRIKE) / MELEE_RECOVER))


def _pushed(arm: list[Vec2], push: Vec2) -> list[Vec2]:
    """`arm` (shoulder, elbow, hand) with its hand moved by `push`."""
    return [arm[0], arm[1] + push * 0.5, arm[2] + push]


def _raised(arm: list[Vec2], hand: Vec2, k: float, elbow_out: Vec2) -> list[Vec2]:
    """`arm` taken `k` of the way to reaching its hand up to `hand`."""
    if k <= 0.0:
        return arm
    elbow = arm[0].lerp(hand, 0.5) + elbow_out
    return [arm[0], arm[1].lerp(elbow, k), arm[2].lerp(hand, k)]


def _windup(e: Elemental) -> float:
    return smoothstep(e.charge)


# ----- water -----------------------------------------------------------------------------


def _water(e: Elemental) -> Look:
    t = e.clock
    look = Look()
    waist, chest, _ = _body_frame(e, 2.0, 1.4)
    face = chest + Vec2(10.0, -8.0)
    column, widths = _column(e, waist, 5.0, 2.8, 2.0, 16.0)
    ripple = math.sin(t * 3.0)
    rear = _windup(e)

    def crest_at(dx: float, dy: float) -> Vec2:
        """A point of the wave on its back, rearing up and over for a surge."""
        return chest + Vec2(dx + 7.0 * rear * -dy / 24.0, dy * (1.0 + 0.6 * rear))

    def drops(near: bool) -> None:
        for k in range(6):
            a = t * 2.0 + k * math.tau / 6
            f = (t * 0.6 + k / 6) % 1.0
            at = chest + Vec2(math.cos(a) * (15.0 + 4.0 * f), math.sin(a) * 4.0 - 4.0 + 10.0 * f)
            if (math.sin(a) >= 0.0) == near:
                look.fill(_blob(at, 1.3, 1.6), WATER_LIGHT if near else WATER_FAR, solid=False)

    drops(near=False)
    far_shoulder = chest + Vec2(-7.0, -6.0)
    far_arm = [far_shoulder, far_shoulder + Vec2(-4.0, 8.0), far_shoulder + Vec2(-2.0, 15.0)]
    look.fill(_limb(far_arm, [7.5, 6.0, 5.0]), WATER_FAR)
    look.fill(_blob(far_arm[-1], 3.8, 3.6), WATER_FAR)

    look.fill(_tube(column, widths), WATER)
    crest = [
        crest_at(-9.0, 0.0),
        crest_at(-14.0, -10.0),
        crest_at(-10.0, -20.0),
        crest_at(0.0, -24.0),
        crest_at(9.0, -22.0 + 0.3 * ripple),
        crest_at(15.0 + ripple, -17.0),
        crest_at(14.0 + ripple, -13.5),
        crest_at(10.0, -15.5),
        crest_at(3.0, -16.0),
        crest_at(-3.0, -12.0),
    ]
    look.fill(_polygon(_smooth([*crest, crest[0]], 4)), WATER)
    look.fill(_torso(waist, chest), WATER)
    look.fill(_blob(face, 6.0, 5.4), WATER)

    look.stroke(
        _line(
            _smooth(
                [
                    crest_at(-11.5, -8.0),
                    crest_at(-8.0, -18.0),
                    crest_at(0.0, -21.5),
                    crest_at(8.0, -20.0),
                ],
                5,
            )
        ),
        WATER_LIGHT,
        2.2,
    )
    for k in range(4):
        foam = crest_at(15.0 + ripple - 1.8 * k, -15.0 - 2.0 * k + 0.4 * k * k)
        look.fill(_blob(foam, 1.8 - 0.25 * k, 1.6 - 0.2 * k), FOAM, solid=False)
    look.stroke(
        _line(
            _smooth(
                [chest + Vec2(-4.0, 6.0), chest + Vec2(-6.0, -2.0), chest + Vec2(-3.0, -8.0)], 4
            )
        ),
        WATER_LIGHT,
        1.6,
    )

    spiral = []
    for k in range(2, len(column) - 2):
        u = k / (len(column) - 1)
        spiral.append(column[k] + Vec2(math.sin(u * 9.0 - t * 4.0) * widths[k] * 0.28, 0.0))
    look.stroke(_line(spiral), WATER_LIGHT, 1.4)

    near_shoulder = chest + Vec2(6.0, -6.0)
    lift = math.sin(t * 2.0) * 1.2
    near_arm = [
        near_shoulder,
        near_shoulder + Vec2(7.0, 6.0),
        near_shoulder + Vec2(13.0, 11.0 + lift),
    ]
    near_arm = _raised(near_arm, chest + Vec2(14.0, -14.0), rear, Vec2(4.0, 3.0))
    near_arm = _pushed(near_arm, _punch(e))
    look.fill(_limb(near_arm, [7.5, 6.0, 5.0]), WATER)
    hand = near_arm[-1] + Vec2(1.0, 0.5)
    look.fill(_blob(hand, 4.4, 4.0), WATER)
    for k in range(3):
        f = (t * 1.5 + k / 3) % 1.0
        splash = hand + Vec2(3.0 + 6.0 * f, -1.0 - 4.0 * f + 6.0 * f * f) + Vec2(0.0, 2.0 * k - 2.0)
        look.fill(_blob(splash, 1.2 * (1.0 - 0.5 * f), 1.4 * (1.0 - 0.5 * f)), FOAM, solid=False)

    drops(near=True)
    look.fill(_blob(face + Vec2(2.6, -0.8), 1.3, 1.1), WATER_DARK, False)
    look.fill(_blob(face + Vec2(-0.6, -0.6), 1.1, 0.9), WATER_DARK, False)
    look.fill(_blob(face + Vec2(2.9, -1.1), 0.45, 0.45), FOAM, False)
    look.stroke(_line([face + Vec2(0.6, 2.4), face + Vec2(4.2, 2.0)]), WATER_DARK, 0.9)
    return look


# ----- earth -----------------------------------------------------------------------------


def _earth(e: Elemental) -> Look:
    t = e.clock
    look = Look()
    waist, chest, head = _body_frame(e, 1.4, 0.8)
    column, widths = _column(e, waist, 3.0, 1.6, 3.0, 14.0)
    lift, slam = _windup(e), 0.0
    special = e.special
    if lift >= 1.0 and special is not None:
        lift, slam = 0.0, 1.0 - smoothstep((special.time - special.windup) / SLAM_RECOVER)

    def fists(arm: list[Vec2], up: Vec2, down: Vec2) -> list[Vec2]:
        """Raised overhead for a slam, then brought down on the ground."""
        arm = _raised(arm, chest + up, lift, Vec2(-3.0, 0.0))
        return _raised(arm, chest + down, slam, Vec2(6.0, -2.0))

    rocks = []
    for k in range(7):
        u = 0.15 + 0.7 * (k / 6)
        a = t * 1.8 + k * 2.4
        i = int(u * (len(column) - 1))
        spot = column[i] + Vec2(math.cos(a) * (widths[i] / 2 + 4.0), math.sin(a) * 2.0)
        rocks.append((spot, math.sin(a) > 0.0, 1.8 + (k % 3) * 0.8, a))

    def rock(at: Vec2, size: float, spin: float) -> QPainterPath:
        return _polygon(
            [
                at + Vec2.from_angle(spin + j * math.tau / 5, size * (0.8 + 0.3 * (j % 2)))
                for j in range(5)
            ]
        )

    for at, near, size, spin in rocks:
        if not near:
            look.fill(rock(at, size, spin), ROCK_FAR, solid=False)

    far_shoulder = chest + Vec2(-7.0, -6.0)
    far_arm = [far_shoulder, far_shoulder + Vec2(-4.0, 8.0), far_shoulder + Vec2(-2.0, 16.0)]
    far_arm = fists(far_arm, Vec2(-1.0, -31.0), Vec2(8.0, 26.0))
    look.fill(_limb(far_arm, [8.0, 7.0, 6.0]), ROCK_FAR)
    look.fill(rock(far_arm[-1] + Vec2(0.0, 2.0), 5.5, 0.4), ROCK_FAR)

    look.fill(_tube(column, widths), ROCK_DARK)
    torso = [
        waist + Vec2(-8.0, 2.0),
        chest + Vec2(-13.0, 4.0),
        chest + Vec2(-12.0, -6.0),
        chest + Vec2(-6.0, -12.0),
        chest + Vec2(4.0, -14.0),
        chest + Vec2(11.0, -9.0),
        chest + Vec2(13.0, 0.0),
        chest + Vec2(8.0, 8.0),
        waist + Vec2(7.0, 2.0),
    ]
    look.fill(_polygon(torso), ROCK)
    look.fill(
        _polygon(
            [
                chest + Vec2(-6.0, -12.0),
                chest + Vec2(4.0, -14.0),
                chest + Vec2(2.0, -6.0),
                chest + Vec2(-7.0, -5.0),
            ]
        ),
        ROCK_LIGHT,
        solid=False,
    )
    look.fill(
        _polygon(
            [
                chest + Vec2(4.0, -2.0),
                chest + Vec2(12.0, 0.0),
                chest + Vec2(8.0, 7.0),
                chest + Vec2(2.0, 5.0),
            ]
        ),
        ROCK_LIGHT,
        solid=False,
    )
    for base, way, size in (
        (chest + Vec2(-10.0, -6.0), Vec2(-0.7, -1.0), 7.0),
        (chest + Vec2(-5.0, -11.0), Vec2(-0.3, -1.0), 5.5),
        (chest + Vec2(-12.0, 0.0), Vec2(-1.0, -0.3), 5.0),
    ):
        way = way.normalized()
        side = Vec2(-way.y, way.x) * 1.8
        look.fill(_polygon([base + side, base + way * size, base - side]), CRYSTAL)
        look.fill(
            _polygon([base + side * 0.2, base + way * size, base - side * 0.9]),
            CRYSTAL_LIGHT,
            solid=False,
        )

    face = chest + Vec2(12.0, -8.0)
    look.fill(
        _polygon(
            [
                face + Vec2(-5.0, -5.0),
                face + Vec2(3.0, -5.5),
                face + Vec2(6.5, -1.5),
                face + Vec2(5.0, 4.5),
                face + Vec2(-3.0, 5.0),
            ]
        ),
        ROCK,
    )
    look.fill(
        _polygon(
            [
                face + Vec2(-3.0, -5.2),
                face + Vec2(3.0, -5.5),
                face + Vec2(6.5, -1.5),
                face + Vec2(-1.0, -2.0),
            ]
        ),
        ROCK_LIGHT,
        False,
    )
    glow = 0.75 + 0.25 * math.sin(t * 3.0)
    eye = QColor(GLOW)
    eye.setAlpha(int(255 * glow))
    look.fill(
        _polygon([face + Vec2(0.5, -1.4), face + Vec2(5.4, -1.0), face + Vec2(1.0, 0.6)]),
        eye,
        False,
    )
    look.stroke(_line([face + Vec2(0.0, 3.0), face + Vec2(4.5, 2.6)]), ROCK_DARK, 1.0)

    for at, near, size, spin in rocks:
        if near:
            look.fill(rock(at, size, spin), ROCK_LIGHT)

    near_shoulder = chest + Vec2(6.0, -6.0)
    sway = math.sin(t * 1.4) * 1.2
    near_arm = [
        near_shoulder,
        near_shoulder + Vec2(6.0, 7.0),
        near_shoulder + Vec2(8.0 + sway, 16.0),
    ]
    near_arm = fists(near_arm, Vec2(8.0, -30.0), Vec2(17.0, 26.0))
    near_arm = _pushed(near_arm, _punch(e))
    look.fill(_limb(near_arm, [9.0, 8.0, 7.0]), ROCK)
    fist = near_arm[-1] + Vec2(0.5, 2.5)
    look.fill(rock(fist, 8.0, 0.2), ROCK)
    look.fill(
        _polygon([fist + Vec2(-2.0, -4.0), fist + Vec2(4.0, -3.5), fist + Vec2(2.0, 0.0)]),
        ROCK_LIGHT,
        False,
    )
    return look


# ----- air -------------------------------------------------------------------------------


def _air(e: Elemental) -> Look:
    t = e.clock
    look = Look()
    waist, chest, _ = _body_frame(e, 2.4, 1.5)
    face = chest + Vec2(10.0, -9.0)
    column, widths = _column(e, waist, 4.0 * (1.0 - 0.6 * e.spin), 3.5, 2.0, 16.0)
    pump = math.sin(t * 2.4) * 1.2
    spin = e.spin
    special = e.special
    whirl = t * 0.45 + (2.5 * special.time**1.5 if spin > 0.0 and special is not None else 0.0)
    """Where its bands of wind are in their climb (racing round as it spins up)."""
    widths = [w * (1.0 + 1.1 * spin * (i / (len(widths) - 1)) ** 1.5) for i, w in enumerate(widths)]
    tuck = chest + Vec2(0.0, -4.0)

    def tucked(arm: list[Vec2]) -> list[Vec2]:
        """Pulled in to its body as it spins into a tornado."""
        return [p.lerp(tuck, 0.85 * spin) for p in arm]

    for k in range(4):
        f = (t * 0.9 + k / 4) % 1.0
        side = 1.0 if k % 2 else -1.0
        grow = 1.0 + spin
        puff = column[0] + Vec2(side * (4.0 + 12.0 * f) * grow, -1.5 - 4.0 * f)
        colour = QColor(DUST)
        colour.setAlpha(int(200 * (1.0 - f)))
        look.fill(_blob(puff, (3.0 + 3.0 * f) * grow, 2.0 + 2.0 * f), colour, solid=False)

    far_arm = tucked(
        [
            chest + Vec2(-4.0, -8.0),
            chest + Vec2(-9.0, -17.0),
            chest + Vec2(-2.0, -25.0 - pump),
        ]
    )
    look.fill(_limb(far_arm, [7.5, 6.5, 5.5]), AIR_FAR)
    look.fill(_blob(far_arm[-1], 5.2 * (1.0 - 0.5 * spin), 4.8 * (1.0 - 0.5 * spin)), AIR_FAR)

    narrow = QTransform()
    narrow.translate(chest.x, chest.y)
    narrow.scale(1.0 - 0.6 * spin, 1.0)
    narrow.translate(-chest.x, -chest.y)
    look.fill(_tube(column, widths), AIR)
    look.fill(narrow.map(_torso(waist, chest)), AIR)
    look.fill(narrow.map(_blob(face, 5.6, 5.2)), AIR)

    for k in range(7):
        f = (k / 7 + whirl) % 1.0
        i = int(f * (len(column) - 1))
        if i < 1 or i > len(column) - 3:
            continue
        centre, width = column[i], widths[i]
        band = [
            centre + Vec2(-width / 2, -1.0),
            centre + Vec2(0.0, 1.6),
            centre + Vec2(width / 2, -1.0),
        ]
        look.stroke(_line(_smooth(band, 4)), AIR_DARK if k % 2 else AIR_LIGHT, 1.3)
    for k in range(4):
        f = (k / 4 + whirl) % 1.0
        y = chest.y + 8.0 - 19.0 * f
        half = (
            10.5 * (1.0 - 0.6 * spin) * math.sqrt(max(0.0, 1.0 - ((y - chest.y + 2.0) / 12.0) ** 2))
        )
        band = [
            Vec2(chest.x - half, y - 1.0),
            Vec2(chest.x, y + 2.0),
            Vec2(chest.x + half, y - 1.0),
        ]
        look.stroke(_line(_smooth(band, 4)), AIR_DARK if k % 2 else AIR_LIGHT, 1.3)

    near_arm = [chest + Vec2(7.0, -5.0), chest + Vec2(14.0, 3.0), chest + Vec2(22.0, -1.0 + pump)]
    near_arm = tucked(_pushed(near_arm, _punch(e)))
    look.fill(_limb(near_arm, [8.0, 6.5, 5.5]), AIR)
    fist = near_arm[-1]
    look.fill(_blob(fist, 5.4 * (1.0 - 0.5 * spin), 5.0 * (1.0 - 0.5 * spin)), AIR)
    for k in range(3):
        f = (k / 3 + t * 0.9) % 1.0
        at = near_arm[0].lerp(near_arm[1], f) if f < 0.5 else near_arm[1].lerp(fist, f)
        look.stroke(_line([at + Vec2(-2.4, -1.4), at + Vec2(2.4, 1.4)]), AIR_DARK, 1.1)

    for k in range(3):
        a = t * 2.6 + k * math.tau / 3
        pebble = chest + Vec2(math.cos(a) * 15.0, 6.0 + math.sin(a) * 3.0)
        if math.sin(a) > 0.0:
            look.fill(_blob(pebble, 1.3, 1.1), AIR_DARK, solid=False)

    if spin < 0.6:
        look.fill(narrow.map(_blob(face + Vec2(2.6, -0.6), 1.2, 0.9)), AIR_LIGHT, False)
        look.fill(narrow.map(_blob(face + Vec2(-0.4, -0.6), 1.0, 0.8)), AIR_LIGHT, False)
    return look


# ----- fire ------------------------------------------------------------------------------


def _fire(e: Elemental) -> Look:
    t = e.clock
    look = Look()
    waist, chest, _ = _body_frame(e, 3.0, 1.2)
    face = chest + Vec2(11.0, -9.0)
    flick = math.sin(t * 9.0)

    def flicker(phase: float, amount: float):
        return lambda a: 1.0 + amount * math.sin(a * 5.0 + t * 11.0 + phase)

    column, widths = _column(e, waist, 6.0, 2.2, 2.0, 16.0)
    swoosh = [Vec2(-24.0 - 6.0 * e.trail, -3.0 - 1.5 * flick), Vec2(-13.0, -0.5), column[0]]
    lead = _smooth(swoosh, 3)[:-1]
    spine = lead + column
    tail_widths = _spread([0.6, 1.4, widths[0]], len(lead) + 1)[:-1] + widths
    tail_widths = [
        w * (1.0 + 0.12 * math.sin(i * 1.9 + t * 12.0)) for i, w in enumerate(tail_widths)
    ]

    far_shoulder = chest + Vec2(-7.0, -6.0)
    far_arm = [far_shoulder, far_shoulder + Vec2(-4.0, 8.0), far_shoulder + Vec2(-1.0, 15.0)]
    look.fill(_limb(far_arm, [8.0, 6.5, 5.0]), FIRE_DEEP)
    look.fill(_blob(far_arm[-1], 4.0, 3.6), FIRE_DEEP)
    horn = face + Vec2(-4.0, -3.0)
    look.fill(
        _limb([horn, horn + Vec2(-5.0, -5.0), horn + Vec2(-11.0, -5.0 + flick)], [3.4, 2.2, 0.6]),
        FIRE_DEEP,
    )

    look.fill(_tube(spine, tail_widths), FIRE)
    look.fill(_torso(waist, chest, lambda i: 0.6 * math.sin(t * 11.0 + i * 2.3)), FIRE)
    for k in range(4):
        root = (chest + Vec2(-11.5, -1.0)).lerp(chest + Vec2(-2.0, -12.0), k / 3)
        sway = math.sin(t * 8.0 + k * 1.7)
        tip = root + Vec2(-7.0 + 2.0 * sway, -7.0 - 2.0 * k - 2.0 * math.sin(t * 6.0 + k))
        look.fill(_polygon([root + Vec2(-2.5, 1.5), tip, root + Vec2(2.5, -1.0)]), FIRE)
    look.fill(_blob(face, 6.0, 5.4, flicker(2.0, 0.06)), FIRE)
    horn = face + Vec2(-1.5, -4.0)
    look.fill(
        _limb([horn, horn + Vec2(-3.0, -5.0), horn + Vec2(-8.0, -8.0 + flick)], [3.6, 2.4, 0.6]),
        FIRE_DEEP,
    )

    look.fill(_tube(column[3:], [w * 0.4 for w in widths[3:]]), FIRE_LIGHT, solid=False)
    heart = [
        waist + Vec2(-4.5, 1.0),
        chest + Vec2(-6.5, 1.0),
        chest + Vec2(-4.0, -6.0),
        chest + Vec2(0.5, -10.0 + 1.5 * flick),
        chest + Vec2(4.0, -4.0),
        chest + Vec2(4.5, 3.0),
        waist + Vec2(3.5, 1.0),
    ]
    look.fill(_polygon(_smooth([*heart, heart[0]], 4)), FIRE_LIGHT, solid=False)
    look.fill(_blob(chest + Vec2(-0.5, 1.0), 2.8, 4.5, flicker(1.0, 0.1)), FIRE_CORE, solid=False)

    near_shoulder = chest + Vec2(6.0, -6.0)
    reach = math.sin(t * 2.0) * 1.2
    near_arm = [
        near_shoulder,
        near_shoulder + Vec2(7.0, 6.0),
        near_shoulder + Vec2(9.0 + reach, 15.0),
    ]
    near_arm = _raised(near_arm, RAISED_HAND, _windup(e), Vec2(6.0, 0.0))
    near_arm = _pushed(near_arm, _punch(e))
    hand = near_arm[-1] + Vec2(0.5, 1.5)
    if e.charge > 0.0:
        look.fill(_blob(hand + Vec2(0.0, -7.0), 5.0 * e.charge, 7.0 * e.charge), FIRE_LIGHT)
        look.fill(_blob(hand + Vec2(0.0, -7.0), 2.5 * e.charge, 4.0 * e.charge), FIRE_CORE)
    for k in range(3):
        claw = hand + Vec2(-2.0 + 2.2 * k, 2.5)
        look.fill(
            _polygon(
                [claw + Vec2(-1.3, -1.0), claw + Vec2(1.0 + 0.4 * k, 5.0), claw + Vec2(1.3, -1.0)]
            ),
            FIRE,
        )
    look.fill(_limb(near_arm, [8.0, 6.5, 5.5]), FIRE)
    look.fill(_blob(hand, 4.6, 4.0), FIRE)
    elbow = near_arm[1]
    look.fill(
        _polygon(
            [elbow + Vec2(-3.0, -1.0), elbow + Vec2(-7.0, -7.0 + flick), elbow + Vec2(0.5, -3.0)]
        ),
        FIRE,
    )

    look.fill(
        _polygon([face + Vec2(1.0, -2.4), face + Vec2(5.6, -1.4), face + Vec2(1.6, -0.6)]),
        EMBER,
        False,
    )
    look.fill(
        _polygon([face + Vec2(1.0, 1.8), face + Vec2(5.8, 1.2), face + Vec2(2.6, 3.0)]),
        EMBER,
        False,
    )
    return look


LOOKS = {"water": _water, "earth": _earth, "air": _air, "fire": _fire}


def _effects(painter: QPainter, elemental: Elemental) -> None:
    """World-space effects stay independent of the body's transforms and opacity."""
    painter.save()
    for effect in elemental.effects:
        if isinstance(effect, Wave):
            painter.save()
            painter.translate(effect.x, effect.y)
            painter.scale(effect.direction, max(0.05, effect.size))
            crest = QPainterPath()
            crest.moveTo(-28.0, 0.0)
            crest.cubicTo(-20.0, -12.0, -15.0, -40.0, 3.0, -35.0)
            crest.cubicTo(20.0, -32.0, 15.0, -18.0, 5.0, -21.0)
            crest.cubicTo(14.0, -12.0, 12.0, -4.0, 19.0, 0.0)
            crest.closeSubpath()
            painter.fillPath(crest, WATER)
            painter.strokePath(crest, world_pen(WATER_LIGHT, 2.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(FOAM)
            for k in range(5):
                painter.drawEllipse(qt(Vec2(2.0 + k * 2.5, -34.0 + k * 2.0)), 2.3, 1.8)
            painter.restore()
        elif isinstance(effect, Shockwave):
            for side in (-1, 1):
                end = max(effect.low, min(effect.high, effect.x + side * effect.radius))
                points = [
                    Vec2(effect.x + (end - effect.x) * k / 12, effect.y - (k % 2) * 3)
                    for k in range(13)
                ]
                painter.strokePath(_line(points), world_pen(ROCK_LIGHT, 2.5))
                painter.strokePath(_line(points), world_pen(CRYSTAL, 1.0))
        elif isinstance(effect, (FireballShot, BurningPatch)):
            draw_fire(painter, effect.flames)
            if isinstance(effect, FireballShot) and not effect.burst:
                painter.setPen(world_pen(FIRE, 2.0))
                painter.setBrush(FIRE_LIGHT)
                painter.drawEllipse(qt(effect.position), 6.0, 6.0)
                painter.setBrush(FIRE_CORE)
                painter.drawEllipse(qt(effect.position), 3.0, 3.0)
        elif isinstance(effect, Caught):
            center = effect.stickman.center()
            for k in range(3):
                y = center.y - 12.0 + k * 10.0
                points = [
                    Vec2(center.x - 15.0, y),
                    Vec2(center.x, y + 4.0),
                    Vec2(center.x + 15.0, y - 2.0),
                ]
                painter.strokePath(_line(_smooth(points)), world_pen(AIR_LIGHT, 1.5))
    painter.restore()
