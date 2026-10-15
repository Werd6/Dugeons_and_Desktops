"""QPainter drawing of the displacer beast.

It's drawn in its own body frame (x toward the head, y toward its feet, origin at the
body center), so the same picture stands on a window top, clings flat to a side or
hangs belly-up under an underside. Six legs step in a ripple (a bound when it lopes),
the shoulder blades roll, the head stays low and level, and the tail and the two
barbed shoulder tentacles never stop moving. A faint flickering afterimage, offset
from the real body, is its displacement.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.systems.displacer import (
    BODY_HEIGHT,
    CLAW_TIMES,
    HALF_LENGTH,
    SHOULDER,
    STAB_TIMES,
    Displacer,
    along,
)

FUR = QColor(40, 42, 78)
FUR_SHEEN = QColor(84, 92, 160)
FUR_DARK = QColor(16, 16, 34)
FUR_FAR = QColor(22, 22, 46)
TENTACLE = QColor(48, 52, 100)
TENTACLE_FAR = QColor(28, 30, 62)
PAD = QColor(70, 78, 146)
BARB = QColor(214, 220, 244)
EYE = QColor(120, 255, 200)
EYE_GLOW = QColor(70, 255, 180, 80)
EYE_DEAD = QColor(40, 70, 64)
MOUTH = QColor(10, 8, 18)
FANG = QColor(240, 236, 226)
GHOST = QColor(110, 150, 255)
GHOST_ALPHA = (0.07, 0.2)
"""The afterimage's opacity flickers between these..."""
ILLUSION_ALPHA = (0.35, 0.55)
"""...its illusion's, sent out on its own..."""
FRENZY_ALPHA = (0.2, 0.5)
"""...and the afterimage's in a frenzy."""
RIPPLE_RADIUS = 26.0

TAIL_SEGMENTS = 14
TAIL_SEGMENT = 2.5
TENTACLE_SEGMENTS = 16
TENTACLE_SEGMENT = 2.6
LEGS = ("front", "mid", "rear")
WAVE_GAIT = {"rear": 0.0, "mid": 1.0 / 3.0, "front": 2.0 / 3.0}
"""Each side steps rear to front; the far side half a cycle behind."""
BOUND_GAIT = {"rear": 0.0, "mid": 0.22, "front": 0.5}
"""Loping, each pair lands almost together: hind, middle, then fore."""
BOUND_SPLIT = 0.07


def _qt(point: Vec2) -> QPointF:
    return QPointF(point.x, point.y)


def _pen(color: QColor, width: float) -> QPen:
    return QPen(
        color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
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


def _ik(root: Vec2, target: Vec2, upper: float, lower: float, bend: float) -> tuple[Vec2, Vec2]:
    """The joint of a two-bone limb from `root` reaching for `target` (pulled in if out
    of reach), bowing to the +angle side for `bend` +1: the end too."""
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


@dataclass
class Leg:
    near: bool
    points: list[Vec2]
    widths: list[float]
    """At each point."""


@dataclass
class Pose:
    body: list[Vec2]
    back: list[Vec2]
    neck: list[Vec2]
    head: Vec2
    tilt: float
    legs: list[Leg] = field(default_factory=list)
    tail: list[Vec2] = field(default_factory=list)
    tentacles: list[tuple[bool, list[Vec2], float]] = field(default_factory=list)


def _foot(phase: float, duty: float, stride: float, lift: float) -> Vec2:
    """Where a foot is through its stride, relative to under its hip: planted and
    sliding back for `duty` of the cycle, then lifted and swung forward."""
    p = phase % 1.0
    if p < duty:
        return Vec2(stride * (0.5 - p / duty), 0.0)
    q = (p - duty) / (1.0 - duty)
    return Vec2(stride * (smoothstep(q) - 0.5), -math.sin(math.pi * q) * lift)


def pose(beast: Displacer) -> Pose:
    t = beast.time
    dead = beast.dead
    crouch = beast.crouch
    landing = beast.landing * beast.impact
    stalk = beast.low
    lope = beast.lope
    slump = beast.slump
    swipe = _swipe(beast)
    claw = beast.attack_weight if beast.attack == "claw" else 0.0
    flying = beast.airborne and not dead
    falling_dead = beast.airborne and dead
    flight = beast.flight
    amp = 0.0 if beast.airborne else clamp(beast.speed / 25.0, 0.0, 1.0)
    phase = beast.phase
    H = BODY_HEIGHT

    duty = 0.68 + (0.42 - 0.68) * lope
    cycle = beast.cycle()
    stride = duty * cycle * amp
    lift = (2.4 + 1.6 * lope) * amp

    flex = math.sin(math.tau * (phase - 0.1)) * 2.4 * lope
    bob = (
        0.35 * math.sin(2 * math.tau * phase) * (1 - lope) + 1.1 * math.sin(math.tau * phase) * lope
    ) * amp
    stretch = 2.5 * math.sin(math.pi * flight) if flying else 0.0
    drop = 0.8 + 3.2 * stalk + 3.5 * landing + 6.5 * slump
    wiggle = 0.7 * math.sin(t * 24.0) * crouch * crouch
    sh = Vec2(
        HALF_LENGTH - flex * 0.5 + stretch + 5.0 * claw,
        -1.0 + drop + 1.0 * crouch + bob - 3.0 * claw,
    )
    hp = Vec2(-HALF_LENGTH + flex * 0.5 - stretch, -1.5 + drop + 3.2 * crouch + wiggle + bob * 0.6)
    mid = sh.lerp(hp, 0.5) + Vec2(0.0, 0.4)
    arch = 1.6 * max(0.0, math.sin(math.tau * (phase - 0.1))) * lope + 1.2 * crouch

    def offset_of(leg: str, near: bool) -> float:
        wave = WAVE_GAIT[leg] + (0.0 if near else 0.5)
        bound = BOUND_GAIT[leg] + (0.0 if near else BOUND_SPLIT)
        return wave + (bound - wave) * lope

    roots = {"front": sh + Vec2(0.0, 1.0), "mid": mid + Vec2(0.5, 1.8), "rear": hp + Vec2(1.0, 0.6)}
    rests = {"front": sh.x + 1.0, "mid": mid.x + 0.5, "rear": hp.x - 1.0}

    def foot_target(leg: str, near: bool) -> Vec2:
        side = 0.0 if near else -0.6
        if dead:
            spread = {"front": 11.0, "mid": 3.0, "rear": -11.0}[leg]
            lying = Vec2(rests[leg] + spread + (0.0 if near else 1.5), H - 0.8 + side)
            dangle = roots[leg] + Vec2(spread * 0.3, 11.0)
            return dangle.lerp(lying, slump) if not falling_dead else dangle
        if flying:
            f = smoothstep(flight)
            if leg == "front":
                reach = Vec2(sh.x + 4.0, sh.y + 9.0).lerp(
                    Vec2(sh.x + 12.0, sh.y + 4.0), smoothstep(flight * 2.5)
                )
                return reach.lerp(
                    Vec2(sh.x + 9.0, sh.y + 10.5), smoothstep((flight - 0.6) / 0.4)
                ) + Vec2(0.0 if near else -1.2, side)
            if leg == "mid":
                return Vec2(mid.x + 9.0 * (f - 0.5), mid.y + 10.0 + side)
            back = Vec2(hp.x - 11.0, hp.y + 6.0)
            tuck = Vec2(hp.x - 1.0, hp.y + 9.5)
            return back.lerp(tuck, smoothstep((flight - 0.45) / 0.55)) + Vec2(
                0.0 if near else -1.5, side
            )
        step = _foot(phase + offset_of(leg, near), duty, stride, lift)
        walking = Vec2(rests[leg] + step.x, H + step.y)
        gather = {"front": 3.0, "mid": 0.5, "rear": 3.5}[leg]
        crouched = Vec2(rests[leg] + gather, H)
        braced = Vec2(rests[leg] + {"front": 4.0, "mid": 0.0, "rear": -2.5}[leg], H)
        foot = walking.lerp(crouched, crouch).lerp(braced, clamp(landing, 0.0, 1.0))
        if leg == "front" and near:
            foot = foot.lerp(Vec2(sh.x + 13.0, sh.y + 1.0), swipe)
            if claw > 0.0:
                foot = foot.lerp(beast.paw_at(beast.attack_time), claw)
        return foot

    legs: list[Leg] = []
    for near in (False, True):
        for leg in LEGS:
            root = roots[leg]
            paw = foot_target(leg, near)
            if leg == "rear":
                hock = paw + Vec2(-3.2, -4.6)
                knee, hock = _ik(root, hock, 8.0, 7.5, -1.0)
                top = hp + Vec2(0.5, -4.0)
                paw = hock + (paw - hock).normalized() * min(5.6, (paw - hock).length())
                points = [top, root, knee, hock, paw]
                widths = [5.6, 4.6, 3.0, 2.0, 1.8]
            else:
                wrist = paw + Vec2(-0.6, -2.4)
                upper, lower = (8.0, 7.5) if leg == "front" else (7.5, 7.0)
                elbow, wrist = _ik(root, wrist, upper, lower, 1.0)
                top = root + Vec2(-2.5, -4.5) if leg == "front" else root + Vec2(0.0, -3.0)
                paw = wrist + (paw - wrist).normalized() * min(2.6, (paw - wrist).length())
                points = [top, root, elbow, wrist, paw]
                widths = [4.8 if leg == "front" else 3.6, 3.8, 2.6, 1.9, 1.8]
            legs.append(Leg(near, points, widths))

    roll_near = 1.5 * amp * (0.5 - 0.5 * math.cos(math.tau * (phase + offset_of("front", True))))
    hip_roll = 0.8 * amp * (0.5 - 0.5 * math.cos(math.tau * (phase + offset_of("rear", True))))
    body = [
        hp + Vec2(-6.0, -1.0),
        hp + Vec2(-4.0, -5.2),
        hp + Vec2(1.0, -7.0 - hip_roll),
        mid + Vec2(-1.0, -6.2 + 0.6 * stalk - arch),
        sh + Vec2(-4.0, -8.4 - roll_near - 1.6 * stalk),
        sh + Vec2(1.5, -7.6 - 0.4 * stalk),
        sh + Vec2(5.5, -5.2),
        sh + Vec2(7.0, 0.6),
        sh + Vec2(2.0, 5.2),
        mid + Vec2(-2.0, 2.8 - 0.8 * crouch),
        hp + Vec2(3.0, 3.0),
        hp + Vec2(-2.5, 2.8),
        hp + Vec2(-6.0, 1.0),
    ]
    back = [body[2], body[3], body[4], body[5]]

    head = Vec2(
        sh.x + 12.5 + stretch * 0.6 + 2.5 * swipe,
        sh.y - bob - 3.4 + 2.0 * stalk + 1.4 * crouch + 1.5 * swipe,
    )
    tilt = 0.12 * stalk + 0.1 * crouch - (0.12 if flying else 0.0)
    if dead:
        head = head.lerp(Vec2(sh.x + 10.0, H - 3.4), slump if not falling_dead else 0.0)
        tilt += 0.35 * slump
    neck = [
        sh + Vec2(1.0, -7.2),
        head + Vec2(-3.0, -2.4).rotated(tilt),
        head + Vec2(-2.4, 2.4).rotated(tilt),
        sh + Vec2(6.5, 1.5),
        sh + Vec2(2.0, -1.0),
    ]

    tail = _tail(beast, hp + Vec2(-5.0, -3.0), flying, amp)
    tentacles = [
        _tentacle(beast, sh + Vec2(-2.5, -8.0), False, flying),
        _tentacle(beast, sh + Vec2(-4.0, -7.6), True, flying),
    ]
    return Pose(body, back, neck, head, tilt, legs, tail, tentacles)


def _swipe(beast: Displacer) -> float:
    """0 to 1 and back over a swipe at its quarry."""
    strike = beast.strike
    return math.sin(math.pi * (1.0 - strike) ** 0.7) if strike > 0.0 else 0.0


def _tail(beast: Displacer, base: Vec2, flying: bool, amp: float) -> list[Vec2]:
    t = beast.time
    stalk, lope, crouch, slump = beast.low, beast.lope, beast.crouch, beast.slump
    start = math.pi - 0.75
    curl = 0.11
    start += 0.3 * stalk
    curl -= 0.07 * stalk
    start = start + (math.pi - 0.25 - start) * lope
    curl = curl + (0.035 - curl) * lope
    if flying:
        start, curl = math.pi - 0.05, 0.02
    if beast.dead:
        start, curl = start + (math.pi - 0.95 - start) * slump, curl
    points = [base]
    heading = 0.0
    for i in range(TAIL_SEGMENTS):
        u = i / (TAIL_SEGMENTS - 1)
        sway = 0.14 * math.sin(t * 2.1 - i * 0.45) * (0.3 + u)
        twitch = 0.45 * math.sin(t * 9.0) * stalk * max(0.0, u - 0.6) * 2.5
        lash = 0.55 * crouch * math.sin(t * 15.0 - i * 0.55) * (0.2 + u)
        counter = 0.25 * math.sin(math.pi * beast.flight - i * 0.3) * u if flying else 0.0
        live = 0.0 if beast.dead else 1.0
        heading = start + curl * i + (sway + twitch + lash + counter) * live
        point = points[-1] + Vec2.from_angle(heading, TAIL_SEGMENT)
        if not beast.airborne:
            point = Vec2(point.x, min(point.y, BODY_HEIGHT - 0.6))
        points.append(point)
    return points


def _tentacle(
    beast: Displacer, root: Vec2, near: bool, flying: bool
) -> tuple[bool, list[Vec2], float]:
    t = beast.time
    seed = 0.0 if near else 2.1
    crouch, lope, slump = beast.crouch, beast.lope, beast.slump
    coil = 0.5 * math.sin(0.7 * t + seed) + 0.35 * math.sin(1.9 * t + 2.0 * seed)
    base = -math.pi / 2 - 0.75 if near else -math.pi + 0.2
    """Up and back from the shoulder (the far one low over the back)..."""
    bend = (2.3 if near else 1.5) + 0.5 * coil
    """...then arching forward (the near one over the head), coiling and uncoiling."""
    wave_size = 1.0
    base += (-math.pi / 2 - 0.35 - base) * crouch
    bend += (1.6 - bend) * crouch
    wave_size -= 0.6 * crouch
    base -= 0.25 * lope
    bend -= 0.6 * lope
    if flying:
        base, bend, wave_size = -math.pi + 0.45, 0.3, 0.5
    fury = beast.fury
    # In a frenzy both flare up and out, straighter, writhing fast.
    base += ((-math.pi / 2 + 0.1 if near else -math.pi / 2 - 0.9) - base) * fury * 0.85
    bend += (0.6 - bend) * fury * 0.85
    wave_size += 0.5 * fury
    swipe = _swipe(beast)
    base += ((-0.45 if near else -0.8) - base) * swipe
    bend += (0.5 - bend) * swipe
    if beast.dead:
        limp_base = -0.5 if near else -math.pi + 0.5
        limp_bend = 1.2 if near else -1.2
        base = base + (limp_base - base) * slump
        bend = bend + (limp_bend - bend) * slump
        wave_size *= 1.0 - slump
    points = [root]
    for i in range(TENTACLE_SEGMENTS):
        u = i / (TENTACLE_SEGMENTS - 1)
        wave = 0.3 * math.sin(2.3 * t + seed - 0.55 * i) + 0.16 * math.sin(
            3.9 * t + 1.7 * seed - 0.95 * i
        )
        wave += 0.22 * fury * math.sin(14.0 * t + 3.0 * seed - 0.8 * i)
        angle = base + bend * u**1.4 + wave * wave_size * (0.25 + u)
        point = points[-1] + Vec2.from_angle(angle, TENTACLE_SEGMENT)
        if not beast.airborne:
            point = Vec2(point.x, min(point.y, BODY_HEIGHT - 0.8))
        points.append(point)
    twist = 0.55 + 0.45 * abs(math.sin(1.3 * t + seed))
    return near, points, twist


# ----- painting ------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    fur: QColor
    sheen: QColor
    dark: QColor
    far: QColor
    tentacle: QColor
    tentacle_far: QColor
    pad: QColor
    barb: QColor
    eye: QColor
    glow: QColor | None


LIVE = Palette(FUR, FUR_SHEEN, FUR_DARK, FUR_FAR, TENTACLE, TENTACLE_FAR, PAD, BARB, EYE, EYE_GLOW)
DEAD = Palette(FUR, FUR_SHEEN, FUR_DARK, FUR_FAR, TENTACLE, TENTACLE_FAR, PAD, BARB, EYE_DEAD, None)
GHOSTLY = Palette(
    GHOST,
    GHOST.lighter(130),
    GHOST.darker(160),
    GHOST.darker(130),
    GHOST,
    GHOST.darker(130),
    GHOST.lighter(120),
    GHOST.lighter(150),
    EYE,
    None,
)


@dataclass
class Placed:
    """The pose turned about in depth and laid along its center line, in the world."""

    body: QPainterPath
    back: list[Vec2]
    sheen: list[Vec2]
    """Along the inside of its back, for the light on its fur..."""
    belly: list[Vec2]
    """...and along the inside of its belly, for the shadow."""
    head: Callable[[float, float, float], Vec2]
    """Head-local (x, y, z) to the world."""
    head_yaw: float
    parts: list[tuple[float, str, object]]
    """(depth, kind, data) to paint back to front."""


def _mix(far: QColor, near: QColor, t: float) -> QColor:
    t = clamp(t, 0.0, 1.0)
    return QColor.fromRgbF(
        far.redF() + (near.redF() - far.redF()) * t,
        far.greenF() + (near.greenF() - far.greenF()) * t,
        far.blueF() + (near.blueF() - far.blueF()) * t,
        far.alphaF() + (near.alphaF() - far.alphaF()) * t,
    )


def _swept(outline: list[Vec2], place, width: float, turning: bool) -> QPainterPath:
    """The smooth outline placed at depths across its `width` and united, so it's
    as thick as it is wide when seen face on."""
    path = _smooth([place(p, 0.0) for p in outline])
    if turning:
        for z in (-width, -width / 2, width / 2, width):
            path = path.united(_smooth([place(p, z) for p in outline]))
    return path


def place(beast: Displacer, shape: Pose) -> Placed:
    spine = beast.spine()
    slide = beast.slide
    yaw_at = beast.yaw_at
    turning = abs(math.sin(beast.head_yaw)) > 0.02 or abs(math.sin(beast.tail_yaw)) > 0.02

    def bend(local: Vec2, z: float = 0.0, yaw: float | None = None) -> Vec2:
        yaw = yaw_at(local.x) if yaw is None else yaw
        return spine.at(local.x * math.cos(yaw) - z * math.sin(yaw), local.y) + slide

    def rigid(anchor: Vec2, anchor_z: float, yaw: float):
        cos, sin = math.cos(yaw), math.sin(yaw)
        x0 = anchor.x * cos - anchor_z * sin
        origin, up = spine.frame(x0)
        forward = along(up)

        def at(local: Vec2, z: float) -> Vec2:
            return origin + forward * (local.x * cos - z * sin - x0) - up * local.y + slide

        return at

    parts: list[tuple[float, str, object]] = []
    for leg in shape.legs:
        z = 3.0 if leg.near else -3.0
        root = leg.points[1]
        yaw = yaw_at(root.x)
        points = [bend(p, z, yaw) for p in leg.points]
        depth = root.x * math.sin(yaw) + z * math.cos(yaw)
        near = 0.5 + 0.5 * (z / 3.0) * math.cos(yaw)
        parts.append((depth, "leg", (Leg(leg.near, points, leg.widths), near)))
    for near_side, points, twist in shape.tentacles:
        z0 = 3.5 if near_side else -3.5
        side = 1.0 if near_side else -1.0
        root = points[0]
        yaw = yaw_at(root.x)
        at = rigid(root, z0, yaw)
        count = len(points) - 1
        placed = [at(p, z0 + side * 5.0 * i / count) for i, p in enumerate(points)]
        if beast.attack == "stab":
            placed = _speared(beast, placed, near_side)
        depth = root.x * math.sin(yaw) + z0 * math.cos(yaw)
        near = 0.5 + 0.5 * side * math.cos(yaw)
        parts.append((depth, "tentacle", (placed, twist, near)))
    count = len(shape.tail) - 1
    tail = [bend(p, -4.0 * i / count) for i, p in enumerate(shape.tail)]
    parts.append((shape.tail[0].x * math.sin(yaw_at(shape.tail[0].x)) - 0.5, "tail", tail))
    parts.append((0.0, "body", None))
    head_yaw = yaw_at(shape.head.x)
    head_at = rigid(shape.head, 0.0, head_yaw)

    def head(x: float, y: float, z: float = 0.0) -> Vec2:
        return head_at(shape.head + Vec2(x, y).rotated(shape.tilt), z)

    parts.append((shape.head.x * math.sin(head_yaw) + 0.6, "head", None))
    parts.sort(key=lambda part: part[0])
    body = _swept(shape.body, bend, 4.5, turning).united(_swept(shape.neck, bend, 3.0, turning))
    back = [bend(p + Vec2(0.0, 0.9)) for p in shape.back]
    sheen = [bend(p + Vec2(0.0, 2.2)) for p in shape.body[1:6]]
    belly = [bend(p + Vec2(0.0, -1.6)) for p in shape.body[8:12]]
    return Placed(body, back, sheen, belly, head, head_yaw, parts)


def draw_displacer(painter: QPainter, beast: Displacer, outline: QColor | None = None) -> None:
    """The beast, with its displacement afterimage behind it while it lives (or, sent
    out on its own, its illusion)."""
    if beast.ghost is not None:
        _draw_illusion(painter, beast.ghost)
    placed = place(beast, pose(beast))
    opacity = painter.opacity()
    away = beast.ghost.presence if beast.ghost is not None else 0.0
    if not beast.dead and away < 1.0:
        t, fury = beast.time, beast.fury
        shift = Vec2(
            6.0 * math.sin(0.45 * t) + 2.5 * math.sin(1.7 * t + 1.0), -1.5 + 1.5 * math.sin(1.3 * t)
        )
        shift += Vec2(7.0 * math.sin(9.0 * t), 2.5 * math.sin(13.0 * t)) * fury
        _, up = beast.spine().frame(0.0)
        offset = along(up) * (shift.x * beast.turn) - up * shift.y
        low, high = GHOST_ALPHA
        low, high = low + (FRENZY_ALPHA[0] - low) * fury, high + (FRENZY_ALPHA[1] - high) * fury
        flicker = _flicker(t) + (_flicker(2.7 * t) - _flicker(t)) * fury
        painter.save()
        painter.translate(_qt(offset))
        painter.setOpacity(opacity * (low + (high - low) * flicker) * (1.0 - away))
        _paint(painter, placed, GHOSTLY, None)
        painter.restore()
    _paint(painter, placed, DEAD if beast.dead else LIVE, outline)
    if beast.attack is not None and not beast.dead:
        _paint_streak(painter, beast)


def _speared(beast: Displacer, placed: list[Vec2], near: bool) -> list[Vec2]:
    """A tentacle straightened out along the stab from its root (the far one a moment
    behind and a little shorter and to the side)."""
    way, length = beast.stab_at(max(0.0, beast.attack_time - (0.0 if near else 0.04)))
    if not near:
        way, length = way.rotated(0.12), length * 0.88
    across = Vec2(-way.y, way.x)
    root = placed[0]
    count = len(placed) - 1
    straight = [
        root + way * (length * i / count) + across * (1.5 * math.sin(math.pi * i / count))
        for i in range(count + 1)
    ]
    weight = beast.attack_weight
    return [p.lerp(q, weight) for p, q in zip(placed, straight, strict=True)]


def _paint_streak(painter: QPainter, beast: Displacer) -> None:
    """The blur behind a spearing tentacle tip or raking claws, over the last moment."""
    t = beast.attack_time
    if beast.attack == "stab":
        wind, strike, _ = STAB_TIMES
        root = beast.to_world(SHOULDER)
        across = Vec2(-beast.stab_way.y, beast.stab_way.x)
        tips = [
            root + way * length
            for way, length in (beast.stab_at(u) for u in _trail_times(t, wind, strike))
        ]
        lines = [[tip + across * offset for tip in tips] for offset in (-2.0, 2.0)]
        color, width = BARB, 1.6
    else:
        wind, strike, _ = CLAW_TIMES
        times = _trail_times(t, wind, strike)
        lines = [
            [beast.to_world(beast.paw_at(u) + Vec2(0.0, offset)) for u in times]
            for offset in (-2.5, 0.0, 2.5)
        ]
        color, width = FANG, 1.2
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for line in lines:
        count = len(line) - 1
        for i in range(count):
            fade = 1.0 - i / count
            painter.setPen(_pen(_alpha(color, 200 * fade), width * (0.4 + 0.6 * fade)))
            painter.drawLine(_qt(line[i]), _qt(line[i + 1]))
    painter.restore()


def _trail_times(t: float, wind: float, strike: float) -> list[float]:
    """Moments back from `t` (newest first) over the strike and a little after it."""
    end = wind + strike + 0.1
    if not wind < t <= end:
        return []
    newest = min(t, wind + strike)
    return [u for u in (newest - k * strike / 16 for k in range(17)) if u >= wind]


def _flicker(t: float) -> float:
    return 0.5 + 0.5 * math.sin(17.0 * t) * math.sin(5.3 * t + 1.0)


def _draw_illusion(painter: QPainter, ghost: Displacer) -> None:
    """The illusion: a flickering see-through second beast that shimmers apart when an
    attack passes through it."""
    presence = ghost.presence
    if presence <= 0.0:
        return
    placed = place(ghost, pose(ghost))
    opacity = painter.opacity()
    low, high = ILLUSION_ALPHA
    alpha = opacity * presence * (low + (high - low) * _flicker(ghost.time))
    shimmer = ghost.shimmer
    _, up = ghost.spine().frame(0.0)
    way = along(up)
    painter.save()
    if shimmer > 0.0:
        split = 4.0 * shimmer * (0.6 + 0.4 * math.sin(40.0 * ghost.time))
        for side in (-1.0, 1.0):
            painter.save()
            painter.translate(_qt(way * (side * split)))
            painter.setOpacity(alpha * 0.55)
            _paint(painter, placed, GHOSTLY, None)
            painter.restore()
        painter.setOpacity(alpha * (1.0 - 0.6 * shimmer))
    else:
        painter.setOpacity(alpha)
    _paint(painter, placed, GHOSTLY, None)
    if shimmer > 0.0:
        center = ghost.look_center + ghost.shimmer_at
        radius = RIPPLE_RADIUS * (1.0 - shimmer) + 3.0
        painter.setOpacity(opacity * presence * shimmer)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for ring in (1.0, 0.6):
            painter.setPen(_pen(_alpha(GHOST.lighter(150), 220), 1.4))
            painter.drawEllipse(_qt(center), radius * ring, radius * ring * 0.7)
    painter.restore()


def _paint(painter: QPainter, shape: Placed, palette: Palette, outline: QColor | None) -> None:
    if outline is not None:
        _paint_outline(painter, shape, outline)
    for _, kind, data in shape.parts:
        if kind == "leg":
            leg, near = data
            _paint_leg(painter, leg, _mix(palette.far, palette.fur, near))
        elif kind == "tentacle":
            points, twist, near = data
            _paint_tentacle(
                painter,
                points,
                twist,
                _mix(palette.tentacle_far, palette.tentacle, near),
                _mix(palette.pad.darker(130), palette.pad, near),
                _mix(palette.barb.darker(140), palette.barb, near),
            )
        elif kind == "tail":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(palette.fur)
            painter.drawPath(_tapered(data, _tail_widths(len(data))))
        elif kind == "body":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(palette.fur)
            painter.drawPath(shape.body)
            painter.save()
            painter.setClipPath(shape.body, Qt.ClipOperation.IntersectClip)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(_pen(_alpha(palette.sheen, 110), 5.0))
            painter.drawPath(_smooth(shape.sheen, closed=False))
            painter.setPen(_pen(_alpha(palette.dark, 170), 6.0))
            painter.drawPath(_smooth(shape.belly, closed=False))
            painter.restore()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(_pen(_alpha(palette.sheen, 200), 0.9))
            painter.drawPath(_smooth(shape.back, closed=False))
        else:
            _paint_head(painter, shape, palette)


def _paint_outline(painter: QPainter, shape: Placed, outline: QColor) -> None:
    grow = 2.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(outline)
    for _, kind, data in shape.parts:
        if kind == "tentacle":
            points, twist, _ = data
            painter.drawPath(_tapered(points, _tentacle_widths(len(points)), grow))
            painter.setPen(_pen(outline, grow + 0.6))
            painter.drawPolygon(_pad_outline(_pad_frame(points, twist)))
            painter.setPen(Qt.PenStyle.NoPen)
        elif kind == "leg":
            leg, _ = data
            painter.drawPath(_tapered(leg.points, leg.widths, grow))
        elif kind == "tail":
            painter.drawPath(_tapered(data, _tail_widths(len(data)), grow))
    painter.setPen(_pen(outline, grow))
    painter.drawPath(shape.body)
    painter.drawPath(_head_path(shape))


def _tapered(points: list[Vec2], widths: list[float], grow: float = 0.0) -> QPainterPath:
    """A stroke through `points`, `widths` wide at each, with round joints and ends, as
    one filled shape (so it fades out evenly)."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    left: list[QPointF] = []
    right: list[QPointF] = []
    last = len(points) - 1
    for i, point in enumerate(points):
        way = points[min(i + 1, last)] - points[max(i - 1, 0)]
        across = Vec2(-way.y, way.x).normalized() * ((widths[i] + grow) / 2)
        left.append(_qt(point + across))
        right.append(_qt(point - across))
    outline = [*left, *reversed(right)]
    if _area(outline) < 0.0:
        outline.reverse()
    path.addPolygon(QPolygonF(outline))
    for point, width in zip(points, widths, strict=True):
        radius = (width + grow) / 2
        path.addEllipse(_qt(point), radius, radius)
    return path


def _area(points: list[QPointF]) -> float:
    """Signed area, positive when wound the way Qt winds an ellipse (so with a winding
    fill they add up instead of cutting holes in each other)."""
    total = 0.0
    for a, b in zip(points, points[1:] + points[:1], strict=True):
        total += a.x() * b.y() - b.x() * a.y()
    return total


def _paint_leg(painter: QPainter, leg: Leg, color: QColor) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    path = _tapered(leg.points, leg.widths)
    path.addEllipse(_qt(leg.points[-1] + Vec2(0.5, -0.6)), 1.7, 1.0)
    painter.drawPath(path)


def _tail_widths(count: int) -> list[float]:
    return [3.2 * (1.0 - 0.65 * i / (count - 1)) for i in range(count)]


def _tentacle_widths(count: int) -> list[float]:
    return [2.3 - 1.3 * i / (count - 1) for i in range(count)]


PAD_EDGE = ((0.0, 0.0), (1.2, 1.0), (2.6, 1.9), (4.4, 2.0), (6.0, 1.2), (7.2, 0.0))
PAD_BARBS = ((2.6, 1.9), (4.4, 2.0), (2.6, -1.9), (4.4, -2.0))


def _pad_frame(points: list[Vec2], twist: float):
    """(along, across) on the flattened pad at the tip of a tentacle, to the world; the
    pad narrows as it twists edge-on."""
    tip, before = points[-1], points[-2]
    way = (tip - before).normalized()
    side = Vec2(-way.y, way.x) * twist

    def at(u: float, v: float) -> Vec2:
        return tip + way * (u - 0.6) + side * v

    return at


def _pad_outline(at) -> list[QPointF]:
    edge = [at(u, v) for u, v in PAD_EDGE] + [at(u, -v) for u, v in reversed(PAD_EDGE[1:-1])]
    return [_qt(p) for p in edge]


def _paint_tentacle(
    painter: QPainter, points: list[Vec2], twist: float, color: QColor, pad: QColor, barb: QColor
) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(_tapered(points, _tentacle_widths(len(points))))
    at = _pad_frame(points, twist)
    painter.setBrush(barb)
    for u, v in PAD_BARBS:
        out = 1.0 if v > 0 else -1.0
        painter.drawPolygon(
            [_qt(at(u - 0.7, v * 0.8)), _qt(at(u - 0.6, v + out * 1.5)), _qt(at(u + 0.6, v * 0.8))]
        )
    painter.drawPolygon([_qt(at(6.4, 0.6)), _qt(at(8.6, 0.0)), _qt(at(6.4, -0.6))])
    painter.setBrush(pad)
    painter.drawPolygon(_pad_outline(at))
    painter.setPen(_pen(_alpha(barb, 150), 0.45))
    painter.drawLine(_qt(at(0.8, 0.0)), _qt(at(6.2, 0.0)))


HEAD_SHAPE = [
    (-3.4, -1.0),
    (-2.2, -3.0),
    (0.6, -3.4),
    (3.0, -2.5),
    (5.4, -1.3),
    (6.5, -0.2),
    (6.3, 1.0),
    (4.4, 1.9),
    (1.0, 2.6),
    (-2.2, 2.4),
]


def _head_path(shape: Placed) -> QPainterPath:
    turning = abs(math.sin(shape.head_yaw)) > 0.02
    path = _smooth([shape.head(x, y) for x, y in HEAD_SHAPE])
    if turning:
        for z in (-2.6, -1.3, 1.3, 2.6):
            path = path.united(_smooth([shape.head(x, y, z) for x, y in HEAD_SHAPE]))
    return path


BACK_EAR = ((0.6, -3.0), (-2.0, -6.0), (-1.0, -2.6))
FRONT_EAR = ((-0.6, -2.9), (-4.0, -5.5), (-2.6, -2.1))
FRONT_EAR_INSIDE = ((-1.0, -2.9), (-3.4, -4.8), (-2.4, -2.5))


def _paint_head(painter: QPainter, shape: Placed, palette: Palette) -> None:
    head = shape.head
    cos, sin = math.cos(shape.head_yaw), math.sin(shape.head_yaw)

    def at(x: float, y: float, z: float = 0.0) -> QPointF:
        return _qt(head(x, y, z))

    ears = sorted((-1.5, 1.5), key=lambda z: z * cos)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(palette.far)
    painter.drawPolygon([at(x, y, ears[0]) for x, y in BACK_EAR])
    painter.setBrush(palette.fur)
    painter.drawPath(_head_path(shape))
    painter.setPen(_pen(_alpha(palette.sheen, 190), 0.8))
    painter.drawPolyline([at(-2.0, -2.7), at(0.6, -3.1), at(3.0, -2.2)])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(palette.fur)
    painter.drawPolygon([at(x, y, ears[1]) for x, y in FRONT_EAR])
    painter.setBrush(palette.dark)
    painter.drawPolygon([at(x, y, ears[1]) for x, y in FRONT_EAR_INSIDE])
    painter.setBrush(MOUTH)
    painter.drawEllipse(at(6.3, -0.3), 0.7, 0.55)
    painter.setPen(_pen(MOUTH, 0.5))
    painter.drawLine(at(6.0, 1.0), at(2.4, 1.4))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FANG)
    fang = 0.8 if cos >= 0.0 else -0.8
    painter.drawPolygon([at(4.6, 1.15, fang), at(5.4, 1.05, fang), at(5.0, 2.1, fang)])
    for z in (-1.4, 1.4):
        showing = clamp((2.4 * sin + z * cos + 0.3) / 0.8, 0.0, 1.0)
        if showing <= 0.0:
            continue
        eye = head(2.4, -1.3, z)
        if palette.glow is not None:
            painter.setBrush(_alpha(palette.glow, palette.glow.alpha() * showing))
            painter.drawEllipse(_qt(eye), 2.6, 2.0)
        painter.setBrush(_alpha(palette.eye, 255 * showing))
        painter.drawEllipse(_qt(eye), 1.3, 0.75)
        painter.setPen(_pen(_alpha(MOUTH, 255 * showing), 0.3))
        painter.drawLine(_qt(head(2.4, -1.85, z)), _qt(head(2.4, -0.75, z)))
        painter.setPen(Qt.PenStyle.NoPen)
