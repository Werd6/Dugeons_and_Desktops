"""Mind Flayer and intellect-devourer procedural rendering."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QTransform

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.game.defenders.mindflayer.actor import (
    PULSE_RADIUS,
    WAVE_TIME,
    MindFlayer,
    Power,
)
from dungeons_desktops.game.defenders.mindflayer.devourer import BODY_HEIGHT, Devourer
from dungeons_desktops.render.primitives import alpha, pen, qt, world_pen

FLAYER_ROBE = QColor(98, 52, 150)
FLAYER_ROBE_EDGE = QColor(52, 24, 86)
FLAYER_TRIM = QColor(214, 176, 84)
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
    _draw_cape(painter, flayer, neck, hem, down, back, r, outline)
    collar = [
        neck + back * (0.1 * r) + down * (0.35 * r),
        neck + back * (2.3 * r) + up * (1.6 * r),
        neck + back * (1.7 * r) + up * (2.4 * r),
        neck + back * (1.5 * r) + up * (3.5 * r),
        neck + back * (0.8 * r) + up * (2.6 * r),
        neck + back * (0.2 * r) + up * (3.1 * r),
        neck - back * (0.3 * r) + up * (1.2 * r),
    ]
    painter.setPen(world_pen(outline, 2.0) if outline is not None else pen(FLAYER_CAPE_EDGE, 1.0))
    painter.setBrush(FLAYER_CAPE)
    painter.drawPolygon([qt(p) for p in collar])
    lining = [neck.lerp(p, 0.78) for p in collar]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FLAYER_LINING)
    painter.drawPolygon([qt(p) for p in lining])

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
    painter.setPen(world_pen(FLAYER_TRIM, 0.22 * r))
    painter.drawLine(qt(neck + down * (0.2 * r)), qt(hem + down * (0.2 * r)))
    painter.setPen(world_pen(FLAYER_TRIM, 0.3 * r))
    painter.drawLine(qt(waist - side * (0.95 * r)), qt(waist + side * (0.95 * r)))

    head = t[layout.head]
    center = head.end
    head_up = Vec2.from_angle(head.angle)
    forward = head_up.rotated(facing * math.pi / 2)
    dome = center - forward * (0.45 * r) + head_up * (0.35 * r)
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
) -> None:
    """A long cape from the shoulders, trailing away from the way it's floating (and
    settling behind it when it stops), its crimson lining showing at the turned hem."""
    drift = flayer.drift if not flayer.dead else Vec2(0.0, 0.0)
    trail = drift * -0.25
    if trail.length() > 2.6 * r:
        trail = trail.normalized() * (2.6 * r)
    time = flayer.float_time
    billow = min(1.0, drift.length() / 30.0)
    wave = math.sin(time * (2.0 + 4.0 * billow)) * (0.25 + 0.5 * billow) * r
    length = hem.distance_to(neck) + 0.6 * r
    shoulder = neck + back * (0.3 * r) + down * (0.25 * r)
    front = neck - back * (0.3 * r) + down * (0.25 * r)
    inner = neck + down * length + back * (0.9 * r) + trail * 0.7 + down * (wave * 0.3)
    outer = neck + down * (length * 0.97) + back * (2.9 * r) + trail * 1.2 + down * wave
    belly = neck + down * (length * 0.45) + back * (2.6 * r + 0.4 * wave) + trail * 0.5
    cape = QPainterPath(qt(front))
    cape.lineTo(qt(shoulder))
    cape.quadTo(qt(belly), qt(outer))
    cape.quadTo(qt(outer.lerp(inner, 0.5) + down * (0.6 * r)), qt(inner))
    cape.lineTo(qt(front))
    painter.setPen(world_pen(outline, 2.0) if outline is not None else pen(FLAYER_CAPE_EDGE, 1.0))
    painter.setBrush(FLAYER_CAPE)
    painter.drawPath(cape)
    lining = QPainterPath(qt(outer))
    lining.quadTo(qt(outer.lerp(inner, 0.5) + down * (0.6 * r)), qt(inner))
    lining.quadTo(qt(outer.lerp(inner, 0.5) - down * (0.35 * r)), qt(outer))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FLAYER_LINING)
    painter.drawPath(lining)


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
    """Mind blast bolts, pulse rings, and the glow of a power being summoned."""
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


def draw_devourer(painter: QPainter, devourer: Devourer, outline: QColor | None = None) -> None:
    """A brain scuttling on four clawed legs, feet on whatever surface it's crawling on
    (sideways up a window's side, upside down under it); flipped over, legs up, once
    dead."""
    up, forward, feet = devourer.up, devourer.forward, devourer.position
    painter.save()
    painter.setTransform(
        QTransform(forward.x, forward.y, -up.x, -up.y, feet.x, feet.y), combine=True
    )
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


