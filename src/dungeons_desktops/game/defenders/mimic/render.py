"""QPainter drawing of the mimic, and the "!" over the adventurer it lures.

Drawn flat, like the rest of the game, in one of two views: front-on (lock plate to the
viewer) as a chest, and in side profile as a monster, its lid hinged at the back so it
opens forward as a toothy jaw. Turns are flat flips: the view squashes narrow and
widens again mirrored (`Mimic.scales`). Everything is drawn in its surface frame (x
along the surface, y toward it), so the same picture stands on a window top, clings to
a side or hangs under an underside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.defenders.mimic.actor import (
    BOX_HEIGHT,
    CHEST_DEPTH,
    CHEST_WIDTH,
    DUST_TIME,
    HEIGHT,
    LID_ARCH,
    LID_HEIGHT,
    Coin,
    Knife,
    Mimic,
    Mode,
)

WOOD = QColor(150, 96, 52)
WOOD_DARK = QColor(104, 64, 34)
WOOD_LIGHT = QColor(186, 128, 72)
GRAIN = QColor(92, 56, 28)
IRON = QColor(70, 72, 80)
IRON_LIGHT = QColor(128, 132, 142)
BRASS = QColor(222, 178, 70)
BRASS_DARK = QColor(150, 110, 34)
GOLD = QColor(255, 214, 90)
GOLD_GLOW = QColor(255, 220, 110, 120)
MAW = QColor(70, 10, 18)
MAW_DEEP = QColor(36, 4, 10)
TONGUE = QColor(214, 70, 96)
TONGUE_DARK = QColor(150, 36, 60)
TOOTH = QColor(246, 240, 222)
TOOTH_EDGE = QColor(170, 160, 140)
EYE = QColor(255, 222, 70)
PUPIL = QColor(20, 10, 10)
LEG = QColor(64, 40, 30)
LEG_FAR = QColor(40, 26, 20)
ALERT = QColor(255, 220, 40)
ALERT_EDGE = QColor(60, 36, 0)
FLASH = QColor(255, 250, 220)
DUST = QColor(196, 186, 168)
STEEL = QColor(206, 212, 222)
HILT = QColor(96, 64, 40)

JAW_OPEN = 1.35
"""The lid's swing (radians) with its jaw wide open."""
GAP_OPEN = 7.0
"""Front-on, how far the lid's edge rises with its jaw wide open."""
MIN_SCALE = 0.12
"""Flipping, it squashes no narrower than this."""
TEETH = 5


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


@dataclass
class Op:
    """One thing to paint, in order: a filled polygon/path or a stroked line."""

    path: QPainterPath
    fill: QColor | None
    edge: QColor | None
    width: float
    outlined: bool = True


class Canvas:
    def __init__(self) -> None:
        self.ops: list[Op] = []

    def poly(
        self,
        points: list[Vec2],
        fill: QColor | None,
        edge: QColor | None = None,
        width: float = 0.5,
        outlined: bool = True,
    ) -> None:
        path = QPainterPath()
        path.addPolygon(QPolygonF([_qt(p) for p in points]))
        path.closeSubpath()
        self.ops.append(Op(path, fill, edge, width, outlined))

    def line(self, points: list[Vec2], color: QColor, width: float, outlined: bool = True) -> None:
        path = QPainterPath(_qt(points[0]))
        for p in points[1:]:
            path.lineTo(_qt(p))
        self.ops.append(Op(path, None, color, width, outlined))

    def ellipse(
        self, center: Vec2, rx: float, ry: float, fill: QColor, edge: QColor | None = None
    ) -> None:
        path = QPainterPath()
        path.addEllipse(_qt(center), rx, ry)
        self.ops.append(Op(path, fill, edge, 0.4, False))

    def paint(self, painter: QPainter, outline: QColor | None) -> None:
        if outline is not None:
            for op in self.ops:
                if not op.outlined:
                    continue
                painter.setPen(_pen(outline, op.width + 1.6))
                painter.setBrush(outline if op.fill is not None else Qt.BrushStyle.NoBrush)
                painter.drawPath(op.path)
        for op in self.ops:
            painter.setPen(_pen(op.edge, op.width) if op.edge is not None else Qt.PenStyle.NoPen)
            painter.setBrush(op.fill if op.fill is not None else Qt.BrushStyle.NoBrush)
            painter.drawPath(op.path)


# ----- a flat frame ----------------------------------------------------------------------


@dataclass
class Frame:
    """Its body coordinates (x along its view, z up off its bottom) in its surface frame,
    squashed by `scale` across."""

    scale: float
    base: float
    """Surface-frame y of its bottom (negative: up off the surface)."""
    shift: float
    breath: float = 1.0

    def __call__(self, x: float, z: float) -> Vec2:
        return Vec2(self.shift + x * self.scale, self.base - z * self.breath)


def _swing(mimic: Mimic) -> float:
    """How far its lid is open (0 shut, 1 its jaw wide)."""
    twitch = 0.07 * math.sin(math.pi * (1.0 - mimic.twitch)) if mimic.twitch > 0.0 else 0.0
    return mimic.crack * 0.5 + mimic.jaw + twitch


def _tooth(canvas: Canvas, a: Vec2, b: Vec2, tip: Vec2) -> None:
    canvas.poly([a, b, tip], TOOTH, TOOTH_EDGE, 0.25, False)


def _glint(canvas: Canvas, mimic: Mimic, at: Vec2) -> None:
    shine = max(0.0, math.sin(mimic.time * 1.3 + 0.7)) ** 24
    if shine < 0.05:
        return
    r = 2.6 * shine
    color = _alpha(QColor(255, 250, 210), 255 * shine)
    canvas.line([at - Vec2(r, 0.0), at + Vec2(r, 0.0)], color, 0.5, False)
    canvas.line([at - Vec2(0.0, r), at + Vec2(0.0, r)], color, 0.5, False)


def _eye(canvas: Canvas, at: Vec2, size: float, squash: float) -> None:
    canvas.ellipse(at, 1.6 * size * squash + 0.2, 1.4 * size, EYE, PUPIL)
    canvas.ellipse(at, 0.45 * squash + 0.05, 1.0 * size, PUPIL)


def _tongue(canvas: Canvas, mimic: Mimic, points: list[Vec2]) -> None:
    canvas.line(points, TONGUE_DARK, 2.8, False)
    canvas.line(points, TONGUE, 2.0, False)


def _awake(mimic: Mimic) -> float:
    return clamp(mimic.rise * 1.6 - 0.4, 0.0, 1.0) * (0.0 if mimic.dead else 1.0)


# ----- front-on: the chest ---------------------------------------------------------------


def _draw_front(canvas: Canvas, mimic: Mimic, f: Frame) -> None:
    w = CHEST_WIDTH / 2
    h = BOX_HEIGHT
    swing = _swing(mimic)
    gap = GAP_OPEN * swing
    box = [f(-w, 0.0), f(w, 0.0), f(w, h), f(-w, h)]
    if gap > 0.3:
        _front_maw(canvas, mimic, f, gap)
    canvas.poly(box, WOOD, WOOD_DARK, 0.5)
    for z in (h * 0.36, h * 0.68):
        canvas.line([f(-w + 0.8, z), f(w - 0.8, z)], GRAIN, 0.3, False)
    for x0, x1 in ((-w * 0.8, -w * 0.6), (w * 0.6, w * 0.8)):
        canvas.poly([f(x0, 0.0), f(x1, 0.0), f(x1, h), f(x0, h)], IRON, None, 0.3, False)
    canvas.poly([f(-w, 0.0), f(w, 0.0), f(w, 0.9), f(-w, 0.9)], IRON, None, 0.3, False)
    plate = [f(-2.2, h * 0.3), f(2.2, h * 0.3), f(2.2, h), f(-2.2, h)]
    canvas.poly(plate, BRASS, BRASS_DARK, 0.4, False)
    hole = f(0.0, h * 0.68)
    canvas.ellipse(hole, 0.7 * abs(f.scale), 0.8, PUPIL)
    canvas.line([hole, hole + Vec2(0.0, 1.4)], PUPIL, 0.5, False)
    if _teeth_show(mimic, gap):
        for k in range(TEETH):
            x0 = -w + 2 * w * k / TEETH + 0.5
            x1 = -w + 2 * w * (k + 1) / TEETH - 0.5
            tall = min(2.2, gap * 0.35)
            _tooth(canvas, f(x0, h), f(x1, h), f((x0 + x1) / 2, h + tall))
    _front_lid(canvas, mimic, f, gap)
    if mimic.mode is Mode.CHEST and not mimic.dead:
        _glint(canvas, mimic, f(w * 0.25, h + LID_HEIGHT + LID_ARCH - 0.5))


def _teeth_show(mimic: Mimic, gap: float) -> bool:
    """Front-on, its teeth show once it's opening as a monster, not as loot."""
    return gap > 1.0 and not (mimic.mode is Mode.OPEN and mimic.jaw < 0.3)


def _front_maw(canvas: Canvas, mimic: Mimic, f: Frame, gap: float) -> None:
    w = CHEST_WIDTH / 2 - 0.6
    h = BOX_HEIGHT
    mouth = [f(-w, h - 1.0), f(w, h - 1.0), f(w, h + gap), f(-w, h + gap)]
    golden = mimic.mode is Mode.OPEN and mimic.jaw < 0.05
    canvas.poly(mouth, GOLD if golden else MAW, MAW_DEEP, 0.4, False)
    if golden:
        canvas.ellipse(
            f(0.0, h + gap * 0.5), CHEST_WIDTH * 0.6 * abs(f.scale), 2.0 + gap, GOLD_GLOW
        )
        for k in range(4):
            canvas.ellipse(f(-w * 0.6 + k * w * 0.4, h + 0.4), 1.3, 0.8, BRASS, BRASS_DARK)
        return
    look = clamp((gap - 3.0) / 3.0, 0.0, 1.0) * (0.0 if mimic.dead else 1.0)
    if look > 0.0:
        _eye(canvas, f(0.0, h + gap * 0.62), look, abs(f.scale))
    if gap > 2.0 and mimic.tongue_tip is None and mimic.caught is None:
        sway = math.sin(mimic.time * 4.0) * 1.2
        lash = smoothstep(clamp(mimic.jaw, 0.0, 1.0))
        side = mimic.victim_side if mimic.mode is Mode.OPEN else 0
        root = f(0.0, h + 0.8)
        lip = f(sway * 0.5 + side * 3.0 * lash, h + 0.2)
        tip = f(sway + side * 11.0 * lash, h - 2.5 - 2.0 * lash)
        _tongue(canvas, mimic, [root, lip, tip])


def _front_lid(canvas: Canvas, mimic: Mimic, f: Frame, gap: float) -> None:
    w = CHEST_WIDTH / 2
    tilt = clamp(gap / GAP_OPEN, 0.0, 1.0)
    tall = (LID_HEIGHT + LID_ARCH) * (1.0 - 0.45 * tilt)
    bottom = BOX_HEIGHT + gap
    round_ = 1.4
    lid = [
        f(-w, bottom),
        f(w, bottom),
        f(w, bottom + tall - round_),
        f(w - round_, bottom + tall),
        f(-w + round_, bottom + tall),
        f(-w, bottom + tall - round_),
    ]
    if gap > 0.3:
        inner = clamp(gap * 0.4, 0.0, 2.2)
        rim = [f(-w, bottom - inner), f(w, bottom - inner), f(w, bottom), f(-w, bottom)]
        canvas.poly(rim, MAW, MAW_DEEP, 0.4)
        if _teeth_show(mimic, gap):
            for k in range(TEETH):
                x0 = -w + 2 * w * k / TEETH + 0.5
                x1 = -w + 2 * w * (k + 1) / TEETH - 0.5
                long = min(2.4, gap * 0.4)
                _tooth(canvas, f(x0, bottom), f(x1, bottom), f((x0 + x1) / 2, bottom - long))
    canvas.poly(lid, WOOD_LIGHT, WOOD_DARK, 0.5)
    canvas.line(
        [f(-w + 0.6, bottom + tall * 0.5), f(w - 0.6, bottom + tall * 0.5)], GRAIN, 0.3, False
    )
    for x0, x1 in ((-w * 0.8, -w * 0.6), (w * 0.6, w * 0.8)):
        band = [f(x0, bottom), f(x1, bottom), f(x1, bottom + tall), f(x0, bottom + tall)]
        canvas.poly(band, IRON, None, 0.3, False)
    hasp = [
        f(-1.6, bottom - 1.2),
        f(1.6, bottom - 1.2),
        f(1.2, bottom + tall * 0.6),
        f(-1.2, bottom + tall * 0.6),
    ]
    canvas.poly(hasp, BRASS, BRASS_DARK, 0.3, False)


# ----- side-on: the monster --------------------------------------------------------------


def _lid_profile() -> list[tuple[float, float]]:
    """The lid's end, (back-to-front, up) from its hinge: an arch over a band."""
    d = CHEST_DEPTH
    points = [(0.0, 0.0), (d, 0.0), (d, LID_HEIGHT)]
    for i in range(1, 8):
        a = d * (1.0 - i / 8)
        k = 2.0 * a / d - 1.0
        points.append((a, LID_HEIGHT + LID_ARCH * math.sqrt(max(0.0, 1.0 - k * k))))
    points.append((0.0, LID_HEIGHT))
    return points


LID_PROFILE = _lid_profile()


def _arch(a: float) -> float:
    k = 2.0 * a / CHEST_DEPTH - 1.0
    return LID_HEIGHT + LID_ARCH * math.sqrt(max(0.0, 1.0 - k * k))


def _draw_side(canvas: Canvas, mimic: Mimic, f: Frame) -> None:
    d = CHEST_DEPTH / 2
    h = BOX_HEIGHT
    angle = _swing(mimic) * JAW_OPEN
    cos, sin = math.cos(angle), math.sin(angle)

    def lid(a: float, up: float) -> Vec2:
        return f(-d + a * cos - up * sin, h + a * sin + up * cos)

    front = lid(CHEST_DEPTH, 0.0)
    if angle > 0.04:
        canvas.poly([f(-d, h), f(d - 0.4, h), front], MAW, MAW_DEEP, 0.4, False)
    canvas.poly([f(-d, 0.0), f(d, 0.0), f(d, h), f(-d, h)], WOOD, WOOD_DARK, 0.5)
    for z in (h * 0.36, h * 0.68):
        canvas.line([f(-d + 0.8, z), f(d - 0.8, z)], GRAIN, 0.3, False)
    for x0, x1 in ((-d * 0.8, -d * 0.55), (d * 0.55, d * 0.8)):
        canvas.poly([f(x0, 0.0), f(x1, 0.0), f(x1, h), f(x0, h)], IRON, None, 0.3, False)
    canvas.poly([f(-d, 0.0), f(d, 0.0), f(d, 0.9), f(-d, 0.9)], IRON, None, 0.3, False)
    canvas.ellipse(f(d - 0.9, 1.6), 0.6 * abs(f.scale) + 0.1, 0.6, BRASS, BRASS_DARK)
    canvas.ellipse(f(-d + 0.9, 1.6), 0.6 * abs(f.scale) + 0.1, 0.6, BRASS, BRASS_DARK)
    if angle > 0.2:
        count = 4
        for k in range(count):
            x0 = -d + 2.5 + (2 * d - 3.0) * k / count
            x1 = -d + 2.5 + (2 * d - 3.0) * (k + 1) / count - 0.6
            _tooth(canvas, f(x0, h), f(x1, h), f((x0 + x1) / 2 + 0.2, h + 2.2))
        for k in range(count):
            a0 = 2.5 + (CHEST_DEPTH - 3.0) * k / count
            a1 = 2.5 + (CHEST_DEPTH - 3.0) * (k + 1) / count - 0.6
            _tooth(canvas, lid(a0, 0.0), lid(a1, 0.0), lid((a0 + a1) / 2 + 0.2, -2.4))
    canvas.poly([lid(a, up) for a, up in LID_PROFILE], WOOD_LIGHT, WOOD_DARK, 0.5)
    for a0, a1 in (
        (CHEST_DEPTH * 0.1, CHEST_DEPTH * 0.22),
        (CHEST_DEPTH * 0.78, CHEST_DEPTH * 0.9),
    ):
        band = [lid(a0, 0.0), lid(a1, 0.0), lid(a1, _arch(a1)), lid(a0, _arch(a0))]
        canvas.poly(band, IRON, None, 0.3, False)
    canvas.line([lid(CHEST_DEPTH, 0.2), lid(CHEST_DEPTH, LID_HEIGHT)], BRASS, 0.9, False)
    awake = _awake(mimic)
    if awake > 0.0:
        _eye(canvas, lid(CHEST_DEPTH * 0.66, LID_HEIGHT * 0.95), awake, abs(f.scale))


# ----- legs ------------------------------------------------------------------------------


def _legs(mimic: Mimic) -> list[tuple[bool, list[Vec2]]]:
    """Each leg's (root, knee, foot) from its IK rig, in its surface frame (x along,
    y into the surface, as it's painted)."""
    x_axis = Vec2(-mimic.up.y, mimic.up.x)
    origin, up = mimic.position, mimic.up
    legs = []
    for near, hip, knee, foot in mimic.rig.points(origin, up, mimic.lift, mimic.legs):
        points = [Vec2((p - origin).dot(x_axis), -(p - origin).dot(up)) for p in (hip, knee, foot)]
        legs.append((near, points))
    return legs


def _draw_legs(canvas: Canvas, legs, near: bool) -> None:
    for is_near, (root, knee, foot) in legs:
        if is_near != near:
            continue
        color = LEG if near else LEG_FAR
        canvas.line([root, knee], color, 1.5)
        canvas.line([knee, foot], color, 1.1)
        canvas.ellipse(knee, 0.7, 0.7, color)


# ----- the whole thing ------------------------------------------------------------------


def draw_mimic(painter: QPainter, mimic: Mimic, outline: QColor | None = None) -> None:
    up = mimic.up
    angle = math.degrees(math.atan2(up.x, -up.y))
    painter.save()
    painter.translate(_qt(mimic.position))
    painter.rotate(angle)
    side = mimic.victim_side
    if mimic.tilt:
        pivot = QPointF(side * CHEST_WIDTH / 2, 0.0)
        painter.translate(pivot)
        painter.rotate(side * math.degrees(mimic.tilt))
        painter.translate(-pivot)
    breath = 1.0
    if mimic.mode is Mode.CHEST and not mimic.dead:
        breath = 1.0 + 0.03 * math.sin(mimic.time * 1.7)
    bulge = math.sin(math.pi * (1.0 - mimic.gulp)) if mimic.gulp > 0.0 else 0.0
    breath *= (1.0 - 0.12 * mimic.crouch) * (1.0 - 0.25 * mimic.bounce) * (1.0 + 0.16 * bulge)
    wide = (1.0 + 0.18 * mimic.bounce) * (1.0 + 0.22 * bulge)
    shift = mimic.lunge * (side if mimic.mode is Mode.OPEN else mimic.heading)
    front, profile = mimic.scales()
    canvas = Canvas()
    base = -mimic.lift
    legs = _legs(mimic)
    if front >= abs(profile):
        f = Frame(max(front, MIN_SCALE) * wide, base, shift, breath)
        if mimic.legs <= 0.03 and not mimic.dead:
            canvas.ellipse(Vec2(shift, 0.6), CHEST_WIDTH * 0.55 * f.scale, 1.2, QColor(0, 0, 0, 50))
        _draw_legs(canvas, legs, near=False)
        _draw_front(canvas, mimic, f)
    else:
        scale = math.copysign(max(abs(profile), MIN_SCALE), profile)
        f = Frame(scale * wide, base, shift, breath)
        _draw_legs(canvas, legs, near=False)
        _draw_side(canvas, mimic, f)
    _draw_legs(canvas, legs, near=True)
    for coin in mimic.coins:
        _coin(canvas, coin)
    canvas.paint(painter, outline)
    painter.restore()
    if mimic.tongue_tip is not None:
        _draw_shot_tongue(painter, mimic, outline)
    if mimic.dust < DUST_TIME:
        _draw_dust(painter, mimic)
    if mimic.knife is not None:
        _draw_knife(painter, mimic.knife, outline)
    if mimic.chomp > 0.0:
        _draw_chomp(painter, mimic)


def _draw_shot_tongue(painter: QPainter, mimic: Mimic, outline: QColor | None) -> None:
    """Its long sticky tongue, out from its jaws to its tip."""
    tip = mimic.tongue_tip
    assert tip is not None
    mouth = mimic.mouth()
    length = mouth.distance_to(tip)
    if length < 1.0:
        return
    way = (tip - mouth).normalized()
    normal = Vec2(-way.y, way.x)
    count = max(2, int(length / 8.0))
    points = []
    for i in range(count + 1):
        k = i / count
        wave = math.sin(k * 9.0 - mimic.time * 30.0) * 1.4 * math.sin(math.pi * k)
        points.append(_qt(mouth.lerp(tip, k) + normal * wave))
    path = QPainterPath(points[0])
    for p in points[1:]:
        path.lineTo(p)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if outline is not None:
        painter.setPen(_pen(outline, 4.6))
        painter.drawPath(path)
    painter.setPen(_pen(TONGUE_DARK, 3.2))
    painter.drawPath(path)
    painter.setPen(_pen(TONGUE, 2.2))
    painter.drawPath(path)
    caught = mimic.caught
    if caught is not None:
        squeeze = mimic.squeeze(caught)
        size = 1.0 if squeeze is None else squeeze[2]
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for k, (rx, ry) in enumerate(((5.2, 2.2), (4.6, 2.0))):
            rx, ry = rx * size, ry * size
            at = _qt(tip + Vec2(0.0, (-2.5 + 4.0 * k) * size))
            if outline is not None:
                painter.setPen(_pen(outline, 3.6))
                painter.drawEllipse(at, rx, ry)
            painter.setPen(_pen(TONGUE_DARK, 2.4))
            painter.drawEllipse(at, rx, ry)
            painter.setPen(_pen(TONGUE, 1.5))
            painter.drawEllipse(at, rx, ry)
    else:
        painter.setPen(_pen(TONGUE_DARK, 0.5))
        painter.setBrush(TONGUE)
        painter.drawEllipse(_qt(tip), 2.4, 2.4)
    painter.restore()


def _draw_knife(painter: QPainter, knife: Knife, outline: QColor | None) -> None:
    """A rogue's dagger spinning through the air."""
    painter.save()
    painter.translate(_qt(knife.position))
    painter.rotate(math.degrees(knife.spin))
    parts = (
        (Vec2(-3.2, 0.0), Vec2(-0.8, 0.0), HILT, 1.6),
        (Vec2(-0.6, 0.0), Vec2(4.4, 0.0), STEEL, 1.4),
    )
    if outline is not None:
        painter.setPen(_pen(outline, 3.0))
        painter.drawLine(_qt(Vec2(-3.2, 0.0)), _qt(Vec2(4.4, 0.0)))
    for a, b, color, width in parts:
        painter.setPen(_pen(color, width))
        painter.drawLine(_qt(a), _qt(b))
    painter.setPen(_pen(HILT, 1.2))
    painter.drawLine(_qt(Vec2(-0.8, -1.6)), _qt(Vec2(-0.8, 1.6)))
    painter.restore()


def _draw_dust(painter: QPainter, mimic: Mimic) -> None:
    """Two little puffs kicked up either side as it lands a hop."""
    k = mimic.dust / DUST_TIME
    at = mimic.dust_at
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_alpha(DUST, 150 * (1.0 - k)))
    for side in (-1, 1):
        for j in range(2):
            out = CHEST_DEPTH / 2 + 2.0 + (10.0 + 5.0 * j) * smoothstep(k)
            center = at + Vec2(side * out, -1.2 - (2.0 + j) * k)
            r = 1.0 + (2.2 - 0.6 * j) * k
            painter.drawEllipse(_qt(center), r, r * 0.8)
    painter.restore()


def _coin(canvas: Canvas, coin: Coin) -> None:
    squash = abs(math.cos(coin.spin)) * 0.9 + 0.1
    at = Vec2(coin.x, -coin.y - 1.0)
    canvas.ellipse(at, 1.4 * squash, 1.4, BRASS, BRASS_DARK)


def _draw_chomp(painter: QPainter, mimic: Mimic) -> None:
    """A bite flash where its jaws shut on someone (and the word, for its ambush)."""
    k = mimic.chomp
    at = mimic.chomp_at
    big = mimic.chomp_word in ("CHOMP!", "GULP!")
    size = (9.0 if big else 6.0) * (1.2 - 0.4 * k)
    painter.save()
    painter.setOpacity(painter.opacity() * min(1.0, k * 1.6))
    painter.setPen(_pen(FLASH, 1.2))
    for i in range(8):
        angle = i * math.tau / 8 + 0.2
        inner = at + Vec2.from_angle(angle, size * 0.45)
        outer = at + Vec2.from_angle(angle, size * (1.0 if i % 2 else 0.7))
        painter.drawLine(_qt(inner), _qt(outer))
    if big:
        font = QFont()
        font.setBold(True)
        font.setPixelSize(9)
        path = QPainterPath()
        path.addText(QPointF(0.0, 0.0), font, mimic.chomp_word)
        rect = path.boundingRect()
        rise = (1.0 - k) * 8.0
        top = mimic.center() + mimic.up * (HEIGHT * 0.5 + 8.0 + rise)
        path.translate(top.x - rect.width() / 2, top.y)
        painter.setPen(_pen(ALERT_EDGE, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FLASH)
        painter.drawPath(path)
    painter.restore()


def draw_mimics(painter: QPainter, mimics, outline: QColor | None = None) -> None:
    for mimic in mimics:
        draw_mimic(painter, mimic, outline)


def draw_lure_alert(painter: QPainter, head: Vec2, radius: float, age: float) -> None:
    """The yellow "!" popping up over a lured adventurer's head."""
    pop = smoothstep(clamp(age / 0.14, 0.0, 1.0))
    settle = 1.0 + 0.45 * math.exp(-age * 9.0) * math.sin(clamp(age, 0.0, 1.0) * 22.0)
    scale = pop * settle
    if scale <= 0.01:
        return
    bob = 0.6 * math.sin(age * 6.0)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(13)
    path = QPainterPath()
    path.addText(QPointF(0.0, 0.0), font, "!")
    rect = path.boundingRect()
    painter.save()
    painter.translate(head.x, head.y - radius - 3.0 + bob)
    painter.scale(scale, scale)
    painter.translate(-rect.center().x(), -rect.bottom())
    painter.setPen(_pen(ALERT_EDGE, 2.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ALERT)
    painter.drawPath(path)
    painter.restore()
