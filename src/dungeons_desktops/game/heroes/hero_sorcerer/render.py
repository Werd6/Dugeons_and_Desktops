"""Skull face, floating skull focus, and orbiting skulls for the Hero Sorcerer."""

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.defenders.lich.skeleton_render import (
    BONE as SKELETON_BONE,
)
from dungeons_desktops.game.defenders.lich.skeleton_render import (
    draw_skeleton_skull,
)
from dungeons_desktops.game.heroes.hero_sorcerer.blood_cloud import (
    DRAIN_FLASH,
)
from dungeons_desktops.game.heroes.hero_sorcerer.blood_cloud import (
    RADIUS as BLOOD_RADIUS,
)
from dungeons_desktops.game.heroes.hero_sorcerer.skeletal_grasp import SkeletalArm
from dungeons_desktops.render.primitives import qt, world_pen

BODY = QColor(62, 68, 78)
BODY_FAR = QColor(38, 43, 51)
BODY_WIDTH = 5.0
SCARF = QColor(202, 34, 49)
SCARF_EDGE = QColor(82, 12, 20)
BONE = SKELETON_BONE
ORBIT_RADIUS = 29.0
ORBIT_HEIGHT = 10.0
ORBIT_SPEED = 1.45
STORM_BLACK = QColor(15, 16, 20)
STORM_GREY = QColor(91, 97, 106)
STORM_LIGHT = QColor(151, 154, 160)
STORM_RED = QColor(176, 22, 39)
BLOOD_DARK = QColor(58, 4, 12)
BLOOD_MIST = QColor(148, 10, 28)
BLOOD_BRIGHT = QColor(235, 37, 62)
GRAVE_RIFT = QColor(24, 8, 13)
ARM_SHADOW = QColor(91, 84, 78)
GRIP_GLOW = QColor(142, 18, 34)


def _alpha(color: QColor, opacity: float) -> QColor:
    result = QColor(color)
    result.setAlpha(round(clamp(opacity, 0.0, 255.0)))
    return result


def draw_blood_cloud(painter: QPainter, actor) -> None:
    """Draw drifting blood mist, cut away wherever a desktop window covers it."""
    cloud = actor.blood_cloud
    if cloud is None or cloud.strength <= 0.0:
        return
    painter.save()
    center = cloud.center
    radius = BLOOD_RADIUS * cloud.strength
    allowed = QPainterPath()
    allowed.addEllipse(qt(center), radius, radius * 0.58)
    for box in actor.world.boxes:
        window = QPainterPath()
        window.addRect(QRectF(box.x, box.y, box.width, box.height))
        allowed = allowed.subtracted(window)
    painter.setClipPath(allowed, Qt.ClipOperation.IntersectClip)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_alpha(BLOOD_DARK, 85 * cloud.strength))
    painter.drawEllipse(qt(center), radius, radius * 0.55)
    clock = cloud.age * 0.9
    colors = (BLOOD_DARK, BLOOD_MIST, BLOOD_BRIGHT)
    for index in range(30):
        angle = index * 2.39996 + clock * (0.22 + 0.04 * (index % 4))
        distance = radius * (0.12 + 0.78 * ((index * 11) % 29) / 28.0)
        point = center + Vec2(
            math.cos(angle) * distance,
            math.sin(angle) * distance * 0.5 - 5.0 * math.sin(clock + index),
        )
        puff = (7.0 + (index * 7) % 13) * cloud.strength
        color = colors[index % len(colors)]
        painter.setBrush(_alpha(color, (38 + 9 * (index % 5)) * cloud.strength))
        painter.drawEllipse(qt(point), puff * 1.4, puff * 0.72)
    painter.restore()

    # Each successful drain briefly pulls three blood streams back into the caster.
    if cloud.drain_flash > 0.0:
        painter.save()
        visible = QPainterPath()
        visible.addRect(QRectF(0.0, -10000.0, actor.world.width, actor.world.floor_y + 10000.0))
        for box in actor.world.boxes:
            window = QPainterPath()
            window.addRect(QRectF(box.x, box.y, box.width, box.height))
            visible = visible.subtracted(window)
        painter.setClipPath(visible, Qt.ClipOperation.IntersectClip)
        flash = clamp(cloud.drain_flash / DRAIN_FLASH, 0.0, 1.0)
        target = actor.center()
        direction = (target - center).normalized()
        side = direction.rotated(math.pi / 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index in range(3):
            start = center + side * ((index - 1) * 13.0)
            path = QPainterPath(qt(start))
            bend = start.lerp(target, 0.52) + side * math.sin(clock * 5.0 + index) * 12.0
            path.quadTo(qt(bend), qt(target))
            painter.setPen(world_pen(_alpha(BLOOD_BRIGHT, 205 * flash), 1.2 + index * 0.45))
            painter.drawPath(path)
        painter.restore()


def draw_corpsenado(painter: QPainter, actor) -> None:
    """Draw layered grave winds with bones and skulls caught in the spiral."""
    storm = actor.corpsenado
    if storm is None or storm.strength <= 0.0:
        return
    painter.save()
    center = storm.position
    strength = storm.strength
    height = 78.0 * strength
    clock = storm.age * 4.7

    # A translucent tapered core keeps the separate wind ribbons reading as one funnel.
    core = QPainterPath(qt(center + Vec2(-5.0, 15.0)))
    core.cubicTo(
        qt(center + Vec2(-17.0, -6.0)),
        qt(center + Vec2(-31.0, 15.0 - height)),
        qt(center + Vec2(0.0, 14.0 - height)),
    )
    core.cubicTo(
        qt(center + Vec2(31.0, 15.0 - height)),
        qt(center + Vec2(17.0, -6.0)),
        qt(center + Vec2(5.0, 15.0)),
    )
    core.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_alpha(STORM_BLACK, 128 * strength))
    painter.drawPath(core)

    colors = (STORM_GREY, STORM_RED, STORM_BLACK, STORM_LIGHT)
    for ribbon in range(13):
        vertical = (ribbon + 0.35 * math.sin(clock + ribbon)) / 12.0
        y = center.y + 14.0 - height * vertical
        width = (7.0 + 27.0 * vertical) * strength
        phase = clock * (1.0 if ribbon % 2 else -0.8) + ribbon * 1.9
        points = []
        for step in range(11):
            t = step / 10.0
            x = center.x + math.cos(phase + t * math.tau * 0.78) * width
            lift = math.sin(phase + t * math.tau) * (2.2 + vertical * 2.4)
            points.append(Vec2(x, y + lift - t * 3.0))
        path = QPainterPath(qt(points[0]))
        for point in points[1:]:
            path.lineTo(qt(point))
        painter.setPen(world_pen(_alpha(colors[ribbon % len(colors)], 220 * strength), 2.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    # Debris orbits at different heights and depths; two pieces are recognizable skulls.
    for index in range(5):
        vertical = 0.2 + index * 0.16
        angle = clock * (1.1 + index * 0.06) + index * 2.2
        radius = (9.0 + vertical * 21.0) * strength
        point = center + Vec2(
            math.cos(angle) * radius,
            13.0 - height * vertical + math.sin(angle * 1.7) * 3.0,
        )
        if index in (1, 4):
            draw_skeleton_skull(
                painter,
                point,
                (3.0 + index * 0.22) * strength,
                1 if math.cos(angle) >= 0.0 else -1,
            )
            continue
        along = Vec2.from_angle(angle + index * 0.7, (4.8 + index * 0.45) * strength)
        side = along.rotated(math.pi / 2) * 0.38
        painter.setPen(world_pen(_alpha(BONE, 245 * strength), 1.7 * strength))
        painter.drawLine(qt(point - along), qt(point + along))
        painter.drawLine(qt(point - along * 0.45 - side), qt(point - along * 0.45 + side))
        painter.drawLine(qt(point + along * 0.45 - side), qt(point + along * 0.45 + side))
    painter.restore()


def draw_skeletal_grasp(painter: QPainter, actor) -> None:
    """Draw jointed skeletal arms and curling finger bones in place of tentacles."""
    spell = actor.skeletal_grasp
    if spell is None or spell.strength <= 0.0:
        return
    painter.save()
    strength = spell.strength
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for arm in spell.arms:
        side = Vec2(-arm.normal.y, arm.normal.x)
        painter.setPen(world_pen(_alpha(GRAVE_RIFT, 225 * strength), 2.4 * strength))
        painter.drawLine(qt(arm.base - side * 4.5), qt(arm.base + side * 4.5))
    for arm in spell.arms:
        _draw_skeletal_arm(painter, arm, spell.age, strength)
    painter.restore()


def _draw_skeletal_arm(
    painter: QPainter,
    arm: SkeletalArm,
    age: float,
    strength: float,
) -> None:
    side = Vec2(-arm.normal.y, arm.normal.x)
    reach = arm.tip - arm.base
    upper_length = reach.length() * 0.5
    elbow = arm.base + arm.normal * upper_length
    elbow += side * math.sin(age * 4.0 + arm.phase) * 4.8
    shoulder = arm.base + arm.normal * (2.0 * strength)
    forearm = arm.tip - elbow
    across = forearm.normalized().rotated(math.pi / 2) * 0.72

    # Dark silhouettes under the bone keep the limbs readable on pale windows.
    painter.setPen(world_pen(_alpha(ARM_SHADOW, 235 * strength), 2.45 * strength))
    painter.drawLine(qt(shoulder), qt(elbow))
    painter.drawLine(qt(elbow - across), qt(arm.tip - across))
    painter.drawLine(qt(elbow + across), qt(arm.tip + across))
    painter.setPen(world_pen(_alpha(BONE, 255 * strength), 1.35 * strength))
    painter.drawLine(qt(shoulder), qt(elbow))
    painter.setPen(world_pen(_alpha(BONE, 255 * strength), 0.82 * strength))
    painter.drawLine(qt(elbow - across), qt(arm.tip - across))
    painter.drawLine(qt(elbow + across), qt(arm.tip + across))
    painter.setPen(world_pen(_alpha(ARM_SHADOW, 255 * strength), 1.0 * strength))
    painter.setBrush(_alpha(BONE, 255 * strength))
    painter.drawEllipse(qt(shoulder), 1.35 * strength, 1.35 * strength)
    painter.drawEllipse(qt(elbow), 1.55 * strength, 1.55 * strength)
    _draw_bony_hand(painter, arm, elbow, strength)


def _draw_bony_hand(
    painter: QPainter,
    arm: SkeletalArm,
    elbow: Vec2,
    strength: float,
) -> None:
    forward = (arm.tip - elbow).normalized()
    if forward.length() < 0.1:
        forward = arm.normal
    side = forward.rotated(math.pi / 2)
    gripping = arm.held is not None
    palm = arm.tip - forward * ((4.2 if gripping else 1.5) * strength)
    if gripping:
        pulse = 0.82 + 0.18 * math.sin(arm.phase * 2.0 + arm.tip.x * 0.05)
        painter.setPen(world_pen(_alpha(GRIP_GLOW, 205 * strength), 1.5 * strength))
        painter.setBrush(_alpha(GRIP_GLOW, 42 * strength))
        painter.drawEllipse(qt(arm.tip), 8.5 * strength * pulse, 7.0 * strength * pulse)
    painter.setPen(world_pen(_alpha(ARM_SHADOW, 245 * strength), 1.0 * strength))
    painter.setBrush(_alpha(BONE, 255 * strength))
    palm_x = 2.8 if gripping else 1.9
    palm_y = 2.2 if gripping else 1.45
    painter.drawEllipse(qt(palm), palm_x * strength, palm_y * strength)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for index, spread in enumerate((-1.5, -0.5, 0.5, 1.5)):
        root = palm + side * (spread * 1.15 * strength)
        if gripping:
            outside = arm.tip + forward * (3.2 * strength)
            outside += side * (spread * 3.6 * strength)
            tip = arm.tip + forward * (0.6 * strength)
            tip += side * (spread * 0.72 * strength)
            bend = outside
        else:
            length = (4.2 - 0.3 * abs(index - 1.5)) * strength
            tip = arm.tip + forward * length + side * (spread * 1.15 * strength)
            bend = root.lerp(tip, 0.62)
        path = QPainterPath(qt(root))
        path.quadTo(qt(bend), qt(tip))
        shadow_width = 1.8 if gripping else 1.35
        bone_width = 0.9 if gripping else 0.68
        painter.setPen(world_pen(_alpha(ARM_SHADOW, 240 * strength), shadow_width * strength))
        painter.drawPath(path)
        painter.setPen(world_pen(_alpha(BONE, 255 * strength), bone_width * strength))
        painter.drawPath(path)
        if gripping:
            painter.setBrush(_alpha(BONE, 255 * strength))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(qt(tip), 0.85 * strength, 0.85 * strength)
            painter.setBrush(Qt.BrushStyle.NoBrush)


def draw_skull_face(
    painter: QPainter,
    actor,
    transforms,
    outline: QColor | None = None,
) -> None:
    head = transforms[actor.layout.head]
    draw_skeleton_skull(
        painter,
        head.end,
        actor.layout.head_radius,
        actor.facing,
        outline=outline,
    )


def draw_focus(
    painter: QPainter,
    actor,
    transforms,
    outline: QColor | None = None,
) -> None:
    center = actor.weapon.tip(transforms, actor.facing)
    draw_skeleton_skull(
        painter,
        center,
        actor.layout.head_radius * 0.72,
        actor.facing,
        outline=outline,
    )


def _orbit(actor, transforms, index: int) -> tuple[Vec2, float, float]:
    torso = transforms[actor.layout.torso]
    up = (torso.end - torso.start).normalized()
    forward = up.rotated(math.pi / 2) * actor.facing
    center = torso.start.lerp(torso.end, 0.62) + up * 3.0
    angle = actor.weapon.clock * ORBIT_SPEED + index * math.tau / 3.0
    depth = math.sin(angle)
    point = center + forward * (math.cos(angle) * ORBIT_RADIUS)
    point += up * (depth * ORBIT_HEIGHT + math.sin(angle * 2.0) * 1.5)
    return point, depth, 0.84 + 0.14 * (depth + 1.0)


def draw_orbiting_skulls(
    painter: QPainter,
    actor,
    transforms,
    front: bool,
    outline: QColor | None = None,
) -> None:
    for index in range(3):
        point, depth, scale = _orbit(actor, transforms, index)
        if (depth >= 0.0) != front:
            continue
        draw_skeleton_skull(
            painter,
            point,
            actor.layout.head_radius * 0.62 * scale,
            actor.facing,
            outline=outline,
        )
