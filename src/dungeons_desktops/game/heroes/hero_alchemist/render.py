"""Protective lab gear and Beastform Mutagen rendering for the Hero Alchemist."""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.defenders.minotaur import render as minotaur_render
from dungeons_desktops.game.heroes.hero_alchemist.poison import (
    POISON_DURATION,
    VENT_RELEASE,
)
from dungeons_desktops.render.primitives import qt, world_pen

BODY_WIDTH = 4.8
BODY = QColor(74, 136, 240)
BODY_FAR = QColor(46, 88, 164)
GEAR_EDGE = QColor(18, 23, 25)
CANISTER = QColor(72, 85, 78)
CANISTER_LIGHT = QColor(128, 146, 128)
CANISTER_BAND = QColor(36, 45, 40)
TUBE = QColor(32, 43, 38)
TUBE_STRIPE = QColor(92, 184, 102)
GLOVE = QColor(16, 18, 20)
METAL_GLOVE = QColor(128, 143, 143)
METAL_LIGHT = QColor(203, 218, 211)
GOGGLE_FRAME = QColor(35, 38, 36)
GOGGLE_GLASS = QColor(114, 225, 164)
GOGGLE_GLINT = QColor(221, 255, 233)
MASK = QColor(42, 47, 45)
MASK_RIB = QColor(125, 138, 126)
FILTER = QColor(166, 211, 91)
FILTER_GRID = QColor(48, 62, 43)
BEAST_SKIN = QColor(71, 111, 78)
BEAST_FAR = QColor(45, 73, 54)
BEAST_LIGHT = QColor(105, 151, 98)
BEAST_HOOF = QColor(28, 34, 30)
BACKGROUND = QColor(24, 26, 33)
POISON = QColor(104, 204, 74)
POISON_DARK = QColor(50, 126, 54)
OOZE_BODY = QColor(76, 174, 64)
OOZE_DARK = QColor(25, 91, 43)
OOZE_LIGHT = QColor(148, 232, 83)
OOZE_RIM = QColor(15, 51, 29)


def draw_poison_clouds(painter: QPainter, actor) -> None:
    """Draw deterministic drifting puffs behind the Alchemist and both of his forms."""
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for cloud in actor.poison_clouds:
        fade = smoothstep(clamp((POISON_DURATION - cloud.age) / 1.15, 0.0, 1.0))
        radius = cloud.radius
        if radius <= 0.0 or fade <= 0.0:
            continue
        core = QColor(POISON_DARK)
        core.setAlpha(round(26 * fade))
        painter.setBrush(core)
        painter.drawEllipse(qt(cloud.center), radius * 0.68, radius * 0.42)
        for index in range(12):
            angle = index * math.tau / 12.0 + cloud.age * (0.08 + 0.01 * (index % 3))
            distance = radius * (0.2 + 0.5 * ((index * 7) % 11) / 10.0)
            point = cloud.center + Vec2.from_angle(angle) * distance
            point += Vec2(0.0, -4.0 - 6.0 * math.sin(cloud.age * 1.7 + index))
            puff = radius * (0.13 + 0.035 * (index % 4))
            color = QColor(POISON if index % 3 else POISON_DARK)
            color.setAlpha(round((44 + 10 * math.sin(cloud.age * 2.0 + index)) * fade))
            painter.setBrush(color)
            painter.drawEllipse(qt(point), puff, puff * 0.78)

    if actor.vent_time is not None and actor.vent_time <= VENT_RELEASE:
        progress = smoothstep(clamp(actor.vent_time / VENT_RELEASE, 0.0, 1.0))
        back = Vec2(-actor.facing, 0.0)
        source = actor.center() + back * 10.0 + Vec2(0.0, -7.0)
        for index in range(5):
            distance = 5.0 + index * 7.0 * progress
            point = source + back * distance + Vec2(0.0, -3.0 * math.sin(index * 1.7))
            color = QColor(POISON)
            color.setAlpha(round(130 * (1.0 - index / 6.0)))
            painter.setBrush(color)
            size = 2.5 + index * 1.2
            painter.drawEllipse(qt(point), size, size * 0.75)

    toss = actor.ooze_toss
    if toss is not None:
        point = toss.position
        direction = Vec2(float(toss.facing), 0.0)
        painter.setPen(world_pen(OOZE_RIM, 1.2))
        painter.setBrush(OOZE_BODY)
        painter.drawEllipse(qt(point), 6.5, 5.2)
        painter.setPen(world_pen(OOZE_LIGHT, 1.2))
        for offset in (-2.4, 0.0, 2.4):
            root = point - direction * 4.0 + Vec2(0.0, offset)
            tip = root - direction * (7.0 + abs(offset)) + Vec2(0.0, offset * 0.6)
            painter.drawLine(qt(root), qt(tip))
    painter.restore()


def _draw_ooze_tendril(
    painter: QPainter,
    points: list[Vec2],
    widths: list[float],
    alpha: float = 1.0,
) -> None:
    rim = QColor(OOZE_RIM)
    rim.setAlpha(round(235 * alpha))
    body = QColor(OOZE_BODY)
    body.setAlpha(round(255 * alpha))
    shine = QColor(OOZE_LIGHT)
    shine.setAlpha(round(170 * alpha))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(rim)
    painter.drawPath(minotaur_render._taper(points, widths, grow=0.8))
    painter.setBrush(body)
    painter.drawPath(minotaur_render._taper(points, widths))
    if len(points) > 3:
        painter.setPen(world_pen(shine, 0.65))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(minotaur_render._smooth(points[1:-1], closed=False))


def draw_alchemical_ooze(painter: QPainter, ooze, outline: QColor | None = None) -> None:
    """Draw a low side-view dome which grows tendrils only while attacking."""
    painter.save()
    painter.translate(qt(ooze.contact()))
    painter.scale(float(ooze.facing) * ooze.ooze_scale, ooze.ooze_scale)

    dome = QPainterPath(qt(Vec2(-18.0, 0.0)))
    dome.cubicTo(qt(Vec2(-18.0, -14.0)), qt(Vec2(-9.0, -21.0)), qt(Vec2(0.0, -21.0)))
    dome.cubicTo(qt(Vec2(11.0, -21.0)), qt(Vec2(18.0, -13.0)), qt(Vec2(19.0, 0.0)))
    dome.quadTo(qt(Vec2(0.0, 5.0)), qt(Vec2(-18.0, 0.0)))
    dome.closeSubpath()
    painter.setPen(world_pen(outline or OOZE_RIM, 2.1 if outline else 1.35))
    color = OOZE_LIGHT if ooze.grow_flash > 0.0 else OOZE_BODY
    painter.setBrush(color)
    painter.drawPath(dome)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(170, 244, 105, 135))
    painter.drawEllipse(qt(Vec2(-5.0, -14.0)), 5.5, 2.4)
    painter.setBrush(QColor(34, 104, 43, 180))
    painter.drawEllipse(qt(Vec2(8.5, -8.0)), 2.1, 2.8)
    painter.drawEllipse(qt(Vec2(-10.0, -5.0)), 1.5, 2.0)

    strength = ooze.tendril_strength
    targets = [point for _, point in ooze.attack_targets]
    if strength > 0.0 and targets:
        roots = (Vec2(7.0, -16.0), Vec2(12.0, -10.0), Vec2(8.0, -4.0))
        for index, root in enumerate(roots):
            target = targets[index % len(targets)] + Vec2(0.0, (index - 1) * 3.0)
            _draw_attack_tendril(painter, ooze, root, target, strength, index)
    painter.restore()


def _draw_attack_tendril(
    painter: QPainter,
    ooze,
    root: Vec2,
    target: Vec2,
    strength: float,
    index: int,
) -> None:
    """One of three independently curling arms in the ooze's attack fan."""
    tip = Vec2(
        (target.x - ooze.contact().x) * ooze.facing / ooze.ooze_scale,
        (target.y - ooze.contact().y) / ooze.ooze_scale,
    )
    tip = root.lerp(tip, strength)
    direction = (tip - root).normalized()
    side_sign = ooze.attack_side if index % 2 == 0 else -ooze.attack_side
    side = Vec2(-direction.y, direction.x) * side_sign
    length = max(1.0, tip.distance_to(root))
    points = []
    for step in range(9):
        progress = step / 8.0
        base = root.lerp(tip, progress)
        whip = math.sin(math.pi * progress) * min(13.0, length * 0.22)
        ripple = math.sin(
            2.0 * math.pi * progress + ooze.wave * 5.0 + index * 1.7
        ) * 3.0
        points.append(base + side * (whip + ripple * math.sin(math.pi * progress)))
    _draw_ooze_tendril(
        painter,
        points,
        [6.0, 5.7, 5.3, 4.7, 4.0, 3.2, 2.3, 1.3, 0.5],
    )


def _frame(actor, transforms):
    torso = transforms[actor.layout.torso]
    up = (torso.end - torso.start).normalized()
    forward = up.rotated(math.pi / 2) * actor.facing
    return torso.start, torso.end, up, forward, actor.layout.head_radius


def _canister_center(actor, transforms) -> tuple[Vec2, Vec2, Vec2, float]:
    waist, shoulders, up, forward, radius = _frame(actor, transforms)
    center = shoulders.lerp(waist, 0.5) - forward * (1.42 * radius)
    return center, up, forward, radius


def draw_back_gear(painter: QPainter, actor, transforms) -> None:
    """Draw the gas canister behind the base alchemist body."""
    center, up, forward, radius = _canister_center(actor, transforms)
    half_width = 0.52 * radius
    top = center + up * 0.95 * radius
    bottom = center - up * 0.95 * radius
    path = QPainterPath(qt(top - forward * half_width))
    path.quadTo(qt(top + up * 0.18 * radius), qt(top + forward * half_width))
    path.lineTo(qt(bottom + forward * half_width))
    path.quadTo(
        qt(bottom - up * 0.18 * radius),
        qt(bottom - forward * half_width),
    )
    path.closeSubpath()

    painter.save()
    painter.setPen(world_pen(GEAR_EDGE, 1.0))
    painter.setBrush(CANISTER)
    painter.drawPath(path)
    painter.setPen(world_pen(CANISTER_LIGHT, 0.65))
    painter.drawLine(
        qt(top - forward * 0.28 * radius),
        qt(bottom - forward * 0.28 * radius),
    )
    painter.setPen(world_pen(CANISTER_BAND, 1.15))
    for height in (-0.52, 0.5):
        band = center + up * height * radius
        painter.drawLine(
            qt(band - forward * half_width),
            qt(band + forward * half_width),
        )
    valve = top + up * 0.2 * radius
    painter.setPen(world_pen(GEAR_EDGE, 0.8))
    painter.setBrush(CANISTER_BAND)
    painter.drawEllipse(qt(valve), 0.22 * radius, 0.15 * radius)
    painter.restore()


def draw_headgear(painter: QPainter, actor, transforms) -> None:
    """Draw a side-on goggle and respirator pointing where the actor faces."""
    head_bone = transforms[actor.layout.head]
    head = head_bone.end
    up = Vec2.from_angle(head_bone.angle)
    forward = up.rotated(math.pi / 2) * actor.facing
    radius = actor.layout.head_radius
    _draw_headgear_at(painter, head, up, forward, radius)


def _draw_headgear_at(
    painter: QPainter,
    head: Vec2,
    up: Vec2,
    forward: Vec2,
    radius: float,
) -> None:
    lens = head + forward * (0.32 * radius) + up * (0.45 * radius)

    painter.save()
    # Only the near lens is visible in profile; the band wraps around the skull.
    painter.setPen(world_pen(GOGGLE_FRAME, 1.5))
    painter.drawLine(
        qt(head - forward * 0.92 * radius + up * 0.38 * radius),
        qt(lens - forward * 0.15 * radius),
    )
    painter.setPen(world_pen(GOGGLE_FRAME, 1.2))
    painter.setBrush(GOGGLE_GLASS)
    painter.drawEllipse(qt(lens), 0.43 * radius, 0.34 * radius)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(GOGGLE_GLINT)
    painter.drawEllipse(
        qt(lens - forward * 0.1 * radius + up * 0.09 * radius),
        0.075 * radius,
        0.055 * radius,
    )

    # The respirator hugs the nose and mouth. Its two straps wrap around the skull.
    mask_top = head + forward * 0.46 * radius + up * 0.08 * radius
    nose = head + forward * 1.02 * radius - up * 0.12 * radius
    mouth = head + forward * 0.9 * radius - up * 0.52 * radius
    filter_center = head + forward * 0.68 * radius - up * 0.72 * radius
    chin = head + forward * 0.02 * radius - up * 0.96 * radius
    mask_back = head - forward * 0.24 * radius - up * 0.48 * radius
    painter.setPen(world_pen(GEAR_EDGE, 1.35))
    painter.drawLine(
        qt(head - forward * 0.95 * radius + up * 0.04 * radius),
        qt(mask_top),
    )
    painter.drawLine(
        qt(head - forward * 0.88 * radius - up * 0.28 * radius),
        qt(mask_back + forward * 0.25 * radius),
    )

    mask = QPainterPath(qt(mask_top))
    mask.lineTo(qt(nose))
    mask.lineTo(qt(mouth))
    mask.quadTo(qt(filter_center), qt(chin))
    mask.lineTo(qt(mask_back))
    mask.quadTo(qt(head + forward * 0.12 * radius - up * 0.2 * radius), qt(mask_top))
    mask.closeSubpath()
    painter.setPen(world_pen(GEAR_EDGE, 1.15))
    painter.setBrush(MASK)
    painter.drawPath(mask)

    # A round side cartridge sits below the mouth, like the supplied profile reference.
    painter.setPen(world_pen(GEAR_EDGE, 1.05))
    painter.setBrush(CANISTER_BAND)
    painter.drawEllipse(qt(filter_center), 0.48 * radius, 0.5 * radius)
    painter.setPen(world_pen(FILTER_GRID, 0.55))
    painter.setBrush(FILTER)
    painter.drawEllipse(qt(filter_center), 0.34 * radius, 0.36 * radius)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(qt(filter_center), 0.18 * radius, 0.2 * radius)
    painter.drawLine(
        qt(filter_center - up * 0.31 * radius),
        qt(filter_center + up * 0.31 * radius),
    )
    painter.drawLine(
        qt(filter_center - forward * 0.29 * radius),
        qt(filter_center + forward * 0.29 * radius),
    )
    painter.restore()


class _BeastFigure:
    """The minotaur renderer's exact ground pose driven by the mutagen actor."""

    def __init__(self, beast) -> None:
        self.beast = beast
        self.walking = smoothstep(beast.gait)
        self.lean = 0.22 if beast.attack_time is not None else 0.0
        self.squat = 3.0 if beast.attack_time is not None else 0.0
        step = 0.5 + 0.5 * math.cos(4.0 * math.pi * (beast.phase - 0.08))
        self.bob = self.walking * 2.2 * step
        self.roll = self.walking * 0.03 * math.sin(2.0 * math.pi * beast.phase)
        self.sway = self.walking * math.sin(2.0 * math.pi * beast.phase)

    def body(self, point: Vec2) -> Vec2:
        hip = Vec2(0.0, -minotaur_render.HIP_HEIGHT + self.squat + self.bob)
        local = point - Vec2(0.0, -minotaur_render.HIP_HEIGHT)
        return hip + local.rotated(minotaur_render.HUNCH + self.lean + self.roll)

    def hips(self) -> tuple[Vec2, Vec2]:
        base = Vec2(0.0, -minotaur_render.HIP_HEIGHT + self.squat + self.bob)
        shift = 0.8 * self.sway
        return base + Vec2(-2.5, shift), base + Vec2(2.5, -1.0 - shift)

    def feet(self) -> tuple[Vec2, Vec2]:
        amount = self.walking
        duty = 0.62
        lift = 6.0 * amount
        near = minotaur_render._foot(self.beast.phase, duty, 38.0, lift)
        far = minotaur_render._foot(self.beast.phase + 0.5, duty, 38.0, lift)
        ready_near, ready_far = minotaur_render.READY_FEET
        walk_near, walk_far = minotaur_render.WALK_FEET
        near_x = ready_near.x + (walk_near - ready_near.x) * amount
        far_x = ready_far.x + (walk_far - ready_far.x) * amount
        return (
            Vec2(near_x + near.x * amount, near.y),
            Vec2(far_x + far.x * amount, far.y),
        )

    def fists(self) -> tuple[Vec2, Vec2]:
        if self.beast.attack_time is not None:
            return self.beast.hand_positions()
        guard = minotaur_render.GUARD_NEAR, minotaur_render.FIST_FAR
        if self.walking <= 0.001:
            return guard
        length = (minotaur_render.UPPER_ARM + minotaur_render.FOREARM) * 0.96
        duty = 0.62
        way = 1.0 if self.beast.velocity.x * self.beast.facing >= 0.0 else -1.0
        near_leg = minotaur_render._foot(self.beast.phase, duty, 1.0, 1.0)
        far_leg = minotaur_render._foot(self.beast.phase + 0.5, duty, 1.0, 1.0)

        def hang(shoulder: Vec2, leg: Vec2, rest: float) -> Vec2:
            angle = math.pi * 0.5 + rest + leg.x * way * 0.62 * self.walking
            return shoulder + Vec2.from_angle(angle, length)

        near = hang(self.body(minotaur_render.NEAR_SHOULDER), near_leg, -0.08)
        far = hang(self.body(minotaur_render.FAR_SHOULDER), far_leg, -0.02)
        return guard[0].lerp(near, self.walking), guard[1].lerp(far, self.walking)


def _paint_beast_rear(ink: minotaur_render.Ink, fig: _BeastFigure) -> None:
    """Paint the minotaur layers that sit behind its chest."""
    far_shoulder = fig.body(minotaur_render.FAR_SHOULDER)
    _, far_hand = fig.fists()
    _, far_foot = fig.feet()
    _, far_hip = fig.hips()

    base = fig.body(Vec2(-11.0, -31.0))
    swish = math.sin(fig.beast.elapsed * 2.3)
    tail = [base]
    for index in range(1, 4):
        progress = index / 3.0
        tail.append(base + Vec2(-5.0 * progress + 2.0 * swish * progress**2, 12.0 * progress))
    ink.limb(tail, [3.0, 2.4, 2.0, 1.8], BEAST_FAR)
    ink.circle(tail[-1] + Vec2(0.0, 1.5), 2.6, BEAST_HOOF)

    minotaur_render._arm(ink, far_shoulder, far_hand, BEAST_FAR, 0.92, 1.0)
    minotaur_render._leg(ink, far_hip, far_foot, BEAST_FAR)


def _paint_beast_middle(ink: minotaur_render.Ink, fig: _BeastFigure) -> None:
    """Paint the near leg followed by the chest, matching the minotaur."""
    near_foot, _ = fig.feet()
    near_hip, _ = fig.hips()
    minotaur_render._leg(ink, near_hip, near_foot, BEAST_SKIN)
    minotaur_render._torso(ink, fig, BEAST_SKIN, BEAST_LIGHT)


def _paint_beast_front(ink: minotaur_render.Ink, fig: _BeastFigure) -> None:
    """Paint the near arm last, in front of the torso and head."""
    near_shoulder = fig.body(minotaur_render.NEAR_SHOULDER)
    near_hand, _ = fig.fists()
    minotaur_render._arm(ink, near_shoulder, near_hand, BEAST_SKIN, 1.0, 1.0)


def _draw_beast_tube(
    painter: QPainter,
    vat_center: Vec2,
    hand: Vec2,
    index: int,
) -> None:
    root = vat_center + Vec2(0.0, -6.0 + index * 12.0)
    tube = QPainterPath(qt(root))
    tube.cubicTo(
        qt(root + Vec2(-12.0, 2.0)),
        qt(hand + Vec2(-15.0, -5.0)),
        qt(hand),
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(GEAR_EDGE, 3.0))
    painter.drawPath(tube)
    painter.setPen(world_pen(TUBE_STRIPE if index == 0 else TUBE, 1.0))
    painter.drawPath(tube)


def _draw_beast_glove(painter: QPainter, elbow: Vec2, hand: Vec2) -> None:
    """Point the gauntlet and claws straight along the forearm, away from its elbow."""
    direction = hand - elbow
    angle = math.degrees(direction.angle()) if direction.length() > 1e-3 else 0.0
    painter.save()
    painter.translate(qt(hand))
    painter.rotate(angle)
    painter.setPen(world_pen(GEAR_EDGE, 1.25))
    painter.setBrush(METAL_GLOVE)
    painter.drawEllipse(qt(Vec2(0.0, 0.0)), 7.2, 7.0)
    painter.setPen(world_pen(METAL_LIGHT, 1.25))
    painter.drawLine(qt(Vec2(-3.0, -3.0)), qt(Vec2(3.0, -3.0)))
    for y in (-3.5, 0.0, 3.5):
        painter.drawLine(qt(Vec2(5.0, y)), qt(Vec2(12.0, y)))
    painter.restore()


def _draw_beast_head(
    painter: QPainter,
    fig: _BeastFigure,
    outline: QColor | None,
) -> None:
    """Paint the original round Alchemist head where the bull head would sit."""
    head = fig.body(Vec2(22.0, -58.0))
    head_radius = 7.2
    if outline is not None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outline)
        painter.drawEllipse(qt(head), head_radius + 1.6, head_radius + 1.6)
    painter.setPen(world_pen(BEAST_SKIN, 1.5))
    painter.setBrush(BACKGROUND)
    painter.drawEllipse(qt(head), head_radius, head_radius)
    head_up = Vec2(0.0, -1.0).rotated(minotaur_render.HUNCH + fig.lean + fig.roll)
    _draw_headgear_at(
        painter,
        head,
        head_up,
        head_up.rotated(math.pi / 2),
        head_radius,
    )


def draw_beastform(painter: QPainter, beast, outline: QColor | None = None) -> None:
    """Draw the minotaur's anatomy with the alchemist's head and equipment."""
    painter.save()
    painter.translate(qt(beast.feet))
    painter.scale(float(beast.facing) * beast.visual_scale, beast.visual_scale)
    fig = _BeastFigure(beast)

    # The enlarged vat remains behind the mutant's hump.
    vat_center = fig.body(Vec2(-17.0, -47.0))
    vat_points = [
        fig.body(Vec2(-23.0, -61.0)),
        fig.body(Vec2(-11.0, -61.0)),
        fig.body(Vec2(-11.0, -33.0)),
        fig.body(Vec2(-23.0, -33.0)),
    ]
    vat = QPainterPath(qt(vat_points[0]))
    vat.quadTo(qt(fig.body(Vec2(-17.0, -64.0))), qt(vat_points[1]))
    vat.lineTo(qt(vat_points[2]))
    vat.quadTo(qt(fig.body(Vec2(-17.0, -30.0))), qt(vat_points[3]))
    vat.closeSubpath()
    painter.setPen(world_pen(outline or GEAR_EDGE, 2.0 if outline else 1.3))
    painter.setBrush(CANISTER)
    painter.drawPath(vat)
    painter.setPen(world_pen(CANISTER_LIGHT, 0.9))
    painter.drawLine(qt(fig.body(Vec2(-20.0, -59.0))), qt(fig.body(Vec2(-20.0, -34.0))))
    painter.setPen(world_pen(CANISTER_BAND, 1.8))
    for y in (-56.0, -38.0):
        painter.drawLine(qt(fig.body(Vec2(-23.0, y))), qt(fig.body(Vec2(-11.0, y))))

    near_target, far_target = fig.fists()
    near_shoulder = fig.body(minotaur_render.NEAR_SHOULDER)
    far_shoulder = fig.body(minotaur_render.FAR_SHOULDER)
    near_elbow, near_hand = minotaur_render._ik(
        near_shoulder,
        near_target,
        minotaur_render.UPPER_ARM,
        minotaur_render.FOREARM,
        1.0,
    )
    far_elbow, far_hand = minotaur_render._ik(
        far_shoulder,
        far_target,
        minotaur_render.UPPER_ARM,
        minotaur_render.FOREARM,
        1.0,
    )
    if outline is not None:
        outline_ink = minotaur_render.Ink(painter, outline, 1.6)
        _paint_beast_rear(outline_ink, fig)
        _paint_beast_middle(outline_ink, fig)
        _paint_beast_front(outline_ink, fig)

    # Match the minotaur's anatomical paint order. The far gauntlet and hose sit
    # behind the chest; the original head sits behind the near arm and gauntlet.
    ink = minotaur_render.Ink(painter)
    _paint_beast_rear(ink, fig)
    _draw_beast_tube(painter, vat_center, far_hand, 1)
    _draw_beast_glove(painter, far_elbow, far_hand)
    _paint_beast_middle(ink, fig)
    _draw_beast_head(painter, fig, outline)
    _paint_beast_front(ink, fig)
    _draw_beast_tube(painter, vat_center, near_hand, 0)
    _draw_beast_glove(painter, near_elbow, near_hand)

    if beast.transforming:
        # A green-filled injector bridges the small starting frame into the larger body.
        progress = smoothstep(beast.elapsed / 0.85)
        injector = near_hand.lerp(Vec2(8.0, -43.0), progress)
        painter.setPen(world_pen(METAL_LIGHT, 1.0))
        painter.drawLine(qt(injector), qt(Vec2(5.0, -45.0)))
        painter.setPen(world_pen(FILTER, 3.0))
        painter.drawLine(
            qt(injector + Vec2(1.0, -1.0)),
            qt(injector + Vec2(6.0, -6.0)),
        )
    painter.restore()


def draw_gloves_and_tubes(painter: QPainter, actor, transforms) -> None:
    """Connect the rear canister to both black gloves with flexible hoses."""
    center, up, forward, radius = _canister_center(actor, transforms)
    hands = [
        transforms[chain.bones[-1]].end
        for chain in actor.layout.arms
        if chain.bones[-1] not in actor.severed
    ]
    painter.save()
    for index, hand in enumerate(hands):
        outlet = center + up * ((0.42 - index * 0.58) * radius)
        outside = outlet - forward * ((0.75 + index * 0.12) * radius)
        approach = hand - forward * (0.55 * radius) - up * (0.18 * radius)
        hose = QPainterPath(qt(outlet))
        hose.cubicTo(qt(outside), qt(approach), qt(hand))
        painter.setPen(world_pen(GEAR_EDGE, 2.25))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(hose)
        painter.setPen(world_pen(TUBE_STRIPE if index == 0 else TUBE, 0.75))
        painter.drawPath(hose)

    for chain in actor.layout.arms:
        final_name = chain.bones[-1]
        if final_name in actor.severed:
            continue
        forearm = transforms[final_name]
        cuff = forearm.start.lerp(forearm.end, 0.67)
        painter.setPen(world_pen(GLOVE, BODY_WIDTH * actor.layout.scale + 0.8))
        painter.drawLine(qt(cuff), qt(forearm.end))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(GLOVE)
        painter.drawEllipse(
            qt(forearm.end),
            1.45 * actor.layout.scale,
            1.45 * actor.layout.scale,
        )
    painter.restore()
