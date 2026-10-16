"""QPainter drawing of the lich.

Flat fills with one shade and one outline, like the other monsters: a tall cone of
ragged black robe (a faint grey rim keeps it from vanishing on a dark desktop) with a
high pointed collar, a bone-white skull with dark sockets and green pinpoint eyes, a
gold crown, bony forearms and hands out of the sleeves, and bony toes under the hem.
The flame hand is held out before him, palm up, with a green flame flickering over it.

Everything is placed by `Lich.joints` and `Lich.project`, which turn him through a
three-quarter view toward the viewer, so a turn round is smooth: the arm and the eyes
swing round with him and nothing is mirrored at once. The robe's silhouette doesn't
depend on the turn at all; its hem trails his motion and sways.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.defenders.lich.actor import (
    DOOR_EMERGE,
    DOOR_FADE,
    DOOR_STEP_OUT,
    DOOR_SWAP,
    Bit,
    Door,
    Joints,
    Lich,
)
from dungeons_desktops.game.defenders.minotaur.render import Ink, _alpha, _pen, _qt, _smooth, _taper

ROBE = QColor(26, 24, 32)
ROBE_LIGHT = QColor(52, 50, 64)
ROBE_FOLD = QColor(10, 9, 13)
ROBE_RIM = QColor(112, 118, 128, 190)
BONE = QColor(234, 228, 206)
BONE_SHADE = QColor(178, 170, 146)
SOCKET = QColor(18, 14, 20)
EYE = QColor(150, 255, 130)
GOLD = QColor(240, 192, 62)
GOLD_SHADE = QColor(176, 124, 30)
GEM = QColor(70, 232, 112)
FLAME = QColor(70, 226, 96)
FLAME_CORE = QColor(212, 255, 196)
GLOW = QColor(90, 255, 140)
DEAD_EYE = QColor(40, 60, 40)
CRACKLE = QColor(214, 255, 236)

ROBE_WIDTHS = (
    (-35.5, 3.0),
    (-33.0, 6.0),
    (-26.0, 6.6),
    (-18.0, 7.2),
    (-10.0, 8.4),
    (-3.0, 9.8),
    (0.0, 10.8),
)
"""Half-width of the robe down his body (y from his feet)."""
HEM_POINTS = 9
DOOR_EDGE = QColor(130, 255, 160)
DOOR_VIOLET = QColor(176, 96, 255)
DOOR_VOID = QColor(34, 12, 56)
DOOR_WIDTH = 22.0
DOOR_HEIGHT = 54.0
MOTES = 14


def draw_lich(painter: QPainter, lich: Lich, outline: QColor | None = None) -> None:
    joints = lich.joints() if not lich.dead else None
    door = lich.door if not lich.dead else None
    painter.save()
    if door is not None:
        _doors(painter, door)
    visibility = lich.visibility
    if visibility > 0.01:
        opacity = painter.opacity()
        painter.setOpacity(opacity * visibility)
        if outline is not None:
            _paint(Ink(painter, outline, 1.4), lich, joints)
        _paint(Ink(painter), lich, joints)
        painter.setOpacity(opacity)
    if door is not None:
        _door_motes(painter, door)
    painter.restore()


def draw_liches(painter: QPainter, liches, outline: QColor | None = None) -> None:
    for lich in liches:
        draw_lich(painter, lich, outline)


# ----- dimension door ---------------------------------------------------------------


def _ease(t: float) -> float:
    return smoothstep(clamp(t, 0.0, 1.0))


def _doors(painter: QPainter, door: Door) -> None:
    """The door he goes into (traced, opened, closed behind him) and the one he comes
    out of (shimmering into view, opening, closing after him)."""
    t = door.time
    _door_frame(
        painter,
        door.origin,
        trace=_ease(t / 0.35),
        opening=_ease((t - 0.25) / 0.25) * (1.0 - _ease((t - 0.8) / 0.25)),
        alpha=1.0 - _ease((t - 1.0) / 0.3),
        t=t,
    )
    shimmer = _ease(t / 0.3) * (0.5 + 0.5 * _ease((t - 0.4) / 0.3))
    _door_frame(
        painter,
        door.target,
        trace=_ease((t - 0.15) / 0.4),
        opening=_ease((t - 0.55) / 0.25) * (1.0 - _ease((t - 1.0) / 0.25)),
        alpha=shimmer * (1.0 - _ease((t - 1.1) / 0.25)),
        t=t,
    )


def _door_outline(feet: Vec2) -> list[Vec2]:
    """Up the left jamb, round the arched top and down the right jamb."""
    half, top = DOOR_WIDTH / 2, feet.y - DOOR_HEIGHT
    arch = [
        Vec2(feet.x - half * math.cos(a), top + half - half * math.sin(a))
        for a in (i * math.pi / 8 for i in range(9))
    ]
    return [Vec2(feet.x - half, feet.y), *arch, Vec2(feet.x + half, feet.y)]


def _partial(points: list[Vec2], fraction: float) -> list[Vec2]:
    lengths = [a.distance_to(b) for a, b in zip(points, points[1:], strict=False)]
    left = sum(lengths) * fraction
    out = [points[0]]
    for (a, b), length in zip(zip(points, points[1:], strict=False), lengths, strict=False):
        if left >= length:
            out.append(b)
            left -= length
            continue
        if length > 0.0:
            out.append(a.lerp(b, left / length))
        break
    return out


def _door_frame(
    painter: QPainter, feet: Vec2, trace: float, opening: float, alpha: float, t: float
) -> None:
    if alpha <= 0.01 or trace <= 0.0:
        return
    outline = _door_outline(feet)
    shape = _polygon(outline)
    painter.setPen(Qt.PenStyle.NoPen)
    panel = _ease((trace - 0.6) / 0.4) * alpha
    if opening > 0.0:
        middle = feet + Vec2(0.0, -DOOR_HEIGHT / 2)
        glow = QRadialGradient(_qt(middle), DOOR_HEIGHT * 0.6)
        glow.setColorAt(0.0, _alpha(GLOW, 200 * opening * alpha))
        glow.setColorAt(0.6, _alpha(DOOR_VIOLET, 150 * opening * alpha))
        glow.setColorAt(1.0, _alpha(DOOR_VIOLET, 0))
        painter.setBrush(glow)
        painter.drawPath(shape)
    if panel > 0.0:
        # The panel swings open on its left hinge: its free edge sweeps in.
        left = feet.x - DOOR_WIDTH / 2
        width = DOOR_WIDTH * (1.0 - 0.85 * opening)
        painter.save()
        painter.setClipPath(shape)
        painter.setBrush(_alpha(DOOR_VOID, 220 * panel))
        painter.drawRect(QRectF(left, feet.y - DOOR_HEIGHT, width, DOOR_HEIGHT))
        painter.setBrush(_alpha(DOOR_EDGE, 200 * panel))
        painter.drawEllipse(_qt(Vec2(left + width - 3.0, feet.y - DOOR_HEIGHT * 0.45)), 1.0, 1.0)
        painter.restore()
    traced = _partial(outline, trace)
    path = QPainterPath(_qt(traced[0]))
    for p in traced[1:]:
        path.lineTo(_qt(p))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(_alpha(DOOR_VIOLET, 110 * alpha), 4.0))
    painter.drawPath(path)
    painter.setPen(_pen(_alpha(DOOR_EDGE, 255 * alpha), 1.3))
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_alpha(FLAME_CORE, 255 * alpha))
    painter.drawEllipse(_qt(traced[-1]), 1.4, 1.4)
    for k in range(3):
        spark = _partial(outline, ((t * 0.7 + k / 3.0) % 1.0) * trace)[-1]
        painter.drawEllipse(_qt(spark), 0.8, 0.8)


def _door_motes(painter: QPainter, door: Door) -> None:
    """His body streaming into the first door as green motes, and out of the second."""
    t = door.time
    going = (t - DOOR_FADE) / (DOOR_SWAP - DOOR_FADE)
    coming = (t - DOOR_EMERGE) / DOOR_STEP_OUT
    painter.setPen(Qt.PenStyle.NoPen)
    for k in range(MOTES):
        delay = 0.4 * k / MOTES
        body = Vec2(math.sin(k * 2.1) * 7.0, -4.0 - k * 40.0 / MOTES)
        swirl = Vec2(math.sin(k * 1.3 + t * 9.0) * 2.0, -DOOR_HEIGHT * 0.45)
        color = GLOW if k % 2 else DOOR_VIOLET
        if 0.0 < going < 1.4:
            s = _ease((going - delay) / 0.6)
            if 0.0 < s < 1.0:
                point = (door.origin + body).lerp(door.origin + swirl, s)
                painter.setBrush(_alpha(color, 230 * (1.0 - 0.7 * s)))
                painter.drawEllipse(_qt(point), 1.0, 1.0)
        if 0.0 < coming < 1.4:
            s = _ease((coming - delay) / 0.6)
            if 0.0 < s < 1.0:
                point = (door.target + swirl).lerp(door.target + body, s)
                painter.setBrush(_alpha(color, 230 * (1.0 - s)))
                painter.drawEllipse(_qt(point), 1.0, 1.0)


# ----- pieces ---------------------------------------------------------------------


def _rimmed(ink: Ink, path: QPainterPath, color: QColor, rim: QColor = ROBE_RIM) -> None:
    ink.shape(path, color)
    if ink.detail:
        painter = ink.painter
        painter.setPen(_pen(rim, 0.9))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


def _robe_outline(lich: Lich, root: Vec2, slump: float) -> list[Vec2]:
    t = lich.time
    lift = clamp(lich.lift.value, 0.0, 1.0)
    trail = clamp(-lich.drag.value * 0.07, -4.0, 4.0)
    squash = 1.0 - 0.8 * slump

    def center(y: float) -> float:
        return lich.project(0.0, 0.0, y * squash, root).x - root.x

    def bend(y: float) -> float:
        k = clamp((y + 30.0) / 27.0, 0.0, 1.0)
        return trail * k * k

    def width(y: float) -> float:
        for (y0, w0), (y1, w1) in zip(ROBE_WIDTHS, ROBE_WIDTHS[1:], strict=False):
            if y <= y1:
                k = clamp((y - y0) / (y1 - y0), 0.0, 1.0)
                return (w0 + (w1 - w0) * k) * (1.0 + 0.6 * slump * k)
        return ROBE_WIDTHS[-1][1] * (1.0 + 0.6 * slump)

    side_ys = [y for y, _ in ROBE_WIDTHS]
    front = [Vec2(center(y) + bend(y) + width(y), y * squash) for y in side_ys]
    back = [Vec2(center(y) + bend(y) - width(y), y * squash) for y in reversed(side_ys)]
    hem: list[Vec2] = []
    hem_y = 2.5 * lift
    left_x, right_x = back[0].x, front[-1].x
    gait = smoothstep(clamp(lich.gait.value, 0.0, 1.0))
    flutter = 0.6 + 1.2 * lift + 0.8 * gait
    ripple = 2.0 * math.pi * 2.0 * lich.phase
    for i in range(HEM_POINTS):
        k = i / (HEM_POINTS - 1)
        x = right_x + (left_x - right_x) * k
        jag = 0.0 if i % 2 == 0 else -2.6 * (1.0 - 0.6 * slump)
        wave = math.sin(ripple + i * 0.9) * gait
        sway = (math.sin(t * 2.4 + i * 1.7) * 0.6 + 0.5 * wave) * flutter
        rise = 0.6 * (0.5 + 0.5 * math.sin(t * 3.1 + i)) + 0.6 * gait * (0.5 + 0.5 * wave)
        y = hem_y + jag - rise * (1.0 if i % 2 else 0.5)
        hem.append(Vec2(x + sway + trail * 0.3, y))
    points = [root + p for p in front + hem + back]
    ground = lich.ground_below(lich.position - Vec2(0.0, 1.0))
    return [Vec2(p.x, min(p.y, ground)) for p in points]


def _collar(lich: Lich, root: Vec2) -> list[list[Vec2]]:
    c = lich.project(0.0, 0.0, -34.0, root)
    flaps = []
    for side in (-1.0, 1.0):
        flaps.append(
            [
                c + Vec2(side * 2.0, 1.5),
                c + Vec2(side * 7.2, 0.5),
                c + Vec2(side * 6.4, -11.0),
                c + Vec2(side * 3.0, -5.0),
            ]
        )
    return flaps


def _polygon(points: list[Vec2]) -> QPainterPath:
    path = QPainterPath(_qt(points[0]))
    for p in points[1:]:
        path.lineTo(_qt(p))
    path.closeSubpath()
    return path


def _oval(center: Vec2, rx: float, ry: float, angle: float) -> list[Vec2]:
    return [
        center + Vec2(rx * math.cos(a), ry * math.sin(a)).rotated(angle)
        for a in (i * math.pi / 4 for i in range(8))
    ]


def _cheeks(center: Vec2, half: float, angle: float) -> list[Vec2]:
    """Wide at the cheekbones, narrowing down to the upper teeth."""
    points = [
        (-half, -1.6),
        (half, -1.6),
        (half * 0.95, 0.4),
        (half * 0.6, 2.2),
        (-half * 0.6, 2.2),
        (-half * 0.95, 0.4),
    ]
    return [center + Vec2(x, y).rotated(angle) for x, y in points]


def _bone(ink: Ink, a: Vec2, b: Vec2, width: float, color: QColor = BONE) -> None:
    ink.limb([a, b], [width, width * 0.85], color)


def _sleeve(ink: Ink, shoulder: Vec2, elbow: Vec2, cuff: Vec2, droop: float) -> None:
    """A wide bell sleeve: down the upper arm and along the forearm, its cuff hanging
    open below the wrist."""
    grow = ink.grow
    arm = _taper([shoulder, elbow, cuff], [6.4 + grow, 5.0 + grow, 5.6 + grow])
    side = (cuff - elbow).normalized().rotated(math.pi / 2)
    if side.y < 0.0:
        side = -side
    back = (elbow - cuff).normalized()
    drape = _polygon(
        [
            cuff - side * (2.8 + grow),
            cuff + side * (2.6 + grow) + back * 0.5,
            cuff + back * (3.0 + grow) + Vec2(0.0, droop + grow),
            elbow + side * (2.0 + grow),
        ]
    )
    _rimmed(ink, arm.united(drape).simplified(), ROBE)


def _hand(ink: Ink, wrist: Vec2, forward: float, up: bool) -> None:
    """A bony hand: palm up (fingers forward and curling up) or hanging."""
    palm = wrist + Vec2(forward * 1.4, -0.4 if up else 1.0)
    ink.circle(palm, 1.7, BONE)
    for i, lift in enumerate((-0.6, 0.6, 1.6)):
        if up:
            tip = palm + Vec2(forward * (2.8 - 0.3 * i), -1.2 - lift)
        else:
            tip = palm + Vec2(forward * (1.2 + 0.4 * i), 2.6 - 0.2 * i)
        ink.limb([palm, tip], [1.1, 0.8], BONE)


def _arm(ink: Ink, shoulder: Vec2, elbow: Vec2, hand: Vec2, forward: float, up: bool) -> None:
    cuff = elbow.lerp(hand, 0.45 if up else 0.7)
    _bone(ink, cuff, hand, 1.5)
    _hand(ink, hand, forward, up)
    _sleeve(ink, shoulder, elbow, cuff, 5.5 if up else 2.5)


def _skull(
    ink: Ink,
    center: Vec2,
    angle: float,
    yaw: float,
    eyes: float,
    crown: bool = True,
    jaw: float = 0.0,
) -> None:
    """The skull at `center`, turned `yaw` (as in `Lich.yaw`) and tilted `angle`."""
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)

    def at(forward: float, right: float, y: float) -> Vec2:
        return center + Vec2(forward * cos_y - right * sin_y, y).rotated(angle)

    side_on, front_on = abs(cos_y), abs(sin_y)
    chin = at(1.2 - 0.4 * jaw, 0.0, 4.9 + 1.6 * jaw)
    ink.blob(_oval(chin, 2.5 * side_on + 2.5 * front_on, 1.5, angle), BONE_SHADE)
    ink.circle(at(-0.2, 0.0, -1.0), 5.0, BONE)
    face = at(1.0, 0.0, 1.7)
    ink.blob(_cheeks(face, 2.6 * side_on + 3.6 * front_on, angle), BONE)
    if ink.detail:
        painter = ink.painter
        painter.setPen(_pen(SOCKET, 0.5))
        across, down = Vec2(1.0, 0.0).rotated(angle), Vec2(0.0, 1.0).rotated(angle)
        teeth = at(1.2, 0.0, 3.7)
        width = 1.8 * side_on + 2.0 * front_on
        for k in (-0.6, -0.2, 0.2, 0.6):
            tooth = teeth + across * (k * width)
            painter.drawLine(_qt(tooth - down * 0.7), _qt(tooth + down * 0.7))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SOCKET)
        nose = at(3.0, 0.0, 1.6)
        painter.drawPath(
            _polygon([nose + Vec2(-0.8, -0.5), nose + Vec2(0.8, -0.5), nose + Vec2(0.0, 1.0)])
        )
        for side in (1.0, -1.0):
            facing = math.sin(yaw + side * 0.62)
            size = smoothstep(clamp((facing + 0.2) / 0.5, 0.0, 1.0))
            if size <= 0.01:
                continue
            eye = at(2.3, side * 2.1, -0.4)
            painter.setBrush(SOCKET)
            painter.drawEllipse(_qt(eye), 2.0 * size, 2.2 * size)
            if eyes > 0.0:
                glow = QRadialGradient(_qt(eye), 2.4 * size)
                glow.setColorAt(0.0, _alpha(GLOW, 130 * eyes))
                glow.setColorAt(1.0, _alpha(GLOW, 0))
                painter.setBrush(glow)
                painter.drawEllipse(_qt(eye), 2.4 * size, 2.4 * size)
                painter.setBrush(_alpha(EYE, 255 * eyes))
                painter.drawEllipse(_qt(eye), 0.75 * size, 0.75 * size)
    if crown:
        _crown(ink, center + Vec2(-0.4, -4.4).rotated(angle), angle + 0.08)


def _crown(ink: Ink, base: Vec2, angle: float) -> None:
    def at(x: float, y: float) -> Vec2:
        return base + Vec2(x, y).rotated(angle)

    outline = [
        at(-4.8, 0.6),
        at(-4.9, -2.0),
        at(-4.6, -6.4),
        at(-2.2, -2.9),
        at(0.0, -7.6),
        at(2.2, -2.9),
        at(4.6, -6.4),
        at(4.9, -2.0),
        at(4.8, 0.6),
    ]
    ink.shape(_polygon(outline), GOLD)
    for x, y in ((-4.6, -6.6), (0.0, -7.8), (4.6, -6.6)):
        ink.circle(at(x, y), 0.9, GOLD)
    if ink.detail:
        painter = ink.painter
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(GOLD_SHADE)
        painter.drawPath(_polygon([at(-4.8, 0.6), at(-4.9, -0.8), at(4.9, -0.8), at(4.8, 0.6)]))
        painter.setBrush(GEM)
        painter.drawEllipse(_qt(at(0.0, -1.9)), 1.1, 1.1)
        for x in (-3.0, 3.0):
            painter.drawEllipse(_qt(at(x, -1.7)), 0.7, 0.7)


def _flame(ink: Ink, base: Vec2, t: float, size: float, lean: float) -> None:
    if size <= 0.02 or not ink.detail:
        return
    painter = ink.painter
    glow = QRadialGradient(_qt(base + Vec2(0.0, -3.0 * size)), 14.0 * size)
    glow.setColorAt(0.0, _alpha(GLOW, 120))
    glow.setColorAt(0.5, _alpha(GLOW, 40))
    glow.setColorAt(1.0, _alpha(GLOW, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(_qt(base + Vec2(0.0, -3.0 * size)), 14.0 * size, 14.0 * size)
    flick = 1.1 * math.sin(t * 11.0) + 0.6 * math.sin(t * 17.3 + 1.0) + lean
    tall = 1.0 + 0.12 * math.sin(t * 13.0) + 0.08 * math.sin(t * 7.1)

    def body(scale: float, drop: float) -> list[Vec2]:
        s = size * scale
        return [
            base + Vec2(flick * s, -9.5 * s * tall + drop),
            base + Vec2((2.4 + 0.4 * flick) * s, -4.6 * s + drop),
            base + Vec2(3.2 * s, -1.0 * s + drop),
            base + Vec2(0.0, 2.4 * s + drop),
            base + Vec2(-3.2 * s, -1.0 * s + drop),
            base + Vec2((-2.4 + 0.4 * flick) * s, -4.6 * s + drop),
        ]

    painter.setBrush(FLAME)
    painter.drawPath(_smooth(body(1.0, 0.0)))
    painter.setBrush(FLAME_CORE)
    painter.drawPath(_smooth(body(0.55, 0.8 * size)))
    for k in range(4):
        age = (t * 0.9 + k / 4.0) % 1.0
        x = math.sin(k * 7.3 + t * 3.0) * 2.5 + flick * age
        ember = base + Vec2(x * size, -(6.0 + age * 12.0) * size)
        painter.setBrush(_alpha(FLAME_CORE if k % 2 else FLAME, 230 * (1.0 - age)))
        painter.drawEllipse(_qt(ember), 0.7 * size, 0.7 * size)


def _motes(painter: QPainter, lich: Lich, root: Vec2) -> None:
    lift = clamp(lich.lift.value, 0.0, 1.0)
    if lift < 0.05:
        return
    painter.setPen(Qt.PenStyle.NoPen)
    t = lich.time
    for k in range(6):
        age = (t * 0.7 + k / 6.0) % 1.0
        x = math.sin(k * 2.3 + t * 1.7) * 8.0
        mote = root + Vec2(x, 1.0 + age * 9.0)
        painter.setBrush(_alpha(GLOW, 170 * lift * (1.0 - age)))
        painter.drawEllipse(_qt(mote), 0.9, 0.9)


# ----- the whole figure -------------------------------------------------------------


def _paint(ink: Ink, lich: Lich, joints: Joints | None) -> None:
    if joints is None:
        _paint_dead(ink, lich)
        return
    root = joints.root
    yaw = lich.yaw.value
    forward = math.cos(yaw)
    fdir = 1.0 if forward >= 0.0 else -1.0
    if ink.detail:
        _motes(ink.painter, lich, root)
    far_arm = lich.depth(1.5, -4.0) < 0.0
    if far_arm:
        _arm(ink, joints.shoulders[1], joints.elbows[1], joints.hands[1], fdir, up=False)
    if not joints.flame_front:
        _arm(ink, joints.shoulders[0], joints.elbows[0], joints.hands[0], fdir, up=True)
    for flap in _collar(lich, root):
        _rimmed(ink, _smooth(flap), ROBE)
    robe = _robe_outline(lich, root, 0.0)
    _rimmed(ink, _smooth(robe), ROBE)
    if ink.detail:
        _robe_detail(ink.painter, lich, root, forward)
    _skull(ink, joints.skull, joints.tilt * fdir, yaw, 1.0, jaw=joints.jaw)
    if not far_arm:
        _arm(ink, joints.shoulders[1], joints.elbows[1], joints.hands[1], fdir, up=False)
    if joints.flame_front:
        _arm(ink, joints.shoulders[0], joints.elbows[0], joints.hands[0], fdir, up=True)
    if joints.finger > 0.05:
        hand = joints.hands[1]
        knuckle = hand + Vec2(fdir * 1.4, 0.2)
        tip = knuckle + Vec2(fdir * 4.8 * joints.finger, -0.6 * joints.finger)
        ink.limb([knuckle, tip], [1.2, 0.8], BONE)
    size = 0.8 + 0.7 * clamp(lich.flare.value, 0.0, 1.2)
    _flame(ink, joints.flame, lich.time, size, clamp(-lich.drag.value * 0.04, -1.5, 1.5))
    if ink.detail and joints.crackle > 0.02:
        _crackle(ink.painter, joints.hands[0], joints.hands[1], fdir, lich.time, joints.crackle)


def _crackle(
    painter: QPainter, hand: Vec2, other: Vec2, fdir: float, t: float, amount: float
) -> None:
    """Lightning flickering between his outstretched hands and off his fingertips."""
    jag = random.Random(int(t * 30.0))
    tips = [hand + Vec2(fdir * 3.5, -1.0), other + Vec2(fdir * 3.0, 0.5)]
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for a, b in ((tips[0], tips[1]), *((tip, tip + Vec2(fdir * 6.0, 0.0)) for tip in tips)):
        points = [a]
        for i in range(1, 4):
            points.append(a.lerp(b, i / 4) + Vec2(jag.uniform(-1.5, 1.5), jag.uniform(-2.0, 2.0)))
        points.append(b + Vec2(jag.uniform(-1.0, 1.0), jag.uniform(-1.5, 1.5)))
        path = QPainterPath(_qt(points[0]))
        for point in points[1:]:
            path.lineTo(_qt(point))
        painter.setPen(_pen(_alpha(GLOW, 120 * amount), 2.4))
        painter.drawPath(path)
        painter.setPen(_pen(_alpha(CRACKLE, 255 * amount), 0.8))
        painter.drawPath(path)


def _robe_detail(painter: QPainter, lich: Lich, root: Vec2, forward: float) -> None:
    """The one lit panel down his front and a couple of dark folds."""
    trail = clamp(-lich.drag.value * 0.07, -4.0, 4.0)
    shift = 3.6 * forward
    top = lich.project(0.0, 0.0, -31.0, root) + Vec2(shift * 0.6, 0.0)
    mid = lich.project(0.0, 0.0, -16.0, root) + Vec2(shift * 0.9 + trail * 0.2, 0.0)
    bottom = root + Vec2(shift + trail * 0.6, -3.5)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ROBE_LIGHT)
    painter.drawPath(
        _smooth(
            [
                top + Vec2(-0.8, 0),
                mid + Vec2(-1.6, 0),
                bottom + Vec2(-2.2, 0),
                bottom + Vec2(1.8, 0),
                mid + Vec2(1.2, 0),
                top + Vec2(0.6, 0),
            ]
        )
    )
    painter.setPen(_pen(ROBE_FOLD, 0.8))
    a = lich.project(0.0, 0.0, -20.0, root) + Vec2(-2.6 - shift * 0.3, 0.0)
    b = root + Vec2(-4.0 - shift * 0.2 + trail * 0.5, -4.0)
    painter.drawLine(_qt(a), _qt(b))


def _paint_dead(ink: Ink, lich: Lich) -> None:
    root = lich.position
    slump = smoothstep(lich.slump)
    robe = _robe_outline(lich, root, slump)
    _rimmed(ink, _smooth(robe), ROBE)
    if slump < 0.7:
        for flap in _collar(lich, root + Vec2(0.0, 28.0 * slump)):
            squash = [root + (p - root) * (1.0 - slump) for p in flap]
            _rimmed(ink, _smooth(squash), ROBE)
    hand_bit = None
    for bit in lich.bits:
        _bit(ink, lich, bit)
        if bit.kind == "hand":
            hand_bit = bit
    if hand_bit is not None and lich.flame > 0.0:
        sputter = 0.75 + 0.25 * math.sin(lich.time * 31.0)
        _flame(ink, hand_bit.position + Vec2(0.0, -2.5), lich.time, lich.flame * sputter, 0.0)


def _bit(ink: Ink, lich: Lich, bit: Bit) -> None:
    if bit.kind == "skull":
        yaw = 0.35 if lich.heading > 0 else math.pi - 0.35
        _skull(ink, bit.position, bit.angle, yaw, 0.0, crown=False)
    elif bit.kind == "crown":
        _crown(ink, bit.position + Vec2(0.0, 2.0), bit.angle)
    elif bit.kind == "hand":
        _hand(ink, bit.position, 1.0 if lich.heading > 0 else -1.0, up=True)
    else:
        half = Vec2(3.2, 0.0).rotated(bit.angle)
        _bone(ink, bit.position - half, bit.position + half, 1.4)
        ink.circle(bit.position - half, 1.0, BONE)
        ink.circle(bit.position + half, 1.0, BONE)
