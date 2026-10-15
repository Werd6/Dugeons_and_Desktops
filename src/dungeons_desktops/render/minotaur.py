"""QPainter drawing of the minotaur.

A bold, simple silhouette: huge rounded shoulders high on a deep chest that tapers to
a narrow waist, a small bull head jutting out ahead of them whose forward-curving horns
carry the look, massive arms and short powerful legs. Its fists stay cocked in front of
its chest. Both fists rise and slam the ground, one hoof rises and slams for a stomp,
and a grabbed adventurer is hurled from the near fist.
Everything is drawn in its own frame (facing +x, feet at the origin, y down), placed by
the sim's eased lean and crouch (`Minotaur.posture`), and mirrored to face the other
way. Its hooves step by IK onto a rolling walk cycle
(eased in and out by `Minotaur.gait`, stretched into a gallop by `Minotaur.gallop`)
from a wide-braced ready stance, and blend into planted stances for its attacks. On a
wall its hands grip above and its hooves kick below.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.systems.minotaur import (
    CLIMB_REACH,
    CLIMB_SPEED,
    GUARD_NEAR,
    HIP_HEIGHT,
    WALL_GAP,
    Minotaur,
)

HIDE = QColor(116, 72, 46)
HIDE_FAR = QColor(72, 44, 30)
HIDE_LIGHT = QColor(164, 118, 84)
HIDE_RAGE = QColor(176, 52, 38)
HIDE_DEAD = QColor(96, 70, 56)
HORN = QColor(236, 224, 194)
HORN_FAR = QColor(176, 164, 138)
HORN_TIP = QColor(70, 58, 46)
HOOF = QColor(34, 26, 22)
EYE = QColor(20, 12, 10)
EYE_RAGE = QColor(255, 72, 36)
EYE_GLOW = QColor(255, 80, 30, 110)
NOSTRIL = QColor(36, 20, 16)
STEAM = QColor(236, 236, 242)

UPPER_ARM = 15.2
FOREARM = 14.2
THIGH = 14.0
SHIN = 11.5
PASTERN = 6.6
"""Hoof to hock (it stands on its toes like a bull)."""

TORSO = [
    Vec2(-4.9, -22.1),
    Vec2(-10.8, -32.4),
    Vec2(-14.5, -42.8),
    Vec2(-14.1, -54.8),
    Vec2(-7.6, -63.3),
    Vec2(1.2, -65.1),
    Vec2(7.9, -63.3),
    Vec2(12.4, -56.2),
    Vec2(15.5, -46.6),
    Vec2(14.2, -39.6),
    Vec2(9.0, -34.0),
    Vec2(7.1, -29.4),
    Vec2(6.3, -24.5),
]
"""A deep chest under a hump of muscle, tapering to a narrow waist."""
CHEST_LIGHT = [
    Vec2(4.4, -57.1),
    Vec2(12.7, -54.2),
    Vec2(15.1, -45.5),
    Vec2(12.6, -38.1),
    Vec2(7.5, -33.7),
    Vec2(6.8, -44.3),
]
NECK = Vec2(11.4, -60.0)
"""What its head pitches about: high on the front of its hump."""
NECK_SHAPE = [Vec2(1.2, -64.1), Vec2(12.9, -65.2), Vec2(18.9, -53.0), Vec2(12.0, -46.6)]
"""Short and thick, jutting its head out ahead of its shoulders."""
HEAD_SHAPE = [
    Vec2(14.3, -62.5),
    Vec2(16.8, -65.4),
    Vec2(20.8, -62.8),
    Vec2(23.6, -59.2),
    Vec2(26.0, -55.9),
    Vec2(27.3, -53.6),
    Vec2(24.8, -51.3),
    Vec2(20.9, -52.0),
    Vec2(17.1, -56.1),
]
MUZZLE = [
    Vec2(23.6, -57.2),
    Vec2(26.0, -55.9),
    Vec2(27.2, -53.7),
    Vec2(25.7, -52.0),
    Vec2(23.8, -53.9),
]
SNOUT = Vec2(26.2, -54.5)
EYE_AT = Vec2(21.2, -59.4)
EAR = [Vec2(15.2, -61.8), Vec2(10.8, -61.7), Vec2(12.7, -59.6), Vec2(15.7, -59.6)]
HORN_NEAR = [
    Vec2(16.3, -63.7),
    Vec2(15.9, -68.3),
    Vec2(18.3, -72.2),
    Vec2(23.3, -74.6),
    Vec2(32.2, -74.6),
]
HORN_NEAR_W = [6.5, 5.5, 4.2, 2.6, 0.9]
HORN_FAR_LINE = [Vec2(19.9, -60.6), Vec2(26.2, -62.2), Vec2(31.2, -64.5), Vec2(35.5, -67.5)]
HORN_FAR_W = [5.2, 4.0, 2.4, 0.9]
HUNCH = 0.18
"""Extra forward hunch of its whole upper body (baked into the sim's body points)."""

NEAR_SHOULDER = Vec2(6.0, -53.5)
FAR_SHOULDER = Vec2(0.5, -57.5)
"""Where the arms meet the torso: on the shoulder, the near one a little forward and
the far one on the other side of the chest."""
CLIMB_SHOULDERS = (Vec2(10.0, -53.0), Vec2(4.0, -55.0))
"""Squared up to a wall it's climbing."""
DELTOID = 10.4
FIST_FAR = Vec2(-10.0, -32.0)
"""Its far fist, back by the ribs, behind the chest."""
FREE_HANG = Vec2(-1.0, 26.0)
"""Where a hand hangs from its shoulder."""
CLIMB_HANDS = (Vec2(1.0, -1.0), Vec2(-2.0, -1.5))
"""Pushing up off the ground, as at the end of a mantle."""
LIP_NEAR, LIP_FAR = CLIMB_HANDS
"""Its hands on a lip, about its top corner."""
HAND_HOLD = -64.0
HOOF_HOLD = -12.0
"""How high its hands and hooves grip a wall it's climbing, mid-stroke."""
CLIMB_DUTY = 0.6
"""How much of its climbing cycle each hand or hoof spends gripping the wall."""
READY_FEET = (Vec2(-15.0, 0.0), Vec2(16.0, 0.0))
"""Near hoof back, far hoof forward: braced wide."""
WALK_FEET = (-4.0, 4.0)
"""Where each hoof's stride is centered, walking."""

STANCE_FEET = {
    "skid": (Vec2(-1.0, 0.0), Vec2(13.0, 0.0)),
    "stomp": (Vec2(-12.0, 0.0), Vec2(14.0, 0.0)),
    "punch": (Vec2(-10.0, 0.0), Vec2(12.0, 0.0)),
    "smash": (Vec2(-14.0, 0.0), Vec2(8.0, 0.0)),
    "hurl": (Vec2(-8.0, 0.0), Vec2(14.0, 0.0)),
}


def _qt(point: Vec2) -> QPointF:
    return QPointF(point.x, point.y)


def _pen(color: QColor, width: float) -> QPen:
    return QPen(
        color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
    )


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = clamp(t, 0.0, 1.0)
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(alpha))))
    return result


def _smooth(points: list[Vec2], closed: bool = True) -> QPainterPath:
    """A Catmull-Rom curve through `points`."""
    path = QPainterPath(_qt(points[0]))
    n = len(points)
    for i in range(n if closed else n - 1):
        p0 = points[i - 1] if closed or i > 0 else points[0]
        p1, p2 = points[i], points[(i + 1) % n]
        p3 = points[(i + 2) % n] if closed or i + 2 < n else p2
        path.cubicTo(_qt(p1 + (p2 - p0) / 6.0), _qt(p2 - (p3 - p1) / 6.0), _qt(p2))
    if closed:
        path.closeSubpath()
    return path


def _taper(points: list[Vec2], widths: list[float], grow: float = 0.0) -> QPainterPath:
    """One solid tapered shape along `points`, `widths` across at each (its pieces
    overlap, so fill it with the winding rule)."""
    radii = [w * 0.5 + grow for w in widths]
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for a, b, ra, rb in zip(points, points[1:], radii, radii[1:], strict=False):
        side = (b - a).normalized().rotated(math.pi / 2)
        # Clockwise on screen, like `addEllipse`, so the overlaps don't cancel out.
        corners = [a - side * ra, b - side * rb, b + side * rb, a + side * ra]
        path.moveTo(_qt(corners[0]))
        for c in corners[1:]:
            path.lineTo(_qt(c))
        path.closeSubpath()
    for p, r in zip(points, radii, strict=False):
        path.addEllipse(_qt(p), r, r)
    return path


def _ik(root: Vec2, target: Vec2, upper: float, lower: float, bend: float) -> tuple[Vec2, Vec2]:
    """The joint of a two-bone limb from `root` reaching for `target` (pulled in if out
    of reach), bowing to the +angle side for `bend` +1; and the end."""
    offset = target - root
    reach = upper + lower - 1e-3
    distance = offset.length()
    if distance > reach:
        target = root + offset.normalized() * reach
        distance = reach
    distance = max(distance, 1e-3)
    cos_a = clamp(
        (upper * upper + distance * distance - lower * lower) / (2 * upper * distance), -1, 1
    )
    angle = offset.angle() + bend * math.acos(cos_a)
    return root + Vec2.from_angle(angle, upper), target


def _foot(phase: float, duty: float, stride: float, lift: float) -> Vec2:
    """A hoof through its stride, relative to under its hip: planted and sliding back
    for `duty` of the cycle, then lifted and swung forward. The swing leaves and meets
    the ground at the planted hoof's own speed, so a hoof never jerks as it lifts or
    lands."""
    p = phase % 1.0
    if p < duty:
        return Vec2(stride * (0.5 - p / duty), 0.0)
    q = (p - duty) / (1.0 - duty)
    tangent = -stride * (1.0 - duty) / duty * 0.7
    q2, q3 = q * q, q * q * q
    x = (
        (2 * q3 - 3 * q2 + 1) * (-0.5 * stride)
        + (q3 - 2 * q2 + q) * tangent
        + (-2 * q3 + 3 * q2) * (0.5 * stride)
        + (q3 - q2) * tangent
    )
    return Vec2(x, -(math.sin(math.pi * q) ** 2) * lift)


class Ink:
    """Fills its shapes in their own colors, or (for the outline pass) everything in one
    color, grown by `grow`."""

    def __init__(self, painter: QPainter, outline: QColor | None = None, grow: float = 0.0):
        self.painter = painter
        self.outline = outline
        self.grow = grow

    def color(self, color: QColor) -> QColor:
        return self.outline if self.outline is not None else color

    def limb(self, points: list[Vec2], widths: list[float], color: QColor) -> None:
        painter = self.painter
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color(color))
        painter.drawPath(_taper(points, widths, self.grow))

    def shape(self, path: QPainterPath, color: QColor) -> None:
        painter = self.painter
        if self.outline is not None:
            painter.setPen(_pen(self.outline, 2.0 * self.grow))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color(color))
        painter.drawPath(path)

    def blob(self, points: list[Vec2], color: QColor) -> None:
        self.shape(_smooth(points), color)

    def circle(self, center: Vec2, radius: float, color: QColor) -> None:
        path = QPainterPath()
        path.addEllipse(_qt(center), radius, radius)
        self.shape(path, color)

    @property
    def detail(self) -> bool:
        """Inner detail (shading, eyes) only in the fill pass."""
        return self.outline is None


class Figure:
    """Everything about its pose the drawing needs, worked out once per frame."""

    def __init__(self, bull: Minotaur) -> None:
        self.bull = bull
        self.lean, self.squat = bull.posture()
        p = bull.phase
        walking = smoothstep(bull.gait) * (1.0 - smoothstep(bull.stance))
        self.walking = walking
        self.charging = bull.action in ("charge", "skid")
        gallop = bull.gallop
        # Heaviest just after each footfall (a hoof lands at every half cycle), lightest
        # mid-stride: a smooth roll, never a bounce.
        step = 0.5 + 0.5 * math.cos(4.0 * math.pi * (p - 0.08))
        bound = 0.5 + 0.5 * math.cos(2.0 * math.pi * (p - 0.1))
        self.bob = walking * (2.2 * step * (1.0 - gallop) + 3.0 * bound * gallop)
        self.roll = walking * (0.03 + 0.04 * gallop) * math.sin(2.0 * math.pi * p)
        if bull.on_wall:
            climbing = clamp(bull.climb_speed / CLIMB_SPEED, 0.0, 1.0)
            self.roll += 0.03 * climbing * math.sin(2.0 * math.pi * bull.climb_phase)
        self.nod = walking * 0.07 * math.cos(4.0 * math.pi * (p - 0.16))
        self.sway = walking * math.sin(2.0 * math.pi * p)
        self.swing = walking * math.cos(2.0 * math.pi * p)
        breath = math.sin(bull.time * (5.0 if bull.action == "winded" else 2.2))
        self.breath = breath * (1.2 if bull.action == "winded" else 0.5)
        self.pitch = bull.pitch + self.nod

    def body(self, point: Vec2) -> Vec2:
        """An upper-body point, leaning, crouched and rolling."""
        lean = self.lean + self.roll + HUNCH
        hip = Vec2(0.0, -HIP_HEIGHT + self.squat + self.bob)
        swell = 1.0 + 0.025 * self.breath if point.x > 4.0 else 1.0
        local = Vec2(point.x * swell, point.y) - Vec2(0.0, -HIP_HEIGHT)
        return hip + local.rotated(lean)

    def head(self, point: Vec2) -> Vec2:
        """A head point, pitched about the neck."""
        pivot = self.body(NECK)
        return pivot + (point - NECK).rotated(self.lean + self.roll + HUNCH + self.pitch)

    def hips(self) -> tuple[Vec2, Vec2]:
        base = Vec2(0.0, -HIP_HEIGHT + self.squat + self.bob)
        shift = 0.8 * self.sway
        return base + Vec2(-2.5, shift), base + Vec2(2.5, -1.0 - shift)

    def feet(self) -> tuple[Vec2, Vec2]:
        """Near and far hoof."""
        bull = self.bull
        near_hip, far_hip = self.hips()
        if bull.dead:
            return Vec2(5.0, 0.0), Vec2(-3.0, 0.0)
        near, far = self._ground_feet(near_hip, far_hip)
        climb = smoothstep(bull.slung)
        if climb > 0.0:
            wall_near, wall_far = self._wall_feet()
            near, far = near.lerp(wall_near, climb), far.lerp(wall_far, climb)
        return near, far

    def _ground_feet(self, near_hip: Vec2, far_hip: Vec2) -> tuple[Vec2, Vec2]:
        bull = self.bull
        if bull.flight is not None:
            if bull.velocity.y < 0.0:
                return near_hip + Vec2(7.0, 15.0), far_hip + Vec2(-4.0, 18.0)
            return near_hip + Vec2(4.0, 21.0), far_hip + Vec2(-3.0, 22.0)
        g = bull.gallop
        duty = 0.62 - 0.2 * g
        stride = duty * bull.cycle()
        amount = smoothstep(bull.gait)
        lift = (6.0 + 4.0 * g) * amount
        way = bull.stride_way
        near = _foot(bull.phase, duty, stride, lift)
        far = _foot(bull.phase + 0.5, duty, stride, lift)
        (ready_near, ready_far), (walk_near, walk_far) = READY_FEET, WALK_FEET
        near_x = ready_near.x + (walk_near - ready_near.x) * amount
        far_x = ready_far.x + (walk_far - ready_far.x) * amount
        near = Vec2(near_x + near.x * way * amount, near.y)
        far = Vec2(far_x + far.x * way * amount, far.y)
        planted = smoothstep(bull.stance)
        if planted > 0.0:
            set_near, set_far = self._stance_feet()
            near, far = near.lerp(set_near, planted), far.lerp(set_far, planted)
        if bull.action == "stomp":
            near = bull.hoof()
        return near, far

    def fists(self) -> tuple[Vec2, Vec2]:
        """Near and far fist. Walking, each arm hangs and swings opposite its hoof."""
        guard = GUARD_NEAR, FIST_FAR
        if self.walking <= 0.001:
            return guard
        bull = self.bull
        g = bull.gallop
        duty = 0.62 - 0.2 * g
        amp = (0.62 + 0.28 * g) * self.walking
        way = bull.stride_way
        length = (UPPER_ARM + FOREARM) * 0.96
        near_leg = _foot(bull.phase, duty, 1.0, 1.0)
        far_leg = _foot(bull.phase + 0.5, duty, 1.0, 1.0)

        def hang(shoulder: Vec2, leg: Vec2, rest: float) -> Vec2:
            # Straight down is pi/2. The arm swings back as its own hoof swings forward.
            angle = math.pi * 0.5 + rest + leg.x * way * amp
            return shoulder + Vec2.from_angle(angle, length)

        near = hang(self.body(NEAR_SHOULDER), near_leg, -0.08)
        far = hang(self.body(FAR_SHOULDER), far_leg, -0.02)
        t = self.walking
        return guard[0].lerp(near, t), guard[1].lerp(far, t)

    def _stance_feet(self) -> tuple[Vec2, Vec2]:
        bull = self.bull
        if bull.stance_kind == "windup":
            scrape = math.sin(bull.paw * 2.0 * math.pi * 3.2)
            return Vec2(-9.0, 0.0), Vec2(9.0 + 6.0 * scrape, -max(0.0, scrape) * 4.0)
        return STANCE_FEET[bull.stance_kind]

    def _wall_feet(self) -> tuple[Vec2, Vec2]:
        bull = self.bull
        wall = WALL_GAP - 1.5
        phase = bull.climb_phase
        near, far = _climb_limb(phase + 0.5), _climb_limb(phase)
        # Swung out off the wall for a swipe, its hooves push off the wall.
        push = _lunge(bull) * 0.5
        near = Vec2(wall + 0.7 * near.x, HOOF_HOLD + near.y) - push
        far = Vec2(wall - 1.0 + 0.7 * far.x, HOOF_HOLD + 2.0 + far.y) - push
        slide = smoothstep(bull.slide)
        if slide > 0.0:
            near = near.lerp(Vec2(wall, -6.0), slide)
            far = far.lerp(Vec2(wall - 1.0, -2.0), slide)
        progress = bull.haul_progress()
        if (progress is None and bull.on_wall) or (progress is not None and progress[0] == "grab"):
            return near, far
        if progress is None:
            kind, t = "mantle", 1.0
        else:
            kind, t = progress
        over = t if kind == "mantle" else 1.0 - t
        lift = smoothstep(clamp((over - 0.3) / 0.6, 0.0, 1.0))
        tuck = smoothstep(min(1.0, over / 0.3))
        return (
            near.lerp(Vec2(wall - 2.0 + 6.0 * lift, -12.0 - 6.0 * lift), tuck),
            far.lerp(Vec2(wall - 4.0, -4.0), tuck),
        )

    def hands_on_wall(self) -> tuple[Vec2, Vec2] | None:
        bull = self.bull
        progress = bull.haul_progress()
        root = bull.root()
        if progress is not None and progress[0] != "grab":
            haul = bull.haul
            assert haul is not None
            lip = haul.end if progress[0] == "mantle" else haul.start
            local = Vec2((lip.x - root.x) * bull.facing, lip.y - root.y)
            return local + LIP_NEAR, local + LIP_FAR
        if not bull.on_wall and progress is None:
            return None
        # Climbing, sliding, or letting go of the wall's bottom onto the walk below it.
        wall = WALL_GAP + 0.5
        held = _lunge(bull)
        phase = bull.climb_phase
        near, far = _climb_limb(phase), _climb_limb(phase + 0.5)
        near = Vec2(wall + near.x, HAND_HOLD + near.y) - held
        far = Vec2(wall - 0.5 + far.x, HAND_HOLD + 3.0 + far.y) - held
        slide = smoothstep(bull.slide)
        if slide > 0.0:
            near = near.lerp(Vec2(wall, -70.0) - held, slide)
            far = far.lerp(Vec2(wall - 0.5, -64.0) - held, slide)
        lip = bull.lip()
        if lip is not None:
            top = lip - root.y
            if near.y < top + LIP_NEAR.y:
                near = Vec2(WALL_GAP, top) + LIP_NEAR
            if far.y < top + LIP_FAR.y:
                far = Vec2(WALL_GAP, top) + LIP_FAR
        return near, far


def _lunge(bull: Minotaur) -> Vec2:
    """How far its body has swung out off the wall, in its own frame."""
    return Vec2(bull.lunge.x * bull.facing, bull.lunge.y)


def _climb_limb(phase: float) -> Vec2:
    """A hand or hoof through its climb, about its hold: gripping the wall (sliding
    down past the body as it rises) for `CLIMB_DUTY` of the cycle, then pulled off the
    wall and reached up for the next hold, leaving and meeting the wall at its pace."""
    stride = CLIMB_DUTY * CLIMB_REACH
    p = phase % 1.0
    if p < CLIMB_DUTY:
        return Vec2(0.0, stride * (p / CLIMB_DUTY - 0.5))
    q = (p - CLIMB_DUTY) / (1.0 - CLIMB_DUTY)
    tangent = stride * (1.0 - CLIMB_DUTY) / CLIMB_DUTY * 0.7
    q2, q3 = q * q, q * q * q
    y = (
        (2 * q3 - 3 * q2 + 1) * (0.5 * stride)
        + (q3 - 2 * q2 + q) * tangent
        + (-2 * q3 + 3 * q2) * (-0.5 * stride)
        + (q3 - q2) * tangent
    )
    return Vec2(-4.0 * math.sin(math.pi * q) ** 2, y)


def draw_minotaur(painter: QPainter, bull: Minotaur, outline: QColor | None = None) -> None:
    fig = Figure(bull)
    root = bull.root()
    painter.save()
    painter.translate(_qt(root))
    painter.scale(float(bull.facing), 1.0)
    if bull.dead and bull.tilt > 0.0:
        fallen = smoothstep(bull.tilt)
        painter.translate(0.0, -12.0 * fallen)
        painter.rotate(math.degrees(-0.5 * math.pi * fallen))
    if outline is not None:
        _paint(Ink(painter, outline, 1.6), fig)
    _paint(Ink(painter), fig)
    painter.restore()


def _palette(bull: Minotaur) -> tuple[QColor, QColor, QColor]:
    if bull.dead:
        return HIDE_DEAD, HIDE_FAR.darker(110), HIDE_LIGHT.darker(125)
    rage = bull.fury * 0.65
    return (
        _mix(HIDE, HIDE_RAGE, rage),
        _mix(HIDE_FAR, HIDE_RAGE.darker(175), rage),
        _mix(HIDE_LIGHT, HIDE_RAGE.lighter(135), rage * 0.8),
    )


def _paint(ink: Ink, fig: Figure) -> None:
    bull = fig.bull
    hide, far, light = _palette(bull)
    slung = smoothstep(bull.slung)
    climb_near, climb_far = CLIMB_SHOULDERS
    near_shoulder = fig.body(NEAR_SHOULDER.lerp(climb_near, slung))
    far_shoulder = fig.body(FAR_SHOULDER.lerp(climb_far, slung))
    near_hand, far_hand = fig.fists()
    if bull.dead:
        let_go = smoothstep(min(1.0, bull.down_time / 0.5))
        near_hand = near_hand.lerp(near_shoulder + FREE_HANG, let_go)
        far_hand = far_hand.lerp(far_shoulder + FREE_HANG, let_go)
    elif slung > 0.0:
        wall = fig.hands_on_wall() or CLIMB_HANDS
        near_hand, far_hand = near_hand.lerp(wall[0], slung), far_hand.lerp(wall[1], slung)
    smashing = bull.action == "smash" and not bull.dead
    hurling = bull.action == "hurl" and not bull.dead
    punching = bull.action == "punch" and not bull.dead
    swiping = bull.action == "swipe" and not bull.dead
    if smashing:
        near_hand, far_hand = bull.smash_hands()
    elif hurling:
        near_hand = bull.grip()
    elif punching:
        near_hand = bull.fist()
    elif swiping:
        # One hand keeps hold of the wall; the other lashes out at him.
        hold = bull.swipe_hold()
        near_hand = near_hand.lerp(bull.swipe_grip(), hold)
        far_hand = far_hand.lerp(bull.swipe_fist(), hold)
    near_foot, far_foot = fig.feet()
    near_hip, far_hip = fig.hips()

    if fig.charging and ink.detail:
        _streaks(ink, fig)
    _tail(ink, fig, far)
    # The far arm is on the other side of the body: behind the legs, chest and head.
    _arm(ink, far_shoulder, far_hand, _mix(far, hide, 0.6), 0.92, 1.0)
    _horn(ink, fig, HORN_FAR_LINE, HORN_FAR_W, HORN_FAR)
    _leg(ink, far_hip, far_foot, far)
    _leg(ink, near_hip, near_foot, hide)
    _torso(ink, fig, hide, light)
    _head(ink, fig, hide, light)
    # The near arm is in front of the body, and in front of the horns where they cross.
    _arm(ink, near_shoulder, near_hand, hide, 1.0, 1.0)
    if ink.detail and not bull.dead:
        _steam(ink, fig)


def _leg(ink: Ink, hip: Vec2, hoof: Vec2, color: QColor) -> None:
    rake = clamp(-1.0 + 0.3 * (hip.x - hoof.x), -4.0, 3.0)
    hock = hoof + Vec2(rake, -math.sqrt(PASTERN * PASTERN - rake * rake))
    knee, hock = _ik(hip, hock, THIGH, SHIN, -1.0)
    ink.limb([hip, knee, hock, hoof + Vec2(0.5, -2.5)], [15.5, 9.0, 5.5, 5.5], color)
    path = QPainterPath(_qt(hoof + Vec2(-4.0, -4.5)))
    for p in (Vec2(4.5, -4.5), Vec2(6.5, 0.5), Vec2(-4.5, 0.5)):
        path.lineTo(_qt(hoof + p))
    path.closeSubpath()
    ink.shape(path, HOOF)


def _arm(ink: Ink, shoulder: Vec2, hand: Vec2, color: QColor, size: float, bend: float) -> None:
    """A massive arm: a round deltoid, a thick forearm and a big fist.

    `bend` +1 leaves the point of the elbow trailing, so the arm flexes forward
    instead of bending back on itself.
    """
    elbow, hand = _ik(shoulder, hand, UPPER_ARM, FOREARM, bend)
    points = [shoulder, elbow, elbow.lerp(hand, 0.45), hand]
    widths = [13.8 * size, 11.6 * size, 13.8 * size, 10.4 * size]
    contour = color.darker(150)
    if ink.detail:
        ink.limb(points, [w + 1.8 for w in widths], contour)
        ink.circle(hand, 7.8 * size, contour)
    ink.limb(points, widths, color)
    ink.circle(hand, 6.9 * size, color)
    if ink.detail:
        ink.circle(shoulder, DELTOID * size + 0.6, color.darker(125))
    ink.circle(shoulder, DELTOID * size, color)


def _torso(ink: Ink, fig: Figure, hide: QColor, light: QColor) -> None:
    body = _smooth([fig.body(p) for p in TORSO])
    ink.shape(body, hide)
    if not ink.detail:
        return
    painter = ink.painter
    painter.save()
    painter.setClipPath(body, Qt.ClipOperation.IntersectClip)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(light)
    painter.drawPath(_smooth([fig.body(p) for p in CHEST_LIGHT]))
    painter.restore()


def _head(ink: Ink, fig: Figure, hide: QColor, light: QColor) -> None:
    h = fig.head
    bull = fig.bull
    ink.blob([h(p) for p in NECK_SHAPE], hide)
    ink.blob([h(p) for p in EAR], hide.darker(125))
    ink.blob([h(p) for p in HEAD_SHAPE], hide)
    _horn(ink, fig, HORN_NEAR, HORN_NEAR_W, HORN)
    if not ink.detail:
        return
    painter = ink.painter
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(light)
    painter.drawPath(_smooth([h(p) for p in MUZZLE]))
    painter.setBrush(NOSTRIL)
    painter.drawEllipse(_qt(h(SNOUT)), 1.3, 1.0)
    eye = h(EYE_AT)
    if bull.dead:
        painter.setPen(_pen(EYE, 1.1))
        painter.drawLine(_qt(eye - Vec2(1.4, 0.0)), _qt(eye + Vec2(1.4, 0.0)))
        return
    if bull.fury > 0.05:
        painter.setBrush(_alpha(EYE_GLOW, 200 * bull.fury))
        painter.drawEllipse(_qt(eye), 3.4, 3.0)
    painter.setBrush(_mix(EYE, EYE_RAGE, bull.fury))
    painter.drawEllipse(_qt(eye), 1.5, 1.3)


def _horn(ink: Ink, fig: Figure, line: list[Vec2], widths: list[float], color: QColor) -> None:
    points = [fig.head(p) for p in line]
    ink.limb(points, widths, color)
    if ink.detail:
        ink.limb(points[-2:], widths[-2:], HORN_TIP if color is HORN else HORN_TIP.darker(130))


def _tail(ink: Ink, fig: Figure, color: QColor) -> None:
    bull = fig.bull
    swish = math.sin(bull.time * 2.3) * (1.0 + bull.fury * 1.5)
    base = fig.body(Vec2(-11.0, -31.0))
    points = [base]
    for i in range(1, 4):
        t = i / 3.0
        points.append(base + Vec2(-5.0 * t + 2.0 * swish * t * t, 12.0 * t))
    ink.limb(points, [3.0, 2.4, 2.0, 1.8], color)
    ink.circle(points[-1] + Vec2(0.0, 1.5), 2.6, HIDE_FAR.darker(140))


def _steam(ink: Ink, fig: Figure) -> None:
    """Snorts of steam from its nostrils while it's enraged (and a puff when winded)."""
    bull = fig.bull
    strength = max(bull.fury, 0.6 if bull.action == "winded" else 0.0)
    if strength <= 0.02:
        return
    painter = ink.painter
    nostril = fig.head(SNOUT)
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(3):
        age = (bull.time * 1.6 + i / 3.0) % 1.0
        drift = Vec2(3.0 + 8.0 * age, 2.0 - 5.0 * age)
        radius = 1.4 + 3.0 * age
        painter.setBrush(_alpha(STEAM, 170 * strength * (1.0 - age)))
        painter.drawEllipse(_qt(nostril + drift), radius, radius * 0.8)


def _streaks(ink: Ink, fig: Figure) -> None:
    """Speed lines trailing the charge."""
    bull = fig.bull
    speed = abs(bull.speed) / 230.0
    painter = ink.painter
    for i, y in enumerate((-50.0, -38.0, -24.0)):
        flick = (bull.time * 7.0 + i * 0.37) % 1.0
        length = (10.0 + 12.0 * flick) * speed
        start = Vec2(-18.0 - 4.0 * i, y + fig.squat)
        painter.setPen(_pen(_alpha(STEAM, 120 * speed * (1.0 - flick)), 1.2))
        painter.drawLine(_qt(start), _qt(start - Vec2(length, 0.0)))
