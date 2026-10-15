"""QPainter drawing of the desert hydra, in the dragon's style.

Thick round-capped strokes in one skin colour over an optional fattened outline,
a pale belly stripe, and a handful of accents:
a sparse row of big reddish dorsal spikes, four thick muscled legs on big clawed feet (the
far pair darker, behind). The necks are tapering
tubes of the same skin, each outlined on its own so they read apart, the two
outermost shaded darker as they sit behind. Each head is a blunt wedge skull with a
hinged jaw and two swept-back red crest spikes; the middle one is just bigger.

Whatever of it is in the ground at its hole is clipped away, and a lip of dirt is
drawn over the cut.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.render.breath import ACID, ACID_DARK, draw_acid, draw_motes
from dungeons_desktops.systems.hydra import GLOB_RADIUS, SPACING, Head, Hydra, LegPose, Segment

GLOB_SHINE = QColor(236, 255, 170, 200)

SKIN = QColor(112, 80, 54)
SKIN_DARK = QColor(70, 48, 32)
NECK_SHADES = (
    QColor(86, 61, 41),
    QColor(108, 77, 52),
    QColor(124, 90, 61),
    QColor(98, 70, 47),
    QColor(78, 55, 37),
)
"""Per head, by index; the middle head (2) is lightest, the outer ones darkest."""
BELLY = QColor(226, 204, 156)
CLAW = QColor(240, 230, 204)
FIN = QColor(176, 70, 42)
CREST = QColor(222, 92, 44)
CREST_RED = QColor(184, 48, 36)
MOUTH = QColor(96, 22, 28)
TOOTH = QColor(250, 246, 232)
EYE = QColor(255, 210, 60)
PUPIL = QColor(28, 16, 10)
DIRT = QColor(132, 96, 62)
DIRT_DARK = QColor(84, 58, 36)

NECK_STEPS = 18
"""Samples along each drawn neck curve."""
NECK_WIDTH = (15.0, 10.0)
"""Neck thickness at the chest and at the head (scaled by the head)."""
SPIKE_HEIGHT = (10.0, 4.0)
"""Dorsal spike height at the chest and at the tail."""
SPIKES = (1, 2, 3, 5, 7)
"""The segments with a dorsal spike."""
MUSCLE = 14.0
LIMB_WIDTH = 8.0
TOES = ((7.5, 1.0), (6.0, 0.3), (4.5, -0.5))
"""Length and droop of each toe, nearest first."""
DRAW_ORDER = (0, 4, 1, 3, 2)
"""Back heads first, the big middle one on top."""

SKULL = [(-4.5, -0.5), (-3.5, -4.8), (3.0, -5.2), (8.5, -3.4), (10.5, -0.6), (-3.0, 0.8)]
JAW = [(-3.0, 0.4), (9.5, 0.3), (8.0, 3.0), (-2.5, 3.6)]
HINGE = (-2.0, 0.4)


def _qt(point: Vec2) -> QPointF:
    return QPointF(point.x, point.y)


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _points(points: Iterable[tuple[float, float]]) -> list[QPointF]:
    return [QPointF(x, y) for x, y in points]


def draw_hydras(painter: QPainter, hydras, outline: QColor | None = None) -> None:
    for hydra in hydras:
        draw_hydra(painter, hydra, outline)


def draw_hydra(painter: QPainter, hydra: Hydra, outline: QColor | None = None) -> None:
    draw_motes(painter, hydra.wisps)
    if not hydra.underground and hydra.segments:
        painter.save()
        cut = hydra.cut
        if cut is not None:
            region = QPainterPath()
            region.setFillRule(Qt.FillRule.OddEvenFill)
            region.addRect(QRectF(-1e5, -1e5, 2e5, 2e5))
            region.addRect(QRectF(cut.x, cut.y, cut.width, cut.height))
            painter.setClipPath(region, Qt.ClipOperation.IntersectClip)
        runs = _runs(hydra)
        heads = [hydra.heads[j] for j in DRAW_ORDER]
        if outline is not None:
            _legs(painter, hydra, False, outline)
        _legs(painter, hydra, False, None)
        for head in heads:
            _neck(painter, head, outline)
        if outline is not None:
            _legs(painter, hydra, True, outline)
            _body_strokes(painter, runs, outline, 2.4)
            _spikes(painter, hydra, runs, outline, 1.6)
        _body(painter, hydra, runs)
        _legs(painter, hydra, True, None)
        for head in heads:
            if outline is not None:
                _head(painter, hydra, head, outline)
            _head(painter, hydra, head, None)
        painter.restore()
        if cut is not None and hydra.hole is not None:
            _lip(painter, hydra)
        charge = hydra.glob_charge
        if charge > 0.0:
            mouth = hydra.heads[2].mouth_point
            _blob(painter, mouth + Vec2(0.0, 4.0 * charge), GLOB_RADIUS * charge, 0.0)
    draw_acid(painter, hydra.acid)
    glob = hydra.glob
    if glob is not None:
        _blob(painter, glob.position, GLOB_RADIUS, glob.velocity.y)


def _blob(painter: QPainter, center: Vec2, radius: float, fall: float) -> None:
    """A wobbling glob of acid, stretched out long as it falls fast."""
    if radius < 0.5:
        return
    stretch = 1.0 + min(fall / 900.0, 0.8)
    painter.save()
    painter.translate(_qt(center))
    painter.setPen(_pen(ACID_DARK, 1.6))
    painter.setBrush(ACID)
    path = QPainterPath()
    path.moveTo(QPointF(0.0, radius * stretch))
    path.cubicTo(
        QPointF(radius * 1.1, radius * stretch * 0.6),
        QPointF(radius * 0.9, -radius * 1.2 * stretch),
        QPointF(0.0, -radius * 1.5 * stretch),
    )
    path.cubicTo(
        QPointF(-radius * 0.9, -radius * 1.2 * stretch),
        QPointF(-radius * 1.1, radius * stretch * 0.6),
        QPointF(0.0, radius * stretch),
    )
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(GLOB_SHINE)
    painter.drawEllipse(QPointF(-radius * 0.35, radius * 0.1), radius * 0.22, radius * 0.32)
    painter.restore()


# ----- body -------------------------------------------------------------------------


def _runs(hydra: Hydra) -> list[list[tuple[int, Segment]]]:
    """Unbroken stretches of drawn segments, chest first.

    Arching out of a hole the torso stretches well past `SPACING` between segments;
    it stays one stroke (the clip hides what is still in the ground)."""
    cut = hydra.cut is not None
    runs: list[list[tuple[int, Segment]]] = []
    run: list[tuple[int, Segment]] = []
    for i, s in enumerate(hydra.segments):
        if s.hidden and not (cut and _near_cut(hydra, s.center)):
            if run:
                runs.append(run)
            run = []
            continue
        if run and run[-1][1].center.distance_to(s.center) > SPACING * 6.0:
            runs.append(run)
            run = []
        run.append((i, s))
    if run:
        runs.append(run)
    return runs


def _near_cut(hydra: Hydra, point: Vec2) -> bool:
    hole = hydra.hole
    return hole is not None and point.distance_to(hole.point) < 20.0


def _body_strokes(painter: QPainter, runs, color: QColor, grow: float) -> None:
    for run in runs:
        if len(run) == 1:
            s = run[0][1]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            r = s.radius + grow / 2
            painter.drawEllipse(_qt(s.center), r, r)
            continue
        for (_, a), (_, b) in zip(run, run[1:], strict=False):
            painter.setPen(_pen(color, a.radius + b.radius + grow))
            painter.drawLine(_qt(a.center), _qt(b.center))


def _body(painter: QPainter, hydra: Hydra, runs) -> None:
    _spikes(painter, hydra, runs, None, 0.0)
    _body_strokes(painter, runs, SKIN, 0.0)
    for run in runs:
        for (_, a), (_, b) in zip(run, run[1:], strict=False):
            low_a = a.center - a.normal * (a.radius * 0.5)
            low_b = b.center - b.normal * (b.radius * 0.5)
            painter.setPen(_pen(BELLY, (a.radius + b.radius) * 0.42))
            painter.drawLine(_qt(low_a), _qt(low_b))


def _spike_height(hydra: Hydra, index: int) -> float:
    t = index / max(1, len(hydra.segments) - 1)
    return SPIKE_HEIGHT[0] + (SPIKE_HEIGHT[1] - SPIKE_HEIGHT[0]) * t


def _spikes(painter: QPainter, hydra: Hydra, runs, outline: QColor | None, grow: float) -> None:
    painter.setPen(_pen(outline, grow) if outline is not None else Qt.PenStyle.NoPen)
    painter.setBrush(outline if outline is not None else FIN)
    for run in runs:
        for i, s in run:
            if i not in SPIKES:
                continue
            c, t, n, r = s.center, s.tangent, s.normal, s.radius
            h = _spike_height(hydra, i)
            base = c + n * (r * 0.7)
            spike = [
                base + t * (r * 0.55),
                base + n * (h + 2.0) - t * (h * 0.7),
                base - t * 0.6 * r,
            ]
            painter.drawPolygon([_qt(p) for p in spike])


def _legs(painter: QPainter, hydra: Hydra, near: bool | None, outline: QColor | None) -> None:
    for leg in hydra.legs:
        if near is not None and leg.near != near:
            continue
        if outline is not None:
            _limb(painter, leg, outline, 2.4)
            continue
        color = SKIN if leg.near else SKIN_DARK
        _limb(painter, leg, color, 0.0)
        _claws(painter, leg)


def _toes(leg: LegPose) -> list[tuple[Vec2, Vec2]]:
    """Base and tip of each toe: splayed flat on the ground, curling under as it lifts."""
    base = leg.foot + Vec2(0.0, -1.8)
    forward = leg.forward
    curl = 0.7 * leg.lift * (1.0 if forward.x >= 0.0 else -1.0)
    toes = []
    for length, drop in TOES:
        tip = base + forward.rotated(curl) * length + Vec2(0.0, drop)
        toes.append((base, tip))
    toes.append((base, base - forward * 3.5 + Vec2(0.0, 1.0)))
    return toes


def _limb(painter: QPainter, leg: LegPose, color: QColor, grow: float) -> None:
    """A muscled upper leg tapering to the knee, a thick shin and a big splayed foot."""
    hip, knee = leg.hip, leg.knee
    ankle = leg.foot + Vec2(0.0, -3.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    along = knee - hip
    if along.length() > 1e-6:
        side = along.normalized().rotated(math.pi / 2)
        top, bottom = (MUSCLE + grow) / 2, (LIMB_WIDTH + grow) / 2
        painter.drawPolygon(
            [_qt(hip + side * top), _qt(knee + side * bottom), _qt(knee - side * bottom)]
            + [_qt(hip - side * top)]
        )
        painter.drawEllipse(_qt(hip), top, top)
    painter.setPen(_pen(color, LIMB_WIDTH + grow))
    painter.drawLine(_qt(knee), _qt(ankle))
    painter.setPen(_pen(color, 4.0 + grow))
    for base, tip in _toes(leg):
        painter.drawLine(_qt(base), _qt(tip))


def _claws(painter: QPainter, leg: LegPose) -> None:
    painter.setPen(_pen(CLAW, 1.8))
    down = Vec2(0.0, 1.0)
    for _, tip in _toes(leg)[:-1]:
        painter.drawLine(_qt(tip), _qt(tip + leg.forward * 2.2 + down * 1.4))


# ----- necks and heads ------------------------------------------------------------------


def _skin(head: Head) -> QColor:
    """Each head its own shade, darkest at the back, so the necks read apart."""
    return NECK_SHADES[head.index]


def _neck_width(head: Head, t: float) -> float:
    return (NECK_WIDTH[0] + (NECK_WIDTH[1] - NECK_WIDTH[0]) * t) * (0.8 + 0.2 * head.scale)


def _neck_curve(head: Head) -> list[tuple[Vec2, Vec2]]:
    """Points and unit tangents along one smooth cubic from the chest to the skull.

    The simulated chain only sets where the neck leaves the chest and how long it is;
    the drawn neck is this curve, so it never kinks."""
    neck = head.neck
    out = (neck[min(2, len(neck) - 1)] - neck[0]).normalized()
    root = neck[0] - out * (NECK_WIDTH[0] * 0.9)
    facing = Vec2.from_angle(head.angle, 1.0)
    end = head.position - facing * (3.0 * head.scale)
    pull = max(8.0, root.distance_to(end) * 0.45)
    a, b = root + out * pull, end - facing * pull
    curve = []
    for k in range(NECK_STEPS + 1):
        t = k / NECK_STEPS
        u = 1.0 - t
        point = root * (u**3) + a * (3 * u * u * t) + b * (3 * u * t * t) + end * (t**3)
        tangent = (a - root) * (3 * u * u) + (b - a) * (6 * u * t) + (end - b) * (3 * t * t)
        curve.append((point, tangent.normalized() if tangent.length_sq() > 1e-9 else facing))
    return curve


def _neck_shape(head: Head, grow: float) -> QPainterPath:
    curve = _neck_curve(head)
    left, right = [], []
    for k, (point, tangent) in enumerate(curve):
        half = (_neck_width(head, k / NECK_STEPS) + grow) / 2
        side = tangent.rotated(math.pi / 2) * half
        left.append(point + side)
        right.append(point - side)
    path = QPainterPath(_qt(left[0]))
    for point in left[1:]:
        path.lineTo(_qt(point))
    for point in reversed(right):
        path.lineTo(_qt(point))
    path.closeSubpath()
    return path


def _neck(painter: QPainter, head: Head, outline: QColor | None) -> None:
    if len(head.neck) < 2:
        return
    painter.setPen(_pen(outline, 2.4) if outline is not None else Qt.PenStyle.NoPen)
    painter.setBrush(_skin(head))
    painter.drawPath(_neck_shape(head, 0.0))


def _head(painter: QPainter, hydra: Hydra, head: Head, outline: QColor | None) -> None:
    if len(head.neck) < 2:
        return
    flip = -1.0 if math.cos(head.angle) < 0.0 else 1.0
    s = head.scale
    painter.save()
    painter.translate(_qt(head.position))
    painter.rotate(math.degrees(head.angle))
    painter.scale(s, s * flip)
    skull = _rotate(SKULL, -0.2 * head.mouth)
    jaw = _rotate(JAW, 0.55 * head.mouth)
    if outline is not None:
        painter.setPen(_pen(outline, 2.0 / s * 1.2))
        painter.setBrush(outline)
        _crest(painter, outline)
        painter.drawPolygon(_points(skull))
        painter.drawPolygon(_points(jaw))
        painter.restore()
        return
    _crest(painter, None)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(MOUTH)
    painter.drawPolygon(_points([HINGE, skull[4], jaw[1]]))
    painter.setBrush(TOOTH)
    for x in (4.5, 7.5):
        top = _edge_y(skull, x)
        painter.drawPolygon(_points([(x - 0.7, top), (x + 0.7, top), (x, top + 1.5)]))
    painter.setBrush(_skin(head))
    painter.drawPolygon(_points(jaw))
    painter.drawPolygon(_points(skull))
    painter.setBrush(SKIN_DARK)
    painter.drawPolygon(_points([(-3.5, -4.8), (3.0, -5.2), (1.0, -3.6), (-2.8, -3.4)]))
    painter.setBrush(EYE)
    painter.drawEllipse(QPointF(1.6, -2.2), 1.3, 1.05)
    painter.setBrush(PUPIL if not hydra.dead else SKIN_DARK)
    painter.drawEllipse(QPointF(1.8, -2.2), 0.4, 0.9)
    painter.restore()


def _crest(painter: QPainter, outline: QColor | None) -> None:
    """Two swept-back red spikes behind the skull."""
    plates = [
        [(-1.0, -4.4), (-7.5, -8.6), (0.6, -4.9)],
        [(-3.0, -3.6), (-9.0, -5.2), (-1.8, -4.3)],
    ]
    if outline is None:
        painter.setPen(Qt.PenStyle.NoPen)
    for k, plate in enumerate(plates):
        if outline is None:
            painter.setBrush(CREST if k == 0 else CREST_RED)
        painter.drawPolygon(_points(plate))


def _rotate(points: list[tuple[float, float]], angle: float) -> list[tuple[float, float]]:
    c, s = math.cos(angle), math.sin(angle)
    hx, hy = HINGE
    return [(hx + (x - hx) * c - (y - hy) * s, hy + (x - hx) * s + (y - hy) * c) for x, y in points]


def _edge_y(skull: list[tuple[float, float]], x: float) -> float:
    """Height of the skull's underside (hinge back to snout tip) at `x`."""
    (ax, ay), (bx, by) = skull[5], skull[4]
    t = max(0.0, min(1.0, (x - ax) / (bx - ax)))
    return ay + (by - ay) * t


# ----- the hole -----------------------------------------------------------------------


def _lip(painter: QPainter, hydra: Hydra) -> None:
    """Churned dirt heaped round the hole, over the cut where the body goes in."""
    hole = hydra.hole
    assert hole is not None
    painter.save()
    painter.translate(_qt(hole.point + hole.normal * 0.5))
    painter.rotate(math.degrees(hole.normal.angle()) + 90.0)
    painter.setPen(_pen(DIRT_DARK, 1.0))
    painter.setBrush(DIRT)
    path = QPainterPath(QPointF(-17.0, 0.8))
    path.cubicTo(QPointF(-11.0, -4.6), QPointF(-5.0, -1.6), QPointF(-1.0, -3.6))
    path.cubicTo(QPointF(4.0, -1.4), QPointF(11.0, -4.8), QPointF(17.0, 0.8))
    path.closeSubpath()
    painter.drawPath(path)
    painter.restore()
