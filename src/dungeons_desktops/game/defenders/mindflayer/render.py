"""Mind Flayer and intellect-devourer procedural rendering."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient, QTransform

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.game.defenders.mindflayer.actor import (
    PULSE_RADIUS,
    RITUAL_PULSE_RADIUS,
    RITUAL_PULSE_TIME,
    WAVE_TIME,
    MindFlayer,
    Power,
)
from dungeons_desktops.game.defenders.mindflayer.devourer import BODY_HEIGHT, Devourer
from dungeons_desktops.game.defenders.mindflayer.rift import RIFT_MEALS, RIFT_OPEN_TIME, Rift
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.primitives import alpha, pen, qt, world_pen

FLAYER_ROBE = QColor(98, 52, 150)
FLAYER_ROBE_EDGE = QColor(52, 24, 86)
FLAYER_TRIM = QColor(214, 176, 84)
FLAYER_GOLD = QColor(255, 208, 72)
FLAYER_GOLD_EDGE = QColor(176, 120, 36)
RIFT_TENTACLE = QColor(28, 12, 36)
RIFT_TENTACLE_EDGE = QColor(8, 4, 14)
RIFT_TENTACLE_WET = QColor(72, 28, 88)
FLAYER_SKIN = QColor(172, 146, 204)
FLAYER_SKIN_FAR = QColor(120, 98, 150)
FLAYER_SKIN_EDGE = QColor(96, 70, 128)
FLAYER_EYE = QColor(246, 242, 255)
FLAYER_CAPE = QColor(44, 20, 66)
FLAYER_CAPE_EDGE = QColor(20, 8, 32)
FLAYER_LINING = QColor(176, 34, 66)
FLAYER_SHADOW = QColor(40, 20, 70, 60)
FLAYER_TENTACLE = QColor(146, 112, 184)
FLAYER_TENTACLE_EDGE = QColor(62, 36, 92)
TENTACLE_LENGTH = 2.8
PSYCHIC = QColor(196, 112, 255)
PSYCHIC_CORE = QColor(250, 236, 255)
BRAIN = QColor(238, 152, 176)
BRAIN_EDGE = QColor(168, 78, 108)
DEVOURER_LEG = QColor(222, 186, 178)
DEVOURER_LEG_FAR = QColor(170, 130, 126)
LIMB_WIDTH = 3.0


def _draw_brain(
    painter: QPainter, center: Vec2, rx: float, ry: float, outline: QColor | None = None
) -> None:
    if outline is not None:
        painter.setPen(world_pen(outline, 1.6))
        painter.setBrush(outline)
        painter.drawEllipse(qt(center), rx, ry)
    painter.setPen(world_pen(BRAIN_EDGE, max(0.4, 0.12 * ry)))
    painter.setBrush(BRAIN)
    painter.drawEllipse(qt(center), rx, ry)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(qt(center + Vec2(0.0, -ry * 0.9)), qt(center + Vec2(0.0, ry * 0.5)))
    for side in (-1.0, 1.0):
        for index, (x, y) in enumerate(((0.45, -0.35), (0.6, 0.2))):
            fold = center + Vec2(side * x * rx, y * ry)
            arc = 0.28 * rx
            tip = fold + Vec2(0.0, -0.25 * ry * (index + 1))
            painter.drawLine(qt(fold - Vec2(arc, 0.0)), qt(tip))
            painter.drawLine(qt(tip), qt(fold + Vec2(arc, 0.0)))


def draw_mindflayers(
    painter: QPainter,
    flayers: Iterable[MindFlayer],
    devourers: Iterable[Devourer],
    outline: QColor | None = None,
) -> None:
    for devourer in devourers:
        draw_devourer(painter, devourer, outline)
    flayers = list(flayers)
    for flayer in flayers:
        draw_mindflayer(painter, flayer, outline)
    draw_psionics(painter, flayers)


@chromatic_appearance
def draw_mindflayer(painter: QPainter, flayer: MindFlayer, outline: QColor | None = None) -> None:
    """Back to front: the cape streaming behind it, the high flared collar, the far
    arm, the purple robe (it has no legs to speak of), the bulbous head with blank
    eyes, the face tentacles (writhing, or wrapped round a victim's head mid-grab),
    then the near arm."""
    layout = flayer.layout
    t = flayer.transforms()
    r = layout.head_radius
    facing = flayer.facing
    limb = LIMB_WIDTH * layout.scale
    torso = t[layout.torso]
    down = (torso.start - torso.end).normalized()
    up = -down
    side = Vec2(-down.y, down.x)
    back = Vec2(-facing, 0.0)
    neck, waist = torso.end, torso.start
    hem = waist + down * (layout.leg_length * 0.95)
    time = flayer.float_time
    edge_pen = world_pen(outline, 2.0) if outline is not None else pen(FLAYER_ROBE_EDGE, 1.0)

    def arm(name: str, color: QColor) -> None:
        bones = (t[f"upper_arm_{name}"], t[f"lower_arm_{name}"])
        if outline is not None:
            painter.setPen(pen(outline, limb + 2.5 * layout.scale))
            for bone in bones:
                painter.drawLine(qt(bone.start), qt(bone.end))
        painter.setPen(world_pen(FLAYER_ROBE_EDGE, limb * 1.35))
        painter.drawLine(qt(bones[0].start), qt(bones[0].end))
        painter.setPen(world_pen(FLAYER_ROBE, limb))
        painter.drawLine(qt(bones[0].start), qt(bones[0].end))
        painter.setPen(world_pen(color, limb * 0.8))
        painter.drawLine(qt(bones[1].start), qt(bones[1].end))

    follower = flayer.follower
    if not flayer.dead and not follower.in_transition:
        ground = follower.current_anchor().surface
        if ground.walkable:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(FLAYER_SHADOW)
            painter.drawEllipse(qt(Vec2(flayer.feet.x, ground.start.y)), 1.6 * r, 0.4 * r)
    legendary = getattr(flayer, "legendary", False)
    _draw_cape(painter, flayer, neck, hem, down, back, r, outline, legendary=legendary)
    # Hood / high collar — taller and more flared on the Elder Thing Herald.
    hood = 1.45 if legendary else 1.0
    collar = [
        neck + back * (0.1 * r) + down * (0.35 * r),
        neck + back * ((2.3 + 0.7 * (hood - 1.0)) * r) + up * (1.6 * hood * r),
        neck + back * ((1.7 + 0.55 * (hood - 1.0)) * r) + up * (2.4 * hood * r),
        neck + back * ((1.5 + 0.45 * (hood - 1.0)) * r) + up * (3.5 * hood * r),
        neck + back * ((0.8 + 0.35 * (hood - 1.0)) * r) + up * (2.6 * hood * r),
        neck + back * (0.2 * r) + up * (3.1 * hood * r),
        neck - back * (0.3 * r) + up * (1.2 * hood * r),
    ]
    painter.setPen(world_pen(outline, 2.0) if outline is not None else pen(FLAYER_CAPE_EDGE, 1.0))
    painter.setBrush(FLAYER_CAPE)
    painter.drawPolygon([qt(p) for p in collar])
    lining = [neck.lerp(p, 0.78) for p in collar]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FLAYER_LINING)
    painter.drawPolygon([qt(p) for p in lining])
    if legendary and outline is None:
        # Gold piping along the hood rim and a clasp at the throat.
        painter.setPen(world_pen(FLAYER_GOLD_EDGE, 0.28 * r))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rim = [collar[1], collar[2], collar[3], collar[4], collar[5]]
        for a, b in zip(rim, rim[1:], strict=True):
            painter.drawLine(qt(a), qt(b))
        painter.setPen(world_pen(FLAYER_GOLD, 0.18 * r))
        for a, b in zip(rim, rim[1:], strict=True):
            painter.drawLine(qt(a), qt(b))
        clasp = neck + back * (0.15 * r) + down * (0.15 * r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FLAYER_GOLD_EDGE)
        painter.drawEllipse(qt(clasp), 0.42 * r, 0.42 * r)
        painter.setBrush(FLAYER_GOLD)
        painter.drawEllipse(qt(clasp), 0.28 * r, 0.28 * r)

    arm("l", FLAYER_SKIN_FAR)
    flutter = side * (math.sin(time * 2.0) * 0.12 * r)
    robe = [
        neck + side * (0.65 * r),
        waist + side * (1.0 * r),
        hem + side * (1.45 * r) + flutter,
        hem + side * (0.5 * r) + down * (0.3 * r) + flutter,
        hem - side * (0.5 * r) + down * (0.15 * r) + flutter,
        hem - side * (1.45 * r) + flutter,
        waist - side * (1.0 * r),
        neck - side * (0.65 * r),
    ]
    painter.setPen(edge_pen)
    painter.setBrush(FLAYER_ROBE)
    painter.drawPolygon([qt(p) for p in robe])
    trim = FLAYER_GOLD if legendary else FLAYER_TRIM
    painter.setPen(world_pen(trim, (0.28 if legendary else 0.22) * r))
    painter.drawLine(qt(neck + down * (0.2 * r)), qt(hem + down * (0.2 * r)))
    painter.setPen(world_pen(trim, (0.38 if legendary else 0.3) * r))
    painter.drawLine(qt(waist - side * (0.95 * r)), qt(waist + side * (0.95 * r)))
    if legendary and outline is None:
        # Gold hem braid along the robe skirt.
        painter.setPen(world_pen(FLAYER_GOLD_EDGE, 0.22 * r))
        painter.drawPolyline([qt(p) for p in robe[2:6]])
        painter.setPen(world_pen(FLAYER_GOLD, 0.14 * r))
        painter.drawPolyline([qt(p) for p in robe[2:6]])

    head = t[layout.head]
    center = head.end
    head_up = Vec2.from_angle(head.angle)
    forward = head_up.rotated(facing * math.pi / 2)
    dome = center - forward * (0.45 * r) + head_up * (0.35 * r)
    if getattr(flayer, "legendary", False) and not flayer.dead:
        pulse = 0.65 + 0.35 * math.sin(flayer.float_time * 4.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(PSYCHIC, 55 * pulse))
        painter.drawEllipse(qt(dome), 1.8 * r, 1.8 * r)
    if outline is not None:
        painter.setPen(world_pen(outline, 2.0))
        painter.setBrush(outline)
        painter.drawEllipse(qt(dome), 1.1 * r, 1.1 * r)
        painter.drawEllipse(qt(center), r, r)
    painter.setPen(pen(FLAYER_SKIN_EDGE, 1.0))
    painter.setBrush(FLAYER_SKIN)
    painter.drawEllipse(qt(dome), 1.1 * r, 1.1 * r)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(qt(center), r, r)
    painter.setPen(world_pen(FLAYER_SKIN_EDGE, 0.12 * r))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for k in (-1.0, 1.0):
        vein = dome + head_up * (0.3 * r) + forward * (k * 0.3 * r)
        painter.drawLine(qt(vein), qt(vein - forward * (0.35 * r) + head_up * (0.3 * r)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(PSYCHIC if flayer.power is not None else FLAYER_EYE)
    eye = center + forward * (0.45 * r) + head_up * (0.15 * r)
    painter.drawEllipse(qt(eye), 0.34 * r, 0.22 * r)
    _draw_tentacles(painter, flayer, center, head_up, forward, r, outline)
    arm("r", FLAYER_SKIN)


def _draw_cape(
    painter: QPainter,
    flayer: MindFlayer,
    neck: Vec2,
    hem: Vec2,
    down: Vec2,
    back: Vec2,
    r: float,
    outline: QColor | None,
    legendary: bool = False,
) -> None:
    """A long cape from the shoulders, trailing away from the way it's floating (and
    settling behind it when it stops), its crimson lining showing at the turned hem.
    Legendary cloaks run longer, billow wider, and carry a gold border."""
    drift = flayer.drift if not flayer.dead else Vec2(0.0, 0.0)
    sprawl = 1.55 if legendary else 1.0
    trail = drift * (-0.32 if legendary else -0.25)
    trail_cap = (3.8 if legendary else 2.6) * r
    if trail.length() > trail_cap:
        trail = trail.normalized() * trail_cap
    time = flayer.float_time
    billow = min(1.0, drift.length() / 30.0)
    wave = math.sin(time * (2.0 + 4.0 * billow)) * (0.25 + 0.5 * billow) * r * sprawl
    length = hem.distance_to(neck) + (1.35 if legendary else 0.6) * r
    shoulder = neck + back * (0.3 * r) + down * (0.25 * r)
    front = neck - back * (0.3 * r) + down * (0.25 * r)
    inner = neck + down * length + back * (0.9 * sprawl * r) + trail * 0.7 + down * (wave * 0.3)
    outer = (
        neck
        + down * (length * (1.02 if legendary else 0.97))
        + back * ((3.8 if legendary else 2.9) * r)
        + trail * (1.45 if legendary else 1.2)
        + down * wave
    )
    belly = (
        neck
        + down * (length * 0.45)
        + back * ((3.4 if legendary else 2.6) * r + 0.4 * wave)
        + trail * 0.5
    )
    hem_curve = outer.lerp(inner, 0.5) + down * (0.75 if legendary else 0.6) * r
    cape = QPainterPath(qt(front))
    cape.lineTo(qt(shoulder))
    cape.quadTo(qt(belly), qt(outer))
    cape.quadTo(qt(hem_curve), qt(inner))
    cape.lineTo(qt(front))
    painter.setPen(world_pen(outline, 2.0) if outline is not None else pen(FLAYER_CAPE_EDGE, 1.0))
    painter.setBrush(FLAYER_CAPE)
    painter.drawPath(cape)
    lining = QPainterPath(qt(outer))
    lining.quadTo(qt(hem_curve), qt(inner))
    lining.quadTo(qt(outer.lerp(inner, 0.5) - down * (0.35 * r)), qt(outer))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FLAYER_LINING)
    painter.drawPath(lining)
    if legendary and outline is None:
        # Gold filigree along the trailing edge and a shoulder plate.
        painter.setPen(world_pen(FLAYER_GOLD_EDGE, 0.32 * r))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        edge = QPainterPath(qt(shoulder))
        edge.quadTo(qt(belly), qt(outer))
        edge.quadTo(qt(hem_curve), qt(inner))
        painter.drawPath(edge)
        painter.setPen(world_pen(FLAYER_GOLD, 0.18 * r))
        painter.drawPath(edge)
        plate = shoulder + back * (0.35 * r) + down * (0.1 * r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FLAYER_GOLD_EDGE)
        painter.drawEllipse(qt(plate), 0.55 * r, 0.4 * r)
        painter.setBrush(FLAYER_GOLD)
        painter.drawEllipse(qt(plate), 0.38 * r, 0.28 * r)


def _draw_tentacles(
    painter: QPainter,
    flayer: MindFlayer,
    center: Vec2,
    up: Vec2,
    forward: Vec2,
    r: float,
    outline: QColor | None = None,
) -> None:
    """Four thick face tentacles, two-toned and curling at the tips, always writhing.
    Mid-grab they reach out and wrap round the victim's head."""
    base = center + forward * (0.5 * r) - up * (0.5 * r)
    reach = flayer.grab_reach
    victim = flayer.victim if reach > 0.0 else None
    held = None
    if victim is not None:
        held = victim.transforms()[victim.layout.head].end, victim.layout.head_radius
    down = -up
    length = TENTACLE_LENGTH * r
    count = 9
    time = flayer.float_time
    for i, spread in enumerate((0.36, -0.12, 0.12, -0.36)):
        root = base + forward * (spread * r)
        curl = 1.5 if i % 2 == 0 else -1.2
        angle = 0.15 + spread * 0.5
        point = root
        points = [root]
        for k in range(1, count + 1):
            u = k / count
            writhe = math.sin(time * 3.4 + i * 1.7 + u * 5.0) * 0.45 * u
            flick = math.sin(time * 7.0 + i * 2.3) * 0.6 * u**4
            angle_k = angle + writhe + curl * u**3 + flick
            direction = down * math.cos(angle_k) + forward * math.sin(angle_k)
            point = point + direction * (length / count)
            points.append(point)
        if held is not None:
            head, radius = held
            toward = (head - root).normalized()
            approach = head - toward * (radius * 1.05)
            start = math.atan2(approach.y - head.y, approach.x - head.x) + (0.35 * spread / 0.36)
            sweep = (1.0 if i % 2 == 0 else -1.0) * math.pi * 1.25
            wrap = radius * (1.05 + 0.12 * (i % 2))
            gripping = []
            for k in range(count + 1):
                u = k / count
                if u <= 0.5:
                    spot = root.lerp(approach, u / 0.5) + down * (
                        math.sin(u * math.pi * 2) * 0.3 * r
                    )
                else:
                    a = start + sweep * (u - 0.5) / 0.5
                    spot = head + Vec2(math.cos(a), math.sin(a)) * wrap
                gripping.append(spot)
            points = [p.lerp(g, smoothstep(reach)) for p, g in zip(points, gripping, strict=True)]
        widths = [(0.62 - 0.47 * k / count) * r for k in range(count)]
        if outline is not None:
            for k in range(count):
                painter.setPen(world_pen(outline, widths[k] + 2.0))
                painter.drawLine(qt(points[k]), qt(points[k + 1]))
        for k in range(count):
            painter.setPen(world_pen(FLAYER_TENTACLE_EDGE, widths[k] + 0.3 * r))
            painter.drawLine(qt(points[k]), qt(points[k + 1]))
        for k in range(count):
            painter.setPen(world_pen(FLAYER_SKIN if i < 2 else FLAYER_TENTACLE, widths[k]))
            painter.drawLine(qt(points[k]), qt(points[k + 1]))


def draw_psionics(painter: QPainter, flayers: Iterable[MindFlayer]) -> None:
    """Mind blast bolts, pulse rings, ritual rifts, and the glow of a power being summoned."""
    for flayer in flayers:
        if flayer.power in (Power.BLAST, Power.PULSE) and not flayer.dead:
            charge = min(1.0, flayer.power_time / 0.45)
            point = flayer.mouth() if flayer.power is Power.BLAST else flayer.center()
            size = (3.0 if flayer.power is Power.BLAST else 9.0) * (0.4 + charge)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(alpha(PSYCHIC, 90 * charge))
            painter.drawEllipse(qt(point), size, size)
        for bolt in flayer.bolts:
            wobble = 1.0 + 0.25 * math.sin(bolt.age * 30.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(alpha(PSYCHIC, 110))
            painter.drawEllipse(qt(bolt.position), 5.0 * wobble, 5.0 * wobble)
            painter.setBrush(PSYCHIC_CORE)
            painter.drawEllipse(qt(bolt.position), 2.0, 2.0)
            painter.setPen(world_pen(alpha(PSYCHIC, 180), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(bolt.position), 7.0 * wobble, 4.0 * wobble)
        for wave in flayer.waves:
            u = wave.age / WAVE_TIME
            radius = PULSE_RADIUS * smoothstep(min(1.0, u * 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(alpha(PSYCHIC, 230 * (1.0 - u)), 1.0 + 3.0 * (1.0 - u)))
            painter.drawEllipse(qt(wave.center), radius, radius * 0.8)
            painter.setPen(world_pen(alpha(PSYCHIC_CORE, 160 * (1.0 - u)), 1.0))
            painter.drawEllipse(qt(wave.center), radius * 0.8, radius * 0.64)
        if flayer.ritual_point is not None and flayer.ritual_pulse_age is None:
            # Gathering mark while thralls converge.
            mark = flayer.ritual_point
            pulse = 0.55 + 0.45 * math.sin(flayer.float_time * 5.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(alpha(PSYCHIC, 50 * pulse))
            painter.drawEllipse(qt(mark), 16.0, 10.0)
            painter.setPen(world_pen(alpha(PSYCHIC_CORE, 180 * pulse), 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(mark), 10.0, 6.0)
        if flayer.ritual_pulse_age is not None and flayer.ritual_point is not None:
            u = flayer.ritual_pulse_age / RITUAL_PULSE_TIME
            radius = RITUAL_PULSE_RADIUS * smoothstep(min(1.0, u * 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(alpha(PSYCHIC, 240 * (1.0 - u)), 2.5 + 4.0 * (1.0 - u)))
            painter.drawEllipse(qt(flayer.ritual_point), radius, radius * 0.75)
        for rift in flayer.rifts:
            _draw_rift(painter, rift)
            _draw_rift_tentacles(painter, rift)


@chromatic_appearance
def draw_devourer(painter: QPainter, devourer: Devourer, outline: QColor | None = None) -> None:
    """A brain scuttling on four clawed legs, feet on whatever surface it's crawling on
    (sideways up a window's side, upside down under it); flipped over, legs up, once
    dead."""
    up, forward, feet = devourer.up, devourer.forward, devourer.position
    scale = devourer.size
    painter.save()
    painter.setTransform(
        QTransform(forward.x, forward.y, -up.x, -up.y, feet.x, feet.y), combine=True
    )
    if scale != 1.0:
        painter.scale(scale, scale)
    center = Vec2(0.0, -BODY_HEIGHT)
    lying = devourer.dead and not devourer.airborne
    legs = []
    for front in (True, False):
        for near, offset in ((False, 0.5), (True, 0.0)):
            direction = 1.0 if front else -1.0
            hip = center + Vec2(direction * 3.0, 1.5 if not lying else -1.0)
            if lying:
                foot = hip + Vec2(direction * 2.5, -6.0 - (1.0 if near else 0.0))
                knee = hip.lerp(foot, 0.5) + Vec2(direction * 2.4, 0.0)
            elif devourer.airborne:
                foot = hip + Vec2(direction * 4.5, 3.0)
                knee = hip.lerp(foot, 0.5) + Vec2(direction * 0.5, -2.0)
            else:
                cycle = (devourer.phase + offset + (0.25 if front else 0.0)) * math.tau
                swing = math.sin(cycle) * 1.8
                lift = max(0.0, math.cos(cycle)) * 1.4
                foot = Vec2(hip.x + direction * 3.0 + swing, -lift)
                knee = hip.lerp(foot, 0.5) + Vec2(direction * 2.2, -3.0)
            legs.append((near, hip, knee, foot, direction))
    if outline is not None:
        painter.setPen(pen(outline, 3.2))
        for _, hip, knee, foot, _ in legs:
            painter.drawPolyline([qt(hip), qt(knee), qt(foot)])

    def draw_legs(side: bool) -> None:
        for near, hip, knee, foot, direction in legs:
            if near is not side:
                continue
            claw = foot + Vec2(direction * 1.4, -0.5)
            painter.setPen(world_pen(BRAIN_EDGE, 1.7))
            painter.drawPolyline([qt(hip), qt(knee), qt(foot), qt(claw)])
            painter.setPen(world_pen(DEVOURER_LEG if near else DEVOURER_LEG_FAR, 0.9))
            painter.drawPolyline([qt(hip), qt(knee), qt(foot), qt(claw)])

    draw_legs(False)
    _draw_brain(painter, center, 6.0, 4.2, outline)
    draw_legs(True)
    painter.restore()


def draw_deep_portal(
    painter: QPainter,
    center: Vec2,
    age: float,
    *,
    open_time: float = RIFT_OPEN_TIME,
    life: float = 1.0,
    fed: float = 0.0,
) -> None:
    """A deep extradimensional pit: nested dark ellipses, star flecks, warping rim."""
    open_by = smoothstep(min(1.0, age / max(open_time, 1e-3))) * max(0.0, min(1.0, life))
    if open_by <= 0.02:
        return
    fade = (1.0 - 0.18 * fed) * max(0.0, min(1.0, life))
    # Vertical oval that reads as a hole punched through the desktop.
    height = (22.0 + 58.0 * open_by) * (1.0 - 0.12 * fed)
    width = (7.0 + 20.0 * open_by) * (1.0 - 0.1 * fed)
    cx, cy = center.x, center.y
    phase = age * 1.7

    painter.setPen(Qt.PenStyle.NoPen)

    # Soft violet bruise in the air around the tear.
    bruise = QRadialGradient(QPointF(cx, cy - height * 0.1), max(width, height) * 1.35)
    bruise.setColorAt(0.0, alpha(QColor(88, 36, 140), 70 * fade * open_by))
    bruise.setColorAt(0.55, alpha(QColor(40, 12, 72), 40 * fade * open_by))
    bruise.setColorAt(1.0, alpha(QColor(10, 2, 20), 0))
    painter.setBrush(bruise)
    painter.drawEllipse(qt(center), width * 2.4, height * 1.15)

    # Depth shells: each ring smaller/darker, sinking into the void.
    shells = (
        (1.00, QColor(18, 6, 32), 200),
        (0.78, QColor(8, 2, 16), 230),
        (0.55, QColor(2, 0, 6), 245),
        (0.32, QColor(0, 0, 0), 255),
    )
    for scale, color, a in shells:
        wobble = 1.0 + 0.03 * math.sin(phase * 1.3 + scale * 4.0)
        painter.setBrush(alpha(color, a * fade))
        painter.drawEllipse(
            qt(center + Vec2(0.0, height * 0.04 * (1.0 - scale))),
            width * scale * wobble,
            height * scale * 0.92,
        )

    # Cold cyan / magenta chromatic lip so it feels un-real.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(alpha(QColor(120, 220, 255), 110 * fade), 1.6))
    painter.drawEllipse(qt(center + Vec2(-0.8, 0.0)), width * 1.02, height * 0.5)
    painter.setPen(world_pen(alpha(QColor(220, 80, 255), 120 * fade), 1.6))
    painter.drawEllipse(qt(center + Vec2(0.8, 0.0)), width * 1.02, height * 0.5)
    painter.setPen(world_pen(alpha(PSYCHIC, 200 * fade), 2.2))
    painter.drawEllipse(qt(center), width, height * 0.5)

    # Jagged event-horizon fringe.
    rim = QPainterPath()
    steps = 18
    for i in range(steps + 1):
        t = i / steps
        ang = t * math.tau + phase * 0.35
        jitter = 1.0 + 0.08 * math.sin(ang * 3.0 + phase * 2.1)
        px = cx + math.cos(ang) * width * jitter
        py = cy + math.sin(ang) * height * 0.5 * jitter
        if i == 0:
            rim.moveTo(px, py)
        else:
            rim.lineTo(px, py)
    painter.setPen(world_pen(alpha(QColor(160, 70, 220), 90 * fade), 1.1))
    painter.drawPath(rim)

    # Distant stars tumbling in the pit.
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(9):
        seed = i * 1.618 + phase * 0.4
        u = (math.sin(seed * 2.3) * 0.5 + 0.5) * 0.85
        v = (math.cos(seed * 1.7) * 0.5 + 0.5) * 0.85
        ang = seed * 3.1
        sx = cx + math.cos(ang) * width * u * 0.72
        sy = cy + math.sin(ang) * height * 0.42 * v
        twinkle = 0.45 + 0.55 * abs(math.sin(phase * 2.4 + i))
        size = 0.55 + 0.55 * ((i * 37) % 3) / 2.0
        painter.setBrush(alpha(QColor(210, 230, 255), 200 * fade * twinkle * open_by))
        painter.drawEllipse(QPointF(sx, sy), size, size)

    # Bottomless core — absolute black with a faint far spark.
    painter.setBrush(alpha(QColor(0, 0, 0), 255 * fade))
    painter.drawEllipse(qt(center + Vec2(0.0, height * 0.02)), width * 0.22, height * 0.28)
    painter.setBrush(alpha(QColor(140, 180, 255), 90 * fade * open_by))
    painter.drawEllipse(qt(center + Vec2(0.4, height * 0.06)), 1.1, 1.1)


def _draw_rift(painter: QPainter, rift: Rift) -> None:
    # While opening, `draw_deep_portal` handles the bloom; after that `life` fades as it feeds/closes.
    draw_deep_portal(
        painter,
        rift.center,
        rift.age,
        open_time=RIFT_OPEN_TIME,
        life=rift.life if rift.opened else 1.0,
        fed=rift.eaten / RIFT_MEALS,
    )


def _draw_rift_tentacles(painter: QPainter, rift: Rift) -> None:
    """The sentry lash only — drawn while striking or hauling someone in."""
    strike = rift.strike
    if not rift.opened or strike is None:
        return
    points = strike.body(rift.center)
    if len(points) < 2:
        return
    count = len(points) - 1
    gripping = strike.victim is not None
    for k in range(count):
        t = k / max(1, count - 1)
        width = (5.4 if gripping else 4.4) - 3.2 * t
        painter.setPen(world_pen(RIFT_TENTACLE_EDGE, width + 1.6))
        painter.drawLine(qt(points[k]), qt(points[k + 1]))
    for k in range(count):
        t = k / max(1, count - 1)
        width = (4.2 if gripping else 3.2) - 2.4 * t
        color = RIFT_TENTACLE_WET if t < 0.25 else RIFT_TENTACLE
        painter.setPen(world_pen(color, width))
        painter.drawLine(qt(points[k]), qt(points[k + 1]))
    tip = points[-1]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(RIFT_TENTACLE_EDGE)
    painter.drawEllipse(qt(tip), 3.4 if gripping else 2.8, 2.6 if gripping else 2.2)
    painter.setBrush(RIFT_TENTACLE)
    painter.drawEllipse(qt(tip), 2.2 if gripping else 1.8, 1.7 if gripping else 1.4)


