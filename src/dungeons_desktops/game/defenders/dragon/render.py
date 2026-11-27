"""Dragon model renderer and palette shared with the smaller drakes."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.defenders.dragon.actor import ANCIENT_BULK, Dragon, Leg
from dungeons_desktops.game.defenders.dragon.actor import SCALE as DRAGON_SCALE
from dungeons_desktops.game.effects.render import draw_breath
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.effects import draw_fire
from dungeons_desktops.render.primitives import qt, world_pen
from dungeons_desktops.render.wings import draw_wing, folded_wing
from dungeons_desktops.rig.ik import two_bone_points

OUTLINE = QColor(20, 20, 26, 200)
WORM_MOUTH = QColor(70, 16, 24)
WORM_TOOTH = QColor(255, 255, 255)
DRAGON_SKIN = QColor(176, 46, 40)
DRAGON_FAR = QColor(118, 30, 28)
DRAGON_BELLY = QColor(232, 170, 92)
DRAGON_WING = QColor(204, 82, 58, 215)
DRAGON_WING_FAR = QColor(140, 46, 36, 200)
DRAGON_HORN = QColor(240, 226, 192)
DRAGON_TALON = QColor(58, 34, 30)
DRAGON_EYE = QColor(255, 220, 60)
DRAGON_WING_SCALE = 2.0
ANCIENT_GOLD = QColor(255, 190, 48)
ANCIENT_HORN = 1.55
"""How much larger Ancient Wyrm horns and head frills grow vs a normal dragon."""
CATACLYSM_CORE = QColor(255, 246, 180, 210)


@dataclass(frozen=True)
class DragonPalette:
    skin: QColor
    far: QColor
    belly: QColor
    wing: QColor
    wing_far: QColor
    horn: QColor
    talon: QColor
    eye: QColor
    wing_bone: QColor | None = None


DRAGON_PALETTES = {
    "red": DragonPalette(
        DRAGON_SKIN,
        DRAGON_FAR,
        DRAGON_BELLY,
        DRAGON_WING,
        DRAGON_WING_FAR,
        DRAGON_HORN,
        DRAGON_TALON,
        DRAGON_EYE,
    ),
    "green": DragonPalette(
        QColor(44, 132, 62),
        QColor(26, 86, 40),
        QColor(200, 216, 96),
        QColor(78, 164, 84, 215),
        QColor(34, 100, 48, 200),
        QColor(226, 218, 168),
        QColor(30, 46, 28),
        QColor(255, 226, 60),
    ),
    "blue": DragonPalette(
        QColor(36, 82, 182),
        QColor(22, 50, 120),
        QColor(178, 210, 244),
        QColor(66, 122, 216, 215),
        QColor(30, 62, 142, 200),
        QColor(236, 240, 250),
        QColor(24, 28, 52),
        QColor(196, 246, 255),
    ),
    "black": DragonPalette(
        QColor(46, 42, 54),
        QColor(24, 22, 30),
        QColor(178, 168, 142),
        QColor(86, 72, 104, 215),
        QColor(44, 36, 56, 200),
        QColor(156, 142, 116),
        QColor(12, 10, 14),
        QColor(190, 255, 90),
    ),
    "white": DragonPalette(
        QColor(232, 238, 246),
        QColor(168, 182, 204),
        QColor(204, 222, 240),
        QColor(216, 232, 248, 215),
        QColor(158, 176, 204, 200),
        QColor(178, 196, 222),
        QColor(88, 98, 120),
        QColor(96, 196, 255),
    ),
}
"""Wing size relative to the body; the folded wing grows with it."""


@chromatic_appearance
def draw_dragon(
    painter: QPainter,
    dragon: Dragon,
    outline: QColor | None = None,
    palette: DragonPalette | None = None,
    details: Callable[[], None] | None = None,
) -> None:
    """Far wing and legs, tail, body, neck and head, near legs, near wing, then fire."""
    legendary = getattr(dragon, "legendary", False)
    bulk = ANCIENT_BULK if legendary else 1.0
    s = DRAGON_SCALE * dragon.size
    p = palette or DRAGON_PALETTES.get(dragon.variant, DRAGON_PALETTES["red"])
    horn = ANCIENT_GOLD if legendary else p.horn
    near = [_dragon_limb(dragon, leg, bulk=bulk) for leg in dragon.legs if leg.near]
    far = [_dragon_limb(dragon, leg, bulk=bulk) for leg in dragon.legs if not leg.near]
    tail = dragon.tail
    widths = [
        (7.0 * s * (1.0 - i / len(tail)) + 1.2 * s) * bulk for i in range(len(tail))
    ]
    hip, shoulder = dragon.hip, dragon.shoulder
    body_w = 13.0 * s * bulk
    neck_w = 6.5 * s * bulk

    def strokes(color: QColor, grow: float) -> None:
        for limb in far + near:
            limb.stroke(painter, color, grow)
        for i in range(len(tail) - 1):
            painter.setPen(world_pen(color, widths[i] + grow))
            painter.drawLine(qt(tail[i]), qt(tail[i + 1]))
        painter.setPen(world_pen(color, body_w + grow))
        painter.drawLine(qt(hip), qt(shoulder))
        painter.setPen(world_pen(color, neck_w + grow))
        painter.drawLine(qt(dragon.neck_base), qt(dragon.head))

    _draw_wing(painter, dragon, near=False, palette=p)
    if outline is not None:
        strokes(outline, 2.0)
    for leg in far:
        _draw_dragon_leg(painter, leg, p.far, s, p.talon)
    for i in range(len(tail) - 1):
        painter.setPen(world_pen(p.skin, widths[i]))
        painter.drawLine(qt(tail[i]), qt(tail[i + 1]))
    tip, before = tail[-1], tail[-2]
    along = (tip - before).normalized()
    across = Vec2(-along.y, along.x) * (4.5 * s * bulk)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(horn if legendary else p.skin)
    painter.drawPolygon([qt(tip + across), qt(tip + along * (9.0 * s)), qt(tip - across)])

    painter.setPen(world_pen(p.skin, body_w))
    painter.drawLine(qt(hip), qt(shoulder))
    belly = dragon.local(Vec2(0.0, 3.5 * s * bulk))
    painter.setPen(world_pen(p.belly, 5.0 * s * bulk))
    painter.drawLine(qt(hip + belly + dragon.forward * 3.0), qt(shoulder + belly))
    painter.setPen(world_pen(horn if legendary else p.far, 1.35 * s * bulk))
    for k in range(1, 6):
        spine = hip.lerp(shoulder, k / 6.0) + dragon.local(Vec2(0.0, -6.0 * s * bulk))
        painter.drawLine(
            qt(spine),
            qt(spine + dragon.local(Vec2(-1.5, -2.8 - 0.6 * bulk) * s)),
        )

    painter.setPen(world_pen(p.skin, neck_w))
    painter.drawLine(qt(dragon.neck_base), qt(dragon.head))
    _draw_dragon_head(painter, dragon, s, palette=p)

    for leg in near:
        _draw_dragon_leg(painter, leg, p.skin, s, p.talon)
    if details is not None:
        details()
    _draw_wing(painter, dragon, near=True, palette=p)
    draw_flames(painter, dragon)


@dataclass
class DragonLimb:
    joints: list[Vec2]
    widths: list[float]
    toes: list[tuple[Vec2, Vec2, Vec2]]
    """Base, tip and talon direction, dew claw first, nearest toe last."""
    muscle: float
    """Width of the thigh or upper arm where it meets the body, tapering to the knee."""
    scale: float = DRAGON_SCALE

    def stroke(self, painter: QPainter, color: QColor, grow: float) -> None:
        root, knee = self.joints[0], self.joints[1]
        along = knee - root
        if along.length() > 1e-6:
            side = along.normalized().rotated(math.pi / 2)
            steps = [k / 6 for k in range(7)]
            half = [
                (
                    self.widths[0]
                    + (self.muscle - self.widths[0])
                    * (1.0 - smoothstep(clamp((u - 0.25) / 0.75, 0.0, 1.0)))
                    + grow
                )
                / 2
                for u in steps
            ]
            outline = [root + along * u + side * h for u, h in zip(steps, half, strict=True)]
            outline += [
                root + along * u - side * h
                for u, h in reversed(list(zip(steps, half, strict=True)))
            ]
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPolygon([qt(p) for p in outline])
            painter.drawEllipse(qt(root), half[0], half[0])
            painter.restore()
        for i, width in enumerate(self.widths):
            painter.setPen(world_pen(color, width + grow))
            painter.drawLine(qt(self.joints[i]), qt(self.joints[i + 1]))
        painter.setPen(world_pen(color, 1.4 * self.scale + grow * 0.6))
        for base, tip, _ in self.toes:
            painter.drawLine(qt(base), qt(tip))


def _blend_angle(a: float, b: float, t: float) -> float:
    return a + math.remainder(b - a, math.tau) * t


def _dragon_limb(dragon: Dragon, leg: Leg, *, bulk: float = 1.0) -> DragonLimb:
    """Hip or shoulder, knee or elbow, hock or wrist, ankle, all ending on the sim's foot
    point. Hind legs stand digitigrade on a raked metatarsus with the hock kicked back;
    front legs bring the elbow back over a short sloped wrist. The toes lie flat with
    the outline resting on the surface and curl under as the foot lifts."""
    s = DRAGON_SCALE * dragon.size
    facing = dragon.facing
    lift = smoothstep(leg.lift)
    root, foot = leg.root, leg.foot
    thigh, shin, ankle_bone = (8.5, 9.0, 6.0) if not leg.front else (9.0, 9.0, 3.5)
    rake = 0.5 if not leg.front else 0.3

    up = Vec2(0.0, -1.0)
    reach = root - foot
    rise = up.rotated(-facing * rake).angle()
    if reach.length() > 1e-6:
        rise = _blend_angle(rise, reach.angle(), lift)
    rise_dir = Vec2.from_angle(rise)
    hang = (-rise_dir).angle() - facing * 0.6
    toe_angle = _blend_angle(0.0 if facing > 0 else math.pi, hang, lift)
    toe = Vec2.from_angle(toe_angle)
    normal = toe.rotated(-facing * math.pi / 2)

    ankle = foot + normal * (2.8 * s) - toe * (0.6 * s)
    hock = ankle + rise_dir * (ankle_bone * s)
    stretch = max(1.0, hock.distance_to(root) / (0.97 * (thigh + shin) * s))
    bend = -facing if leg.front else facing
    _, knee, hock = two_bone_points(root, thigh * s * stretch, shin * s * stretch, hock, bend)

    size = (0.85 if leg.front else 1.0) * s
    base = foot + normal * (1.3 * s)
    toes = []
    for spread, length in ((-0.42, 3.0), (-0.2, 3.7), (0.0, 4.5)):
        reach_dir = toe.rotated(facing * spread * (1.0 - 0.6 * lift))
        tip = base + reach_dir * (length * size * (1.0 - 0.35 * lift))
        toes.append((base, tip, reach_dir.rotated(facing * (0.4 + 0.8 * lift))))
    dew = (-toe).rotated(facing * (0.6 - 1.1 * lift))
    dew_tip = base + dew * (1.9 * size)
    toes.insert(0, (base, dew_tip, dew.rotated(-facing * 0.8)))
    widths = (4.8, 4.4, 3.6) if not leg.front else (4.4, 4.2, 3.6)
    muscle = 8.2 if not leg.front else 7.0
    return DragonLimb(
        [root, knee, hock, ankle],
        [w * s * bulk for w in widths],
        toes,
        muscle * s * bulk,
        s,
    )


def _draw_dragon_leg(
    painter: QPainter, limb: DragonLimb, color: QColor, s: float, talon: QColor
) -> None:
    limb.stroke(painter, color, 0.0)
    shade = color.darker(125)
    for i, (base, tip, _) in enumerate(limb.toes):
        painter.setPen(world_pen(shade if i < 3 else color, 1.4 * s))
        painter.drawLine(qt(base), qt(tip))
    painter.setPen(world_pen(talon, 1.1 * s))
    for _, tip, hook in limb.toes:
        painter.drawLine(qt(tip), qt(tip + hook * (1.5 * s)))


def _draw_dragon_head(
    painter: QPainter, dragon: Dragon, s: float, palette: DragonPalette | None = None
) -> None:
    head, angle = dragon.head, dragon.head_angle
    forward = Vec2.from_angle(angle)
    up = forward.rotated(-dragon.facing * math.pi / 2)
    jaw = dragon.jaw
    p = palette or DRAGON_PALETTES.get(dragon.variant, DRAGON_PALETTES["red"])

    def at(x: float, y: float) -> Vec2:
        return head + forward * (x * s) - up * (y * s)

    legendary = getattr(dragon, "legendary", False)
    horn = ANCIENT_GOLD if legendary else p.horn
    horn_grow = ANCIENT_HORN if legendary else 1.0
    variant = dragon.variant
    if variant == "green":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(horn if legendary else p.far)
        for x in (-1.0, -3.5):
            base = at(x - 0.8, -3.8)
            tip = at(x - 2.6, -6.3)
            tip = base + (tip - base) * horn_grow
            painter.drawPolygon([qt(at(x, -4.0)), qt(tip), qt(at(x - 1.6, -3.6))])
    elif variant not in ("blue", "black"):
        painter.setPen(world_pen(horn, 1.6 * s * (0.7 + 0.3 * horn_grow)))
        for base, tip in (
            (at(-2.0, -3.5), at(-8.0, -8.0)),
            (at(0.0, -4.0), at(-4.5, -9.0)),
        ):
            tip = base + (tip - base) * horn_grow
            painter.drawLine(qt(base), qt(tip))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(p.skin)
    upper = [at(-4.5, -4.0), at(3.0, -4.5), at(10.0, -1.5), at(10.0, 0.5), at(-4.5, 1.5)]
    open_by = 0.55 * jaw * dragon.facing
    hinge = at(-2.5, 1.0)

    def jaw_point(x: float, y: float) -> Vec2:
        return hinge + (at(x, y) - hinge).rotated(open_by)

    lower = [jaw_point(-4.0, 1.0), jaw_point(9.0, 1.0), jaw_point(8.0, 3.0), jaw_point(-3.0, 4.5)]
    if jaw > 0.05:
        painter.setBrush(WORM_MOUTH)
        painter.drawPolygon([qt(hinge), qt(at(9.0, 0.5)), qt(jaw_point(8.5, 1.5))])
        painter.setBrush(WORM_TOOTH)
        for x in (3.0, 6.0, 8.5):
            painter.drawPolygon([qt(at(x - 1.0, 0.5)), qt(at(x + 0.6, 0.5)), qt(at(x, 2.0))])
        # Lower-jaw fangs pointing up into the mouth.
        for x in (3.5, 6.2, 8.2):
            painter.drawPolygon(
                [
                    qt(jaw_point(x - 0.85, 1.15)),
                    qt(jaw_point(x + 0.55, 1.15)),
                    qt(jaw_point(x - 0.1, -0.55)),
                ]
            )
    painter.setBrush(p.skin)
    painter.drawPolygon([qt(point) for point in upper])
    painter.setBrush(p.belly)
    painter.drawPolygon([qt(point) for point in lower])
    painter.setBrush(p.eye)
    painter.drawEllipse(qt(at(1.5, -1.8)), 1.3 * s, 1.0 * s)
    painter.setBrush(OUTLINE)
    painter.drawEllipse(qt(at(9.0, -0.8)), 0.6 * s, 0.6 * s)
    if variant == "green":
        _draw_horn(
            painter, [at(6.6, -2.4), at(8.4, -7.6), at(10.0, -1.4)], horn, s, grow=horn_grow
        )
    elif variant == "blue":
        _draw_horn(
            painter,
            [at(-0.6, -3.6), at(5.0, -13.0), at(3.0, -4.2)],
            horn,
            s,
            ridges=3,
            grow=horn_grow,
        )
    elif variant == "black":
        _draw_ram_horn(painter, at, horn, s, grow=horn_grow)


def _draw_horn(
    painter: QPainter,
    points: list[Vec2],
    horn: QColor,
    s: float,
    ridges: int = 0,
    grow: float = 1.0,
) -> None:
    """A tapering horn: `points` are base back, tip, base front."""
    back, tip, front = points
    root = back.lerp(front, 0.5)
    tip = root + (tip - root) * grow
    back = root + (back - root) * (0.85 + 0.15 * grow)
    front = root + (front - root) * (0.85 + 0.15 * grow)
    painter.setPen(world_pen(horn.darker(150), 0.5 * s * grow))
    painter.setBrush(horn)
    painter.drawPolygon([qt(back), qt(tip), qt(front)])
    painter.setPen(world_pen(horn.darker(135), 0.45 * s * grow))
    for k in range(1, ridges + 1):
        t = k / (ridges + 1)
        painter.drawLine(qt(back.lerp(tip, t)), qt(front.lerp(tip, t + 0.08)))


def _draw_ram_horn(
    painter: QPainter,
    at: Callable[[float, float], Vec2],
    horn: QColor,
    s: float,
    grow: float = 1.0,
) -> None:
    """A ram's horn curling back, down and round on the side of the head."""
    steps = 22
    # Plant the thick root on the brow; grow expands the curl from there instead of
    # lifting the whole spiral off the skull.
    root_x, root_y = -3.4, -3.2
    root_radius = 4.6 * grow
    cx, cy = root_x, root_y + root_radius
    points, widths = [], []
    for k in range(steps + 1):
        t = k / steps
        turn = -math.pi / 2 - t * 1.75 * math.pi
        radius = (4.6 - 3.2 * t) * grow
        points.append(
            at(cx + radius * math.cos(turn) - 0.6 * t * grow, cy + radius * math.sin(turn))
        )
        widths.append((2.6 - 1.7 * t) * s * (0.85 + 0.15 * grow))
    for color, outline in ((horn.darker(170), 0.9 * s * grow), (horn, 0.0)):
        for k in range(steps):
            painter.setPen(world_pen(color, widths[k] + outline))
            painter.drawLine(qt(points[k]), qt(points[k + 1]))
    painter.setPen(world_pen(horn.darker(140), 0.4 * s))
    for k in range(2, steps - 2, 3):
        across = (points[k + 1] - points[k]).normalized().rotated(math.pi / 2) * (widths[k] * 0.5)
        painter.drawLine(qt(points[k] - across), qt(points[k] + across))


def _draw_wing(
    painter: QPainter, dragon: Dragon, near: bool, palette: DragonPalette | None = None
) -> None:
    s = DRAGON_SCALE * dragon.size * DRAGON_WING_SCALE * (1.0 if near else 0.85)
    p = palette or DRAGON_PALETTES.get(dragon.variant, DRAGON_PALETTES["red"])
    root = dragon.shoulder + dragon.local(
        Vec2(-1.0 if near else 1.0, -5.0) * DRAGON_SCALE * dragon.size
    )

    if dragon.flying:
        # The wing beats up and down around the body's long axis, so seen from the
        # side its span shrinks to a sliver as it swings out toward the viewer.
        beat = dragon.flap + (0.0 if near else 0.25)
        arm = 0.35 + 1.05 * math.cos(beat)
        hand = 0.35 + 1.25 * math.cos(beat - 0.9)
        sweep = -2.0 * math.sin(beat)
        elbow = root + dragon.local(Vec2(1.0 + sweep, -16.0 * math.sin(arm)) * s)
        tip = elbow + dragon.local(Vec2(-12.0 + 2.0 * sweep, -24.0 * math.sin(hand)) * s)
        trailing = elbow + dragon.local(Vec2(-21.0, -13.0 * math.sin(hand)) * s)
        back = root + dragon.local(Vec2(-17.0, 2.0) * s)
    else:
        root, elbow, tip, trailing, back = folded_wing(root, dragon.local, s)

    draw_wing(
        painter,
        (root, elbow, tip, trailing, back),
        s,
        p.wing if near else p.wing_far,
        p.far if near else OUTLINE,
        (p.wing_bone or p.skin) if near else p.far,
        p.far,
    )


def draw_flames(painter: QPainter, dragon: Dragon) -> None:
    if dragon.variant != "red":
        draw_breath(painter, dragon)
    else:
        draw_fire(painter, dragon.flames)
    if getattr(dragon, "legendary", False):
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(CATACLYSM_CORE)
        for flame in dragon.flames:
            if flame.age < 0.3:
                painter.drawEllipse(qt(flame.position), 1.8 * flame.size, 1.8 * flame.size)
        painter.restore()
