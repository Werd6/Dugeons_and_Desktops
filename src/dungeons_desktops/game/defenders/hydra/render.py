"""QPainter drawing of the desert hydra, in the dragon's style.

Thick round-capped strokes in one skin colour over an optional fattened outline,
a pale belly stripe, and a handful of accents:
a ridge of reddish dorsal spikes down the back and tail, four thick muscled legs on big
clawed feet (the far pair darker, behind). Necks share the body skin colour. Bases are filled under the
chest (no outline); free necks and heads are drawn in front with outline clipped away
where they sit inside the body silhouette. Accents (mouth, teeth, eye) are painted on
after. The middle head is just bigger.

Whatever of it is in the ground at its hole is clipped away, and a lip of dirt is
drawn over the cut.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.hydra.actor import (
    GLOB_RADIUS,
    SPACING,
    Head,
    Hydra,
    LegPose,
    Segment,
)
from dungeons_desktops.game.effects.render import (
    ACID,
    ACID_DARK,
    VENOM,
    VENOM_DARK,
    VENOM_HAZE,
    VENOM_SHINE,
    draw_acid,
    draw_motes,
)
from dungeons_desktops.render.chromatic import chromatic_appearance

GLOB_SHINE = QColor(236, 255, 170, 200)

SKIN = QColor(112, 80, 54)
SKIN_DARK = QColor(70, 48, 32)
BELLY = QColor(226, 204, 156)
CLAW = QColor(240, 230, 204)
FIN = QColor(176, 70, 42)
CREST = QColor(222, 92, 44)
"""Menu accent colour for the hydra (not drawn on the creature)."""
LEGENDARY_GOLD = QColor(255, 210, 72)
LEGENDARY_ACID = VENOM
LEGENDARY_ACID_DARK = VENOM_DARK
LEGENDARY_ACID_HAZE = VENOM_HAZE
MOUTH = QColor(96, 22, 28)
TOOTH = QColor(250, 246, 232)
EYE = QColor(255, 210, 60)
DIRT = QColor(132, 96, 62)
DIRT_DARK = QColor(84, 58, 36)

NECK_STEPS = 18
"""Samples along each drawn neck curve."""
NECK_WIDTH = (15.0, 10.0)
"""Neck thickness at the chest and at the head (scaled by the head)."""
SPIKE_HEIGHT = (10.0, 6.5)
"""Dorsal spike height at the chest and at the tip of the tail."""
SPIKES = (1, 2, 3, 4, 5, 6, 7, 8, 9)
"""Dorsal spikes from the shoulders down the full tail."""
MUSCLE = 14.0
LIMB_WIDTH = 8.0
TOES = ((7.5, 1.0), (6.0, 0.3), (4.5, -0.5))
"""Length and droop of each toe, nearest first."""
DRAW_ORDER = (0, 4, 2, 1, 3)
"""Outer backs first, big middle third, nearer pair on top."""
BASE_CAP = 8
"""Samples on the round semicircle that closes each neck at the chest."""

SKULL = [(-4.2, -0.4), (-3.2, -3.6), (1.5, -4.2), (6.5, -3.6), (9.8, -1.8), (10.5, -0.6), (-3.0, 0.8)]
"""Smooth crown with no horn peaks."""
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


@chromatic_appearance
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
        body = _body_path(runs)
        if outline is not None:
            _legs(painter, hydra, False, outline)
        _legs(painter, hydra, False, None)
        # Neck fills under the chest; free necks + heads redraw in front without body borders.
        for head in heads:
            _neck_under(painter, head)
        if outline is not None:
            _legs(painter, hydra, True, outline)
            _body_strokes(painter, runs, outline, 2.4)
            _spikes(painter, hydra, runs, outline, 1.6)
        _body(painter, hydra, runs)
        _legs(painter, hydra, True, None)
        painter.save()
        world = QPainterPath()
        world.addRect(QRectF(-1e5, -1e5, 2e5, 2e5))
        painter.setClipPath(world.subtracted(body), Qt.ClipOperation.IntersectClip)
        for head in heads:
            _neck_head(painter, hydra, head, outline)
        painter.restore()
        painter.restore()
        if cut is not None and hydra.hole is not None:
            _lip(painter, hydra)
        charge = hydra.glob_charge
        if charge > 0.0:
            mouth = hydra.heads[2].mouth_point
            _blob(
                painter,
                mouth + Vec2(0.0, 4.0 * charge),
                GLOB_RADIUS * charge,
                0.0,
                legendary=getattr(hydra, "legendary", False),
            )
    legendary = getattr(hydra, "legendary", False)
    if legendary:
        draw_acid(
            painter,
            hydra.acid,
            haze=LEGENDARY_ACID_HAZE,
            core=LEGENDARY_ACID,
            dark=LEGENDARY_ACID_DARK,
        )
    else:
        draw_acid(painter, hydra.acid)
    glob = hydra.glob
    if glob is not None:
        _blob(painter, glob.position, GLOB_RADIUS, glob.velocity.y, legendary=legendary)


def _blob(
    painter: QPainter,
    center: Vec2,
    radius: float,
    fall: float,
    *,
    legendary: bool = False,
) -> None:
    """A wobbling glob of acid, stretched out long as it falls fast."""
    if radius < 0.5:
        return
    stretch = 1.0 + min(fall / 900.0, 0.8)
    core = LEGENDARY_ACID if legendary else ACID
    dark = LEGENDARY_ACID_DARK if legendary else ACID_DARK
    shine = VENOM_SHINE if legendary else GLOB_SHINE
    painter.save()
    painter.translate(_qt(center))
    painter.setPen(_pen(dark, 1.6))
    painter.setBrush(core)
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
    painter.setBrush(shine)
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


def _body_path(runs, grow: float = 0.0) -> QPainterPath:
    """Filled silhouette of the trail body, used to keep neck outlines off the chest."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for run in runs:
        if not run:
            continue
        if len(run) == 1:
            s = run[0][1]
            r = s.radius + grow / 2
            path.addEllipse(_qt(s.center), r, r)
            continue
        for (_, a), (_, b) in zip(run, run[1:], strict=False):
            stroke = QPainterPath()
            stroke.moveTo(_qt(a.center))
            stroke.lineTo(_qt(b.center))
            stroker = QPainterPathStroker()
            stroker.setWidth(a.radius + b.radius + grow)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            path.addPath(stroker.createStroke(stroke))
    return path


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
    fill = (
        outline
        if outline is not None
        else (LEGENDARY_GOLD if getattr(hydra, "legendary", False) else FIN)
    )
    painter.setBrush(fill)
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


def _neck_width(head: Head, t: float) -> float:
    return (NECK_WIDTH[0] + (NECK_WIDTH[1] - NECK_WIDTH[0]) * t) * (0.8 + 0.2 * head.scale)


def _head_flip(head: Head) -> float:
    return -1.0 if math.cos(head.angle) < 0.0 else 1.0


def _head_local(head: Head, local: tuple[float, float]) -> Vec2:
    """Head-local (x, y) into world space (same transform the accent draw uses)."""
    s = head.scale
    flip = _head_flip(head)
    lx, ly = s * local[0], s * flip * local[1]
    return head.position + Vec2(lx, ly).rotated(head.angle)


def _neck_curve(head: Head) -> list[tuple[Vec2, Vec2]]:
    """Points and unit tangents along one smooth cubic from the chest into the skull.

    The simulated chain only sets where the neck leaves the chest and how long it is;
    the drawn neck is this curve, so it never kinks. The tip lands inside the skull so
    the united skin path has no seam at the hinge.
    """
    neck = head.neck
    out = (neck[min(2, len(neck) - 1)] - neck[0]).normalized()
    # Only a short tuck under the body fill — long pull made a fat knob on the chest.
    root = neck[0] - out * (NECK_WIDTH[0] * 0.65)
    facing = Vec2.from_angle(head.angle, 1.0)
    end = head.position - facing * (1.2 * head.scale)
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


def _poly_path(points: list[Vec2]) -> QPainterPath:
    path = QPainterPath(_qt(points[0]))
    for point in points[1:]:
        path.lineTo(_qt(point))
    path.closeSubpath()
    return path


def _neck_ribbon(head: Head, grow: float = 0.0) -> QPainterPath:
    """Tapering neck tube with a round semicircle cap at the chest (no flat corners)."""
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
    # Round base: semicircle from right[0] back to left[0], away from the tip.
    center, tangent = curve[0]
    offset = right[0] - center
    toward_back = -tangent
    ccw = offset.rotated(0.2).dot(toward_back)
    cw = offset.rotated(-0.2).dot(toward_back)
    sign = 1.0 if ccw >= cw else -1.0
    for i in range(1, BASE_CAP):
        path.lineTo(_qt(center + offset.rotated(sign * math.pi * i / BASE_CAP)))
    path.closeSubpath()
    return path


def _skin_path(
    head: Head,
    skull: list[tuple[float, float]],
    jaw: list[tuple[float, float]],
) -> QPainterPath:
    """One filled silhouette: round-capped neck united with skull and jaw."""
    path = _neck_ribbon(head)
    path = path.united(_poly_path([_head_local(head, p) for p in skull]))
    path = path.united(_poly_path([_head_local(head, p) for p in jaw]))
    return path


def _neck_under(painter: QPainter, head: Head) -> None:
    """Neck fill only, under the body, so the chest join stays seamless."""
    if len(head.neck) < 2:
        return
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(SKIN)
    painter.drawPath(_neck_ribbon(head))


def _neck_head(painter: QPainter, hydra: Hydra, head: Head, outline: QColor | None) -> None:
    """Draw one neck+head as a single skin path, then paint face accents on top."""
    if len(head.neck) < 2:
        return
    skull = _rotate(SKULL, -0.2 * head.mouth)
    jaw = _rotate(JAW, 0.55 * head.mouth)
    skin = _skin_path(head, skull, jaw)
    painter.setPen(_pen(outline, 2.4) if outline is not None else Qt.PenStyle.NoPen)
    painter.setBrush(SKIN)
    painter.drawPath(skin)
    _face(painter, hydra, head, skull, jaw)


def _face(
    painter: QPainter,
    hydra: Hydra,
    head: Head,
    skull: list[tuple[float, float]],
    jaw: list[tuple[float, float]],
) -> None:
    """Mouth, teeth and eye in head-local space (on top of the united skin)."""
    painter.save()
    painter.translate(_qt(head.position))
    painter.rotate(math.degrees(head.angle))
    painter.scale(head.scale, head.scale * _head_flip(head))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(MOUTH)
    painter.drawPolygon(_points([HINGE, skull[5], jaw[1]]))
    painter.setBrush(TOOTH)
    for x in (4.5, 7.5):
        top = _edge_y(skull, x)
        painter.drawPolygon(_points([(x - 0.7, top), (x + 0.7, top), (x, top + 1.5)]))
    for x in (4.5, 7.5):
        ridge = _jaw_y(jaw, x)
        painter.drawPolygon(_points([(x - 0.65, ridge), (x + 0.65, ridge), (x, ridge - 1.35)]))
    painter.setBrush(EYE if not hydra.dead else SKIN_DARK)
    painter.drawEllipse(QPointF(1.6, -2.2), 1.3, 1.05)
    painter.restore()


def _rotate(points: list[tuple[float, float]], angle: float) -> list[tuple[float, float]]:
    c, s = math.cos(angle), math.sin(angle)
    hx, hy = HINGE
    return [(hx + (x - hx) * c - (y - hy) * s, hy + (x - hx) * s + (y - hy) * c) for x, y in points]


def _edge_y(skull: list[tuple[float, float]], x: float) -> float:
    """Height of the skull's underside (hinge back to snout tip) at `x`."""
    (ax, ay), (bx, by) = skull[6], skull[5]
    t = max(0.0, min(1.0, (x - ax) / (bx - ax)))
    return ay + (by - ay) * t


def _jaw_y(jaw: list[tuple[float, float]], x: float) -> float:
    """Height of the jaw's top edge (hinge to snout) at `x`."""
    (ax, ay), (bx, by) = jaw[0], jaw[1]
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
