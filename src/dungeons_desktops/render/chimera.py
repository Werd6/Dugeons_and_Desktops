"""Drawing the chimera in the dragon's flat style: a tawny lion's forequarters with a
mane, black goat's hindquarters on pale hooves, a goat's head on a neck rising from its
back, and a grey-green serpent for a tail, arching over its back."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.render.draw import draw_fire, qt, world_pen
from dungeons_desktops.rig.ik import two_bone_points
from dungeons_desktops.systems.chimera import Chimera, Leg

LION = QColor(204, 166, 108)
LION_FAR = QColor(150, 118, 76)
LION_LIGHT = QColor(232, 206, 156)
MANE = QColor(164, 86, 36)
GOAT = QColor(46, 42, 50)
GOAT_FAR = QColor(28, 26, 32)
HORN = QColor(232, 222, 196)
HOOF = QColor(228, 224, 214)
SNAKE = QColor(118, 134, 102)
SNAKE_LIGHT = QColor(170, 180, 140)
EYE = QColor(250, 214, 80)
MOUTH = QColor(92, 22, 28)
TONGUE = QColor(212, 64, 82)
NOSE = QColor(60, 36, 32)

BODY_WIDTH = 13.0
SNAKE_WIDTHS = (5.0, 4.6, 4.3, 4.1, 4.0, 3.9, 3.8)
"""The serpent's thickness from root toward its neck (it keeps the last one after)."""
SNAKE_HEAD_SCALE = 1.35


def draw_chimeras(
    painter: QPainter, chimeras: Iterable[Chimera], outline: QColor | None = None
) -> None:
    for chimera in chimeras:
        draw_chimera(painter, chimera, outline)
        draw_fire(painter, chimera.flames)


def draw_chimera(painter: QPainter, chimera: Chimera, outline: QColor | None = None) -> None:
    """Far legs, goat neck and head, body, serpent, near legs, mane and lion head (its
    goat's fire is `draw_fire`)."""
    near = [_limb(chimera, leg) for leg in chimera.legs if leg.near]
    far = [_limb(chimera, leg) for leg in chimera.legs if not leg.near]
    widths = _snake_widths(len(chimera.tail))

    if outline is not None:
        for limb in far + near:
            limb.paint(painter, outline, 2.0)
        _body_shape(painter, chimera, outline, 2.0)
        _goat_neck(painter, chimera, outline, 2.0)
        _snake_body(painter, chimera, widths, outline, 2.0)
        _mane(painter, chimera, outline, 1.0)

    for limb in far:
        limb.paint(painter, None, 0.0)
        limb.feet(painter)
    _goat_neck(painter, chimera, None, 0.0)
    _goat_head(painter, chimera)
    _body(painter, chimera)
    _snake_body(painter, chimera, widths, None, 0.0)
    _snake_head(painter, chimera)
    for limb in near:
        limb.paint(painter, None, 0.0)
        limb.feet(painter)
    _mane(painter, chimera)
    _lion_head(painter, chimera)


# ----- shapes ----------------------------------------------------------------------------


def _taper(painter: QPainter, a: Vec2, b: Vec2, wa: float, wb: float, color: QColor) -> None:
    """A limb or neck segment from `a` (`wa` across) to `b` (`wb`), rounded at both ends."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    along = b - a
    if along.length() > 1e-6:
        side = along.normalized().rotated(math.pi / 2)
        painter.drawPolygon(
            [
                qt(a + side * (wa / 2)),
                qt(b + side * (wb / 2)),
                qt(b - side * (wb / 2)),
                qt(a - side * (wa / 2)),
            ]
        )
    painter.drawEllipse(qt(a), wa / 2, wa / 2)
    painter.drawEllipse(qt(b), wb / 2, wb / 2)


def _polygon(painter: QPainter, color: QColor, points: list[Vec2]) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon([qt(p) for p in points])


def _head_frame(
    head: Vec2, angle: float, facing: int, scale: float = 1.0
) -> Callable[[float, float], Vec2]:
    forward = Vec2.from_angle(angle)
    up = forward.rotated(-facing * math.pi / 2)

    def at(x: float, y: float) -> Vec2:
        return head + forward * (x * scale) - up * (y * scale)

    return at


def _hinged(at: Callable[[float, float], Vec2], hinge: Vec2, open_by: float):
    """A lower jaw's frame: `at`, swung open about `hinge` by `open_by`."""

    def jaw(x: float, y: float) -> Vec2:
        return hinge + (at(x, y) - hinge).rotated(open_by)

    return jaw


# ----- legs ------------------------------------------------------------------------------


class _Limb:
    def __init__(
        self,
        chimera: Chimera,
        front: bool,
        joints: list[Vec2],
        widths: list[float],
        color: QColor,
        foot_color: QColor,
        lift: float,
    ) -> None:
        self.chimera = chimera
        self.front = front
        self.joints = joints
        self.widths = widths
        self.color = color
        self.foot_color = foot_color
        self.lift = lift

    def paint(self, painter: QPainter, outline: QColor | None, grow: float) -> None:
        color = outline if outline is not None else self.color
        for i in range(len(self.joints) - 1):
            _taper(
                painter,
                self.joints[i],
                self.joints[i + 1],
                self.widths[i] + grow,
                self.widths[i + 1] + grow,
                color,
            )
        if outline is not None:
            ankle = self.joints[-1]
            painter.drawEllipse(qt(ankle + self._toe() * 1.6), 2.6 + grow / 2, 2.0 + grow / 2)

    def _toe(self) -> Vec2:
        forward, up = self.chimera.forward, self.chimera.up
        hang = (forward * 0.4 - up).normalized()
        return forward.lerp(hang, smoothstep(self.lift)).normalized()

    def feet(self, painter: QPainter) -> None:
        """A round paw for the lion, a pale wedge of a hoof for the goat."""
        ankle = self.joints[-1]
        toe = self._toe()
        down = Vec2(-toe.y, toe.x) if self.chimera.facing > 0 else Vec2(toe.y, -toe.x)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.front:
            painter.setBrush(self.color)
            painter.drawEllipse(qt(ankle + toe * 1.6 + down * 0.6), 2.8, 1.9)
        else:
            heel = ankle + down * 0.4
            tip = ankle + toe * 3.2 + down * 1.6
            back = ankle - toe * 0.6 + down * 1.6
            _polygon(painter, self.foot_color, [heel - toe * 0.8, heel + toe * 1.6, tip, back])


def _blend_angle(a: float, b: float, t: float) -> float:
    return a + math.remainder(b - a, math.tau) * t


def _limb(chimera: Chimera, leg: Leg) -> _Limb:
    """Shoulder, elbow, wrist, paw for a lion's foreleg; hip, knee, hock, hoof for a
    goat's hind leg, raked back. Both end on the sim's foot point."""
    facing = chimera.facing
    lift = smoothstep(leg.lift)
    root, foot = leg.root, leg.foot
    if leg.front:
        thigh, shin, low, rake = 8.6, 8.4, 3.4, 0.2
        widths = [6.6, 4.6, 3.6, 3.2]
        color = LION if leg.near else LION_FAR
    else:
        thigh, shin, low, rake = 8.0, 8.2, 5.6, 0.5
        widths = [8.0, 4.2, 2.6, 2.4]
        color = GOAT if leg.near else GOAT_FAR
    up = chimera.up
    rise = up.rotated(-facing * rake).angle()
    reach = root - foot
    if reach.length() > 1e-6:
        rise = _blend_angle(rise, reach.angle(), lift)
    rise_dir = Vec2.from_angle(rise)
    ankle = foot + up * 2.2
    hock = ankle + rise_dir * low
    stretch = max(1.0, hock.distance_to(root) / (0.97 * (thigh + shin)))
    bend = -facing if leg.front else facing
    _, knee, hock = two_bone_points(root, thigh * stretch, shin * stretch, hock, bend)
    foot_color = HOOF if leg.near else HOOF.darker(135)
    return _Limb(chimera, leg.front, [root, knee, hock, ankle], widths, color, foot_color, leg.lift)


# ----- body ------------------------------------------------------------------------------


def _body_shape(painter: QPainter, chimera: Chimera, color: QColor, grow: float) -> None:
    painter.setPen(world_pen(color, BODY_WIDTH + grow))
    painter.drawLine(qt(chimera.hip), qt(chimera.shoulder))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    chest = chimera.shoulder + chimera.local(Vec2(1.5, 1.5))
    painter.drawEllipse(qt(chest), 8.0 + grow / 2, 8.0 + grow / 2)


def _body(painter: QPainter, chimera: Chimera) -> None:
    """A tawny lion's body, black from a slanted seam back where the goat takes over."""
    hip, body, local = chimera.hip, chimera.body, chimera.local
    _body_shape(painter, chimera, LION, 0.0)
    rear = [
        body + local(Vec2(1.0, -12.0)),
        body + local(Vec2(-4.0, 12.0)),
        hip + local(Vec2(-12.0, 12.0)),
        hip + local(Vec2(-12.0, -12.0)),
    ]
    clip = QPainterPath()
    clip.addPolygon(QPolygonF([qt(p) for p in rear]))
    painter.save()
    painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
    painter.setPen(world_pen(GOAT, BODY_WIDTH))
    painter.drawLine(qt(hip), qt(chimera.shoulder))
    painter.restore()


# ----- goat ------------------------------------------------------------------------------


def _goat_neck(painter: QPainter, chimera: Chimera, outline: QColor | None, grow: float) -> None:
    color = outline if outline is not None else GOAT
    _taper(painter, chimera.goat_root, chimera.goat_head, 9.0 + grow, 5.4 + grow, color)


def _goat_head(painter: QPainter, chimera: Chimera) -> None:
    """A long black muzzle, a beard, an eye and a horn swept back."""
    facing = chimera.goat_facing
    at = _head_frame(chimera.goat_head, chimera.goat_angle, facing)
    hinge = at(-1.5, 1.0)
    jaw = _hinged(at, hinge, 0.45 * chimera.goat_jaw * facing)

    _polygon(painter, GOAT, [at(-0.5, 1.6), at(3.5, 1.8), at(1.0, 7.0)])
    if chimera.goat_jaw > 0.05:
        _polygon(painter, MOUTH, [hinge, at(8.5, 0.6), jaw(8.0, 1.2)])
    _polygon(painter, GOAT, [jaw(-2.0, 0.8), jaw(8.0, 0.8), jaw(7.6, 2.0), jaw(-1.2, 2.6)])
    _polygon(
        painter,
        GOAT,
        [at(-3.5, -2.2), at(1.5, -3.0), at(6.0, -1.6), at(9.2, 0.0), at(9.0, 1.0), at(-3.0, 2.0)],
    )
    painter.setBrush(EYE)
    painter.drawEllipse(qt(at(1.4, -1.3)), 0.9, 0.7)

    steps = 6
    points = [at(-1.0 - 12.0 * t, -2.6 - 2.6 * t + 1.8 * t * t) for t in _steps(steps)]
    widths = [2.3 * (1.0 - t) + 0.4 for t in _steps(steps)]
    for k in range(steps):
        _taper(painter, points[k], points[k + 1], widths[k], widths[k + 1], HORN)


def _steps(count: int) -> list[float]:
    return [k / count for k in range(count + 1)]


# ----- lion ------------------------------------------------------------------------------


def _mane(
    painter: QPainter, chimera: Chimera, outline: QColor | None = None, grow: float = 0.0
) -> None:
    """A soft ring of rounded tufts round the lion's neck, fuller behind."""
    center, local = chimera.mane, chimera.local
    sway = math.sin(chimera.clock * 1.2) * 0.3
    tufts = 7
    points = []
    for k in range(72):
        a = math.tau * k / 72
        behind = max(0.0, -math.cos(a))
        r = 8.4 + 1.0 * abs(math.sin(a * tufts / 2)) + 1.2 * behind + grow
        sweep = -(1.5 + sway) * behind
        points.append(center + local(Vec2(math.cos(a) * r * 0.9 + sweep, math.sin(a) * r)))
    _polygon(painter, outline if outline is not None else MANE, points)


def _lion_head(painter: QPainter, chimera: Chimera) -> None:
    """A broad muzzle with a dark nose and a gold eye, the jaw dropping open on a roar."""
    facing = chimera.facing
    at = _head_frame(chimera.lion_head, chimera.lion_angle, facing)
    hinge = at(-1.5, 1.8)
    jaw = _hinged(at, hinge, 0.6 * chimera.lion_jaw * facing)

    if chimera.lion_jaw > 0.05:
        _polygon(painter, MOUTH, [hinge, at(7.5, 1.6), jaw(7.0, 2.0)])
    _polygon(painter, LION_LIGHT, [jaw(-2.0, 1.8), jaw(7.0, 1.8), jaw(6.4, 3.4), jaw(-0.8, 4.0)])
    upper = [at(-4.0, -4.0), at(1.5, -4.6), at(5.0, -3.2), at(8.0, -1.2), at(8.4, 1.0)]
    _polygon(painter, LION, [*upper, at(7.4, 2.0), at(-3.5, 2.6)])
    _polygon(painter, NOSE, [at(7.0, -1.0), at(8.6, -0.6), at(8.0, 0.4)])
    painter.setBrush(EYE)
    painter.drawEllipse(qt(at(2.6, -2.0)), 1.0, 0.75)


# ----- serpent ---------------------------------------------------------------------------


def _snake_widths(count: int) -> list[float]:
    return [SNAKE_WIDTHS[min(i, len(SNAKE_WIDTHS) - 1)] for i in range(count)]


def _snake_body(
    painter: QPainter,
    chimera: Chimera,
    widths: list[float],
    outline: QColor | None,
    grow: float,
) -> None:
    tail = chimera.tail
    color = outline if outline is not None else SNAKE
    for i in range(len(tail) - 1):
        painter.setPen(world_pen(color, widths[i] + grow))
        painter.drawLine(qt(tail[i]), qt(tail[i + 1]))


def _snake_head(painter: QPainter, chimera: Chimera) -> None:
    """A wedge of a head with a pale jaw that gapes on a hiss, and a flicking tongue."""
    facing = chimera.snake_facing
    at = _head_frame(chimera.snake_head, chimera.snake_angle, facing, SNAKE_HEAD_SCALE)
    hiss = chimera.snake_jaw
    hinge = at(-1.2, 0.6)
    jaw = _hinged(at, hinge, 0.65 * hiss * facing)

    if hiss > 0.05:
        _polygon(painter, MOUTH, [hinge, at(5.6, 0.4), jaw(5.2, 0.8)])
        flick = 0.5 + 0.5 * math.sin(chimera.clock * 22.0)
        root = hinge.lerp(at(5.0, 0.6), 0.6)
        tip = root + (at(6.8 + 1.2 * flick, 0.9) - root) * hiss
        painter.setPen(world_pen(TONGUE, 0.5))
        painter.drawLine(qt(root), qt(tip))
    _polygon(painter, SNAKE_LIGHT, [jaw(-2.0, 0.4), jaw(5.4, 0.4), jaw(4.8, 1.5), jaw(-1.5, 2.0)])
    upper = [at(-2.8, -1.8), at(1.6, -2.4), at(5.0, -1.2), at(6.2, 0.2), at(5.4, 0.7)]
    _polygon(painter, SNAKE, [*upper, at(-2.6, 1.0)])
    painter.setBrush(EYE)
    painter.drawEllipse(qt(at(2.2, -1.0)), 0.9, 0.7)
