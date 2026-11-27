"""Procedural aboleth: layered body shapes, fins, three eyes, solid tentacle ribbons."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.game.defenders.aboleth.actor import (
    SLIME_BURST_TIME,
    SLIME_RADIUS,
    WHIP_ROOTS,
    WHIP_TRAIL_LIFE,
    Aboleth,
    whip_kinematics,
)
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.primitives import alpha, qt, world_pen

BODY = QColor(122, 154, 120)
BODY_MID = QColor(104, 138, 108)
BODY_SHADE = QColor(78, 108, 86)
BODY_BELLY = QColor(148, 168, 138)
BODY_EDGE = QColor(36, 48, 40)
FIN = QColor(184, 176, 122)
FIN_EDGE = QColor(90, 86, 52)
TENTACLE_SAGE = QColor(110, 148, 112)
TENTACLE_SAGE_EDGE = QColor(52, 78, 56)
TENTACLE_SAGE_FAR = QColor(86, 118, 90)
TENTACLE_PURPLE = QColor(139, 107, 138)
TENTACLE_PURPLE_EDGE = QColor(72, 48, 74)
TENTACLE_PURPLE_FAR = QColor(112, 84, 112)
TENTACLE_RIB = QColor(60, 40, 64, 170)
SOCKET = QColor(28, 22, 24)
EYE = QColor(232, 90, 42)
EYE_CHARGE = QColor(255, 30, 24)
EYE_GLOW = QColor(255, 140, 70)
EYE_CHARGE_GLOW = QColor(255, 60, 40)
EYE_SHINE = QColor(255, 230, 190)
PSYCHIC = QColor(220, 50, 70)
PSYCHIC_CORE = QColor(255, 180, 160)
SLIME = QColor(90, 190, 70)
SLIME_CORE = QColor(180, 240, 120)

UPPER_SEGMENTS = 8
LOWER_SEGMENTS = 10
# Roots in local space — shared with actor whip kinematics.
UPPER_ROOTS = WHIP_ROOTS[:2]
LOWER_ROOTS = WHIP_ROOTS[2:]


def _smooth(points: list[Vec2], samples: int = 5) -> QPainterPath:
    """Closed Catmull-Rom silhouette through `points`."""
    if len(points) < 3:
        path = QPainterPath(qt(points[0]))
        for point in points[1:]:
            path.lineTo(qt(point))
        path.closeSubpath()
        return path
    padded = [points[-1], *points, points[0], points[1]]
    path = QPainterPath()
    first = True
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            point = (
                p1 * 2
                + (p2 - p0) * t
                + (p0 * 2 - p1 * 5 + p2 * 4 - p3) * t2
                + (p1 * 3 - p0 - p2 * 3 + p3) * t3
            ) * 0.5
            if first:
                path.moveTo(qt(point))
                first = False
            else:
                path.lineTo(qt(point))
    path.closeSubpath()
    return path


def _area(points: list[QPointF]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:] + points[:1], strict=True):
        total += a.x() * b.y() - b.x() * a.y()
    return total


def _tapered(points: list[Vec2], widths: list[float], grow: float = 0.0) -> QPainterPath:
    """Solid ribbon: polygon + joint disks, wound so they union (no ethereal holes)."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    left: list[QPointF] = []
    right: list[QPointF] = []
    last = len(points) - 1
    for i, point in enumerate(points):
        way = points[min(i + 1, last)] - points[max(i - 1, 0)]
        length = way.length()
        across = (
            Vec2(-way.y, way.x).normalized() * ((widths[i] + grow) / 2)
            if length > 1e-6
            else Vec2(0.0, (widths[i] + grow) / 2)
        )
        left.append(qt(point + across))
        right.append(qt(point - across))
    outline = [*left, *reversed(right)]
    if _area(outline) < 0.0:
        outline.reverse()
    path.addPolygon(QPolygonF(outline))
    for point, width in zip(points, widths, strict=True):
        path.addEllipse(qt(point), (width + grow) / 2, (width + grow) / 2)
    return path


def tentacle_chain(
    root: Vec2,
    base_angle: float,
    length: float,
    segments: int,
    clock: float,
    phase: float,
    *,
    bend: float = 0.55,
    s_curve: float = 0.0,
    wave_scale: float = 1.0,
    flick: float = 0.0,
    trail: float = 0.0,
) -> list[Vec2]:
    """Build a tentacle along an artificial S-backbone.

    Control points bow to one side at 1/3 and the opposite at 2/3 (`s_curve`), then
    ambient sine + tip flick ride on top. Chord length stays near `length`.
    """
    tip_angle = base_angle + bend + trail
    tip = root + Vec2.from_angle(tip_angle, length)
    along = tip - root
    across = Vec2(-along.y, along.x)
    if across.length() > 1e-6:
        across = across.normalized()
    else:
        across = Vec2.from_angle(base_angle + math.pi / 2, 1.0)
    # Explicit S: opposite lateral offsets at the third-points.
    c1 = root.lerp(tip, 0.32) + across * s_curve
    c2 = root.lerp(tip, 0.68) - across * s_curve
    points: list[Vec2] = []
    for i in range(segments + 1):
        u = i / max(1, segments)
        # Cubic Bezier root → c1 → c2 → tip.
        omu = 1.0 - u
        point = (
            root * (omu**3)
            + c1 * (3.0 * omu * omu * u)
            + c2 * (3.0 * omu * u * u)
            + tip * (u**3)
        )
        wave = 0.2 * math.sin(2.1 * clock + phase - 0.55 * i)
        wave += 0.09 * math.sin(3.7 * clock + 1.3 * phase - 0.85 * i)
        wave *= wave_scale * (0.25 + 0.75 * u)
        tip_flick = flick * (u**4) * math.sin(clock * 7.0 + phase * 2.1)
        point = point + across * (wave * 6.0 + tip_flick * 5.0)
        points.append(point)
    return points


def _teardrop_half_height(u: float) -> float:
    """Half-height along the body. `u` is 0 at the tip (−x) and 1 at the head (+x)."""
    u = max(0.0, min(1.0, u))
    # Plump through the front half, then pinches to a point — reference droplet.
    return 15.2 * (u**0.7)


def _body_hull() -> list[Vec2]:
    """Sideways teardrop: pointed tip on −x, blunt rounded head on +x."""
    tip_x, head_x = -50.0, 32.0
    span = head_x - tip_x
    samples = 18
    top: list[Vec2] = []
    bottom: list[Vec2] = []
    for i in range(samples + 1):
        u = i / samples
        x = tip_x + span * u
        h = _teardrop_half_height(u)
        top.append(Vec2(x, -h * 0.88))
        bottom.append(Vec2(x, h * 1.1))
    head_h = _teardrop_half_height(1.0)
    # Deep rounded nose so the head reads as the fat end of a droplet.
    face = [
        Vec2(head_x + 0.5, -head_h * 0.9),
        Vec2(head_x + 4.0, -head_h * 0.7),
        Vec2(head_x + 7.5, -head_h * 0.3),
        Vec2(head_x + 9.0, 0.0),
        Vec2(head_x + 7.5, head_h * 0.35),
        Vec2(head_x + 4.0, head_h * 0.75),
        Vec2(head_x + 0.5, head_h * 0.95),
    ]
    return [*top, *face, *reversed(bottom[:-1])]


def _fin_paths(pulse: float) -> list[list[Vec2]]:
    grow = 1.0 + 0.035 * pulse
    dorsal = [
        Vec2(2.0, -11.0),
        Vec2(10.0, -28.0 * grow),
        Vec2(20.0, -12.0),
    ]
    ventral = [
        Vec2(-10.0, 9.0),
        Vec2(-2.0, 18.0 * grow),
        Vec2(8.0, 10.0),
    ]
    caudal = [
        Vec2(-40.0, -1.5),
        Vec2(-58.0 * grow, -11.0),
        Vec2(-48.0, 0.0),
        Vec2(-58.0 * grow, 10.0),
        Vec2(-40.0, 2.0),
    ]
    return [dorsal, ventral, caudal]


def _widths(count: int, root: float, tip: float) -> list[float]:
    if count <= 1:
        return [root]
    return [root + (tip - root) * (i / (count - 1)) ** 0.85 for i in range(count)]


def _tentacles(clock: float, trail: float) -> tuple[list[list[Vec2]], list[list[Vec2]]]:
    trail_angle = -0.28 * trail
    # Upper pair: opposing S bows up and back; both rooted near the face.
    upper = [
        tentacle_chain(
            Vec2(14.0, -8.0),
            -2.2 + trail_angle,
            46.0,
            UPPER_SEGMENTS,
            clock,
            0.4,
            bend=-0.35,
            s_curve=28.0,
            wave_scale=0.45,
            trail=-0.15 * trail,
        ),
        tentacle_chain(
            Vec2(10.0, -6.0),
            -0.85 + trail_angle,
            42.0,
            UPPER_SEGMENTS,
            clock,
            2.1,
            bend=0.3,
            s_curve=-26.0,
            wave_scale=0.45,
            trail=-0.1 * trail,
        ),
    ]
    # Lower four: same S fan as before, all rooted under the front belly.
    # Local angles: 0 = toward head (+x), π/2 = down. s_curve = lateral bow px.
    lower = [
        tentacle_chain(
            Vec2(16.0, 9.0),
            0.55 + trail_angle * 0.25,
            56.0,
            LOWER_SEGMENTS,
            clock,
            0.15,
            bend=0.45,
            s_curve=30.0,
            wave_scale=0.5,
            flick=0.75,
            trail=-0.2 * trail,
        ),
        tentacle_chain(
            Vec2(12.0, 11.0),
            1.15 + trail_angle * 0.3,
            52.0,
            LOWER_SEGMENTS,
            clock,
            1.3,
            bend=0.25,
            s_curve=-28.0,
            wave_scale=0.45,
            trail=-0.18 * trail,
        ),
        tentacle_chain(
            Vec2(8.0, 11.5),
            1.75 + trail_angle * 0.28,
            50.0,
            LOWER_SEGMENTS,
            clock,
            2.5,
            bend=0.2,
            s_curve=26.0,
            wave_scale=0.45,
            trail=-0.14 * trail,
        ),
        tentacle_chain(
            Vec2(4.0, 10.0),
            2.35 + trail_angle * 0.22,
            48.0,
            LOWER_SEGMENTS,
            clock,
            3.6,
            bend=0.15,
            s_curve=-24.0,
            wave_scale=0.4,
            trail=-0.1 * trail,
        ),
    ]
    return upper, lower


def _apply_whip(aboleth: Aboleth, upper: list[list[Vec2]], lower: list[list[Vec2]]) -> None:
    """Swipe one tentacle through an arc centered on the aim — cock high, slash through, follow."""
    whip = aboleth.whip
    if whip is None:
        return
    index = whip.index
    chains = [*upper, *lower]
    if index < 0 or index >= len(chains) or index >= len(WHIP_ROOTS):
        return
    root = WHIP_ROOTS[index]
    _, tip_angle, length, lag = whip_kinematics(
        whip.progress, root, aboleth.world_to_local(whip.tip)
    )
    segments = len(chains[index]) - 1
    chain = [root]
    for i in range(1, segments + 1):
        t = i / max(1, segments)
        # Proximal segments lead the tip so the limb bows into the swing.
        angle = tip_angle + lag * (1.0 - t)
        chain.append(root + Vec2.from_angle(angle, length * t))
    chains[index][:] = chain


@chromatic_appearance
def draw_aboleth(painter: QPainter, aboleth: Aboleth, outline: QColor | None = None) -> None:
    if aboleth.portal is not None and aboleth.portal.life > 0.02:
        from dungeons_desktops.game.defenders.aboleth.actor import BANISH_OPEN
        from dungeons_desktops.game.defenders.mindflayer.render import draw_deep_portal

        draw_deep_portal(
            painter,
            aboleth.portal.center,
            aboleth.portal.age,
            open_time=BANISH_OPEN,
            life=aboleth.portal.life,
        )

    center = aboleth.draw_center()
    facing = aboleth.facing
    lean = aboleth.draw_lean
    clock = aboleth.clock
    trail = clamp_trail(aboleth.drift.x * facing)
    pulse = math.sin(clock * 2.0)
    emerge = smoothstep(aboleth.emerge_progress)
    fade = (1.0 - aboleth.fade) * (0.15 + 0.85 * emerge)
    if fade <= 0.02:
        _paint_effects(painter, aboleth)
        return
    upper, lower = _tentacles(clock, trail)
    _apply_whip(aboleth, upper, lower)

    painter.save()
    painter.setOpacity(fade)
    painter.translate(qt(center))
    painter.rotate(math.degrees(lean))
    scale = 0.35 + 0.65 * emerge
    painter.scale(facing * scale, scale)

    if outline is not None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outline)
        for chain in (*upper, *lower):
            painter.drawPath(_tapered(chain, _widths(len(chain), 7.5, 2.0), grow=2.2))
        for fin in _fin_paths(pulse):
            painter.drawPolygon([qt(p) for p in fin])
        painter.drawPath(_smooth(_body_hull()))

    # Far limbs behind the torso.
    _paint_tentacles(
        painter,
        upper[1:],
        TENTACLE_SAGE_FAR,
        TENTACLE_SAGE_EDGE,
        sage=True,
        root_w=7.0,
        tip_w=2.2,
    )
    _paint_tentacles(
        painter,
        lower[2:],
        TENTACLE_PURPLE_FAR,
        TENTACLE_PURPLE_EDGE,
        sage=False,
        root_w=5.8,
        tip_w=1.8,
    )

    painter.setPen(world_pen(FIN_EDGE, 1.5))
    painter.setBrush(FIN)
    for fin in _fin_paths(pulse):
        painter.drawPolygon([qt(p) for p in fin])

    _paint_body(painter)
    _paint_tentacles(
        painter,
        upper[:1],
        TENTACLE_SAGE,
        TENTACLE_SAGE_EDGE,
        sage=True,
        root_w=7.4,
        tip_w=2.4,
    )
    _paint_tentacles(
        painter,
        lower[:2],
        TENTACLE_PURPLE,
        TENTACLE_PURPLE_EDGE,
        sage=False,
        root_w=6.2,
        tip_w=1.9,
    )
    _paint_eyes(painter, clock, aboleth.eye_charge)

    painter.restore()
    _paint_effects(painter, aboleth)


def clamp_trail(value: float) -> float:
    return max(-1.0, min(1.0, value / 40.0))


def _paint_whip_trail(painter: QPainter, aboleth: Aboleth) -> None:
    trail = aboleth.whip_trail
    if len(trail) < 2:
        return
    base = TENTACLE_SAGE if aboleth.whip_trail_sage else TENTACLE_PURPLE
    for index, (start, end) in enumerate(zip(trail, trail[1:], strict=False)):
        # Newest samples are last; older ones fade out by age and position.
        life = 1.0 - min(1.0, end.age / WHIP_TRAIL_LIFE)
        strength = ((index + 1) / len(trail)) * life
        if strength < 0.05:
            continue
        painter.setPen(world_pen(alpha(base, int(150 * strength)), 1.2 + 3.2 * strength))
        painter.drawLine(qt(start.position), qt(end.position))


def _paint_effects(painter: QPainter, aboleth: Aboleth) -> None:
    _paint_whip_trail(painter, aboleth)
    for bolt in aboleth.bolts:
        wobble = 1.0 + 0.2 * math.sin(bolt.age * 28.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(PSYCHIC, 130))
        painter.drawEllipse(qt(bolt.position), 5.5 * wobble, 5.5 * wobble)
        painter.setBrush(PSYCHIC_CORE)
        painter.drawEllipse(qt(bolt.position), 2.2, 2.2)
        # Thin trail back toward the eyes.
        painter.setPen(world_pen(alpha(PSYCHIC, 160), 1.4))
        painter.drawLine(qt(aboleth.eye_point()), qt(bolt.position))
    charge = aboleth.eye_charge
    if charge > 0.05:
        eyes = aboleth.eye_point()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(EYE_CHARGE_GLOW, int(90 * charge)))
        painter.drawEllipse(qt(eyes), 10.0 * charge, 14.0 * charge)
    for burst in aboleth.slime_bursts:
        u = burst.age / SLIME_BURST_TIME
        radius = SLIME_RADIUS * smoothstep(min(1.0, u * 1.35))
        fade = 1.0 - u
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(world_pen(alpha(SLIME, 220 * fade), 2.0 + 5.0 * fade))
        painter.drawEllipse(qt(burst.center), radius, radius * 0.78)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(SLIME_CORE, int(140 * fade)))
        painter.drawEllipse(qt(burst.center), radius * 0.35, radius * 0.28)


def _paint_body(painter: QPainter) -> None:
    hull = _smooth(_body_hull())
    painter.setPen(world_pen(BODY_EDGE, 1.7))
    painter.setBrush(BODY)
    painter.drawPath(hull)

    # Soft fills only — no hard mid-body polygons that split the teardrop.
    painter.save()
    painter.setClipPath(hull, Qt.ClipOperation.IntersectClip)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(BODY_BELLY)
    painter.drawEllipse(qt(Vec2(4.0, 5.0)), 22.0, 8.5)
    painter.setBrush(BODY_SHADE)
    painter.drawEllipse(qt(Vec2(-8.0, 0.5)), 18.0, 7.0)
    painter.setBrush(BODY_MID)
    painter.drawEllipse(qt(Vec2(18.0, -4.0)), 14.0, 6.0)
    painter.setBrush(BODY_SHADE)
    painter.drawEllipse(qt(Vec2(28.0, 1.0)), 6.5, 5.0)
    painter.restore()


def _paint_tentacles(
    painter: QPainter,
    chains: Iterable[list[Vec2]],
    color: QColor,
    edge: QColor,
    *,
    sage: bool,
    root_w: float,
    tip_w: float,
) -> None:
    for chain in chains:
        widths = _widths(len(chain), root_w, tip_w)
        # Edge underlay, then opaque fill — reads as a solid outlined ribbon.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(edge)
        painter.drawPath(_tapered(chain, widths, grow=1.6))
        painter.setBrush(color)
        painter.drawPath(_tapered(chain, widths))
        if not sage:
            painter.setPen(world_pen(TENTACLE_RIB, 0.85))
            for i in range(2, len(chain) - 1, 2):
                a, b = chain[i - 1], chain[min(i + 1, len(chain) - 1)]
                across = Vec2(-(b - a).y, (b - a).x)
                if across.length() < 1e-6:
                    continue
                across = across.normalized() * (widths[i] * 0.42)
                painter.drawLine(qt(chain[i] - across), qt(chain[i] + across))
            painter.setPen(Qt.PenStyle.NoPen)


def _paint_eyes(painter: QPainter, clock: float, charge: float = 0.0) -> None:
    glow = 0.75 + 0.25 * math.sin(clock * 2.0)
    iris = EYE if charge < 0.15 else EYE_CHARGE
    flare = EYE_GLOW if charge < 0.15 else EYE_CHARGE_GLOW
    size = 1.0 + 0.55 * charge
    for y in (-5.5, 0.0, 5.5):
        socket = Vec2(33.0, y)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SOCKET)
        painter.drawEllipse(qt(socket), 4.6 * size, 3.0 * size)
        painter.setBrush(alpha(flare, int((70 + 120 * charge) * glow)))
        painter.drawEllipse(qt(socket), 3.2 * size, 2.2 * size)
        painter.setBrush(iris)
        painter.drawEllipse(qt(socket), 2.15 * size, 1.7 * size)
        painter.setBrush(EYE_SHINE)
        painter.drawEllipse(qt(socket + Vec2(0.75, -0.45)), 0.65 * size, 0.5 * size)


def draw_aboleths(
    painter: QPainter, aboleths: Iterable[Aboleth], outline: QColor | None = None
) -> None:
    for aboleth in aboleths:
        draw_aboleth(painter, aboleth, outline)
