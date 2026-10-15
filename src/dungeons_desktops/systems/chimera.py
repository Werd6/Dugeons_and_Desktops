"""The chimera: a lion in front and a goat behind, with a goat's head rising on a long
neck from the middle of its back and a serpent for a tail, arching up over its rump
with its head reared forward.

Three beasts in one body, each going its own way:

- The lion (`LionController`) moves it: it prowls the window tops, the floor and the
  windows' sides, stalks whoever it spots and pounces on him. Its body lies along
  whatever surface its feet are on, rolling round corners, and its legs trot planted
  on that surface (diagonal pairs swing together, the cycle advancing with distance
  so planted feet never slide).
- The goat (`GoatHead`) turns its head on its own to breathe fire at whoever is near,
  then waits out a cooldown.
- The serpent (`SnakeTail`) strikes at whoever comes close behind or (closer) in
  front, then recoils to rest.

With `CHIMERA_HP` gone it slumps where it stands and lies there until it fades.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep, wrap_angle
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.rig.ik import fabrik, two_bone_points
from dungeons_desktops.systems.chimera_goat import GOAT_ROOT, NECK_LENGTH, Fire, GoatHead
from dungeons_desktops.systems.chimera_lion import UPRIGHT, LionController, along
from dungeons_desktops.systems.chimera_snake import SnakeTail, Strike
from dungeons_desktops.systems.mortal import CHIMERA_HP, Mortal

if TYPE_CHECKING:
    from dungeons_desktops.navigation.planner import Anchor
    from dungeons_desktops.systems.world import SimWorld

BODY_LENGTH = 32.0
UPPER_LEG = 10.5
LOWER_LEG = 10.5
LEG_DROP = 2.0
"""Shoulders and hips sit this far below the spine line."""
STRIDE = 30.0
STANCE = 0.6
STEP_HEIGHT = 5.0
FULL_GAIT = 12.0
"""Speed at which its legs swing their full stride."""
CROUCH_SINK = 5.0
LANDING_SINK = 4.0

LION_HEAD = Vec2(10.5, 0.5)
"""Where the lion's head sits relative to the shoulder (x forward, y down)."""
MANE = Vec2(4.0, -2.5)
"""The middle of the mane, relative to the shoulder."""

SNAKE_PATH = (
    Vec2(-1.5, -2.5),
    Vec2(-8.0, -6.0),
    Vec2(-13.5, -14.0),
    Vec2(-15.5, -24.0),
    Vec2(-12.0, -33.0),
    Vec2(-3.0, -39.0),
    Vec2(9.0, -41.0),
    Vec2(21.0, -39.0),
    Vec2(30.0, -34.0),
    Vec2(35.0, -27.0),
)
"""The serpent's resting curve from its root at the rump to its head, relative to the
hip (x forward, y down): back off the rump, up over the goat's horns, and down to hang
its head in front of the goat's face."""
SNAKE_SEGMENTS = 20

FALL_GRAVITY = 600.0
LYING_HEIGHT = 7.0
"""Body height above the ground once it's down."""
ZERO = Vec2(0.0, 0.0)


def _catmull(points: tuple[Vec2, ...], samples: int) -> list[Vec2]:
    """A smooth curve through `points`, densely sampled."""
    out = []
    padded = [points[0], *points, points[-1]]
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for k in range(samples):
            t = k / samples
            t2, t3 = t * t, t * t * t
            out.append(
                (
                    p1 * 2.0
                    + (p2 - p0) * t
                    + (p0 * 2.0 - p1 * 5.0 + p2 * 4.0 - p3) * t2
                    + (p1 * 3.0 - p0 - p2 * 3.0 + p3) * t3
                )
                * 0.5
            )
    out.append(points[-1])
    return out


def _resample(path: list[Vec2], count: int) -> tuple[list[Vec2], float]:
    """`count` points spaced evenly along `path`, and that spacing."""
    lengths = [0.0]
    for a, b in zip(path, path[1:], strict=False):
        lengths.append(lengths[-1] + a.distance_to(b))
    total = lengths[-1]
    spacing = total / (count - 1)
    out, j = [], 0
    for i in range(count):
        target = spacing * i
        while j < len(lengths) - 2 and lengths[j + 1] < target:
            j += 1
        span = lengths[j + 1] - lengths[j]
        t = 0.0 if span < 1e-9 else (target - lengths[j]) / span
        out.append(path[j].lerp(path[j + 1], clamp(t, 0.0, 1.0)))
    return out, spacing


SNAKE_REST, SNAKE_SPACING = _resample(_catmull(SNAKE_PATH, 12), SNAKE_SEGMENTS)
SNAKE_LENGTH = SNAKE_SPACING * (SNAKE_SEGMENTS - 1)


@dataclass
class Leg:
    front: bool
    near: bool
    phase_offset: float
    foot: Vec2 = ZERO
    knee: Vec2 = ZERO
    root: Vec2 = ZERO
    lift: float = 0.0
    """0 planted flat on its surface, 1 tucked up in the air."""


@dataclass
class Mouth:
    """An idle head's jaw: it bares its teeth now and then."""

    jaw: float = 0.0
    open_for: float = 0.0
    wait: float = 0.0

    def update(self, dt: float, rng: random.Random, gap: tuple[float, float]) -> None:
        self.wait -= dt
        self.open_for -= dt
        if self.wait <= 0.0:
            self.open_for = rng.uniform(0.5, 1.1)
            self.wait = self.open_for + rng.uniform(*gap)
        target = 1.0 if self.open_for > 0.0 else 0.0
        self.jaw += (target - self.jaw) * min(1.0, dt * 10.0)


class Chimera(Mortal):
    max_hp = CHIMERA_HP
    linger = 4.0
    snake_length = SNAKE_LENGTH

    def __init__(self, world: SimWorld, anchor: Anchor, facing: int = 1) -> None:
        self.world = world
        self.facing = facing
        self.prowl = LionController(self, world, anchor, facing)
        self.look_up = self.prowl.frame_up
        """Its body's way up, eased after the lion's."""
        self.body = self.prowl.body
        self.velocity = ZERO
        self.phase = 0.0
        self.gait = 0.0
        self.clock = 0.0
        self._fx = random.Random(world.random.random())
        self.legs = [
            Leg(front=True, near=True, phase_offset=0.0),
            Leg(front=False, near=False, phase_offset=0.0),
            Leg(front=True, near=False, phase_offset=0.5),
            Leg(front=False, near=True, phase_offset=0.5),
        ]
        self.goat = GoatHead()
        self.snake = SnakeTail()
        self._lion_idle = Mouth(wait=self._fx.uniform(1.0, 4.0))
        self._goat_idle = Mouth(wait=self._fx.uniform(2.0, 6.0))
        self._snake_idle = Mouth(wait=self._fx.uniform(0.5, 3.0))
        self.lion_jaw = self.goat_jaw = self.snake_jaw = 0.0
        self.lion_head = self.body
        self.lion_angle = self.angle
        self.goat_head = self.body
        self.goat_angle = self.angle
        self.tail: list[Vec2] = []
        self.snake_angle = self.angle
        self._pose(1.0 / 60.0, snap=True)

    # ----- frame ---------------------------------------------------------------

    @property
    def up(self) -> Vec2:
        return self.look_up

    @property
    def forward(self) -> Vec2:
        return along(self.look_up) * self.facing

    @property
    def angle(self) -> float:
        return self.forward.angle()

    def local(self, v: Vec2) -> Vec2:
        """A body-relative offset (x forward, y down) in world space."""
        return self.forward * v.x - self.up * v.y

    @property
    def shoulder(self) -> Vec2:
        return self.body + self.forward * (BODY_LENGTH / 2)

    @property
    def hip(self) -> Vec2:
        return self.body - self.forward * (BODY_LENGTH / 2)

    @property
    def goat_root(self) -> Vec2:
        return self.body + self.local(GOAT_ROOT)

    @property
    def mane(self) -> Vec2:
        return self.shoulder + self.local(MANE)

    @property
    def snake_head(self) -> Vec2:
        return self.tail[-1]

    @property
    def goat_facing(self) -> int:
        return self.goat.facing

    @property
    def snake_facing(self) -> int:
        return self.snake.facing if self.snake.active else self.facing

    @property
    def support(self) -> Surface | None:
        return None if self.dead else self.prowl.support

    @property
    def walking(self) -> bool:
        return not self.dead and not self.prowl.airborne

    @property
    def flames(self) -> list:
        return self.goat.flames

    def center(self) -> Vec2:
        return self.body

    def parts(self) -> list[Vec2]:
        return [
            self.body,
            self.shoulder,
            self.hip,
            self.lion_head,
            self.mane,
            self.goat_root.lerp(self.goat_head, 0.5),
            self.goat_head,
            self.tail[len(self.tail) // 2],
            self.snake_head,
        ]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if _near_segment(point, self.hip, self.shoulder) <= 7.5 + margin:
            return True
        if point.distance_to(self.mane) <= 9.0 + margin:
            return True
        if point.distance_to(self.lion_head) <= 6.0 + margin:
            return True
        if _near_segment(point, self.goat_root, self.goat_head) <= 3.5 + margin:
            return True
        if point.distance_to(self.goat_head) <= 5.0 + margin:
            return True
        if point.distance_to(self.snake_head) <= 4.0 + margin:
            return True
        return any(p.distance_to(point) <= 3.0 + margin for p in self.tail[2::2])

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.clock += dt
        prowl = self.prowl
        prowl.update(dt)
        if prowl.heading != self.facing:
            self._turn(prowl.heading)
        self.phase += prowl.moved / STRIDE
        moving = clamp(prowl.speed / FULL_GAIT, 0.0, 1.0) if self.walking else 0.0
        self.gait += (moving - self.gait) * min(1.0, 6.0 * dt)
        self._lion_idle.update(dt, self._fx, (3.0, 7.0))
        self._goat_idle.update(dt, self._fx, (4.0, 9.0))
        self._snake_idle.update(dt, self._fx, (2.0, 5.0))
        self.snake.update(dt, self)
        self._pose(dt)
        self.goat.update(dt, self)
        self.snake.bite(self)

    def _turn(self, direction: int) -> None:
        """Swing round: the heads, tail and legs mirror across its middle with it."""
        mirror = self.forward
        center = self.body

        def flip(p: Vec2) -> Vec2:
            return p - mirror * (2.0 * (p - center).dot(mirror))

        def flip_angle(angle: float) -> float:
            way = Vec2.from_angle(angle)
            return (way - mirror * (2.0 * way.dot(mirror))).angle()

        self.facing = direction
        self.lion_head, self.goat_head = flip(self.lion_head), flip(self.goat_head)
        self.lion_angle = flip_angle(self.lion_angle)
        self.goat_angle = flip_angle(self.goat_angle)
        self.snake_angle = flip_angle(self.snake_angle)
        self.goat.reflect(mirror)
        self.tail = [flip(p) for p in self.tail]
        for leg in self.legs:
            leg.foot, leg.knee, leg.root = flip(leg.foot), flip(leg.knee), flip(leg.root)

    # ----- terrain ---------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        """The lion rides its window (or falls); the rest of it comes along."""
        if self.dead:
            return
        before = self.prowl.body
        self.prowl.terrain_changed(change)
        delta = self.prowl.body - before
        if delta.length() > 1e-6:
            self._shift(delta)

    def _shift(self, delta: Vec2) -> None:
        self.body += delta
        self.lion_head += delta
        self.goat_head += delta
        self.tail = [p + delta for p in self.tail]
        for leg in self.legs:
            leg.foot += delta
            leg.knee += delta
            leg.root += delta

    # ----- pose ------------------------------------------------------------------

    def _pose(self, dt: float, snap: bool = False) -> None:
        prowl = self.prowl
        walking = self.walking
        turn = 1.0 if snap else min(1.0, dt * (16.0 if walking else 7.0))
        target = prowl.frame_up
        self.look_up = self.look_up.rotated(
            wrap_angle(target.angle() - self.look_up.angle()) * turn
        )
        bob = math.sin(self.phase * math.tau * 2.0) * 0.8 * self.gait
        sink = CROUCH_SINK * prowl.crouch + LANDING_SINK * smoothstep(prowl.landing)
        self.body = prowl.body + (prowl.up * (bob - sink) if walking else ZERO)
        rate = 1.0 if snap else min(1.0, dt * 14.0)
        for leg in self.legs:
            root = (self.shoulder if leg.front else self.hip) + self.local(Vec2(0.0, LEG_DROP))
            if walking:
                foot = self._planted_foot(leg, root, prowl.position, prowl.up)
            else:
                foot = leg.foot.lerp(root + self.local(Vec2(-2.0, 14.0)), rate)
            bend = -self.facing if leg.front else self.facing
            leg.root, leg.knee, leg.foot = two_bone_points(root, UPPER_LEG, LOWER_LEG, foot, bend)
            if walking:
                height = (leg.foot - prowl.position).dot(prowl.up)
                leg.lift = clamp(height / 3.0, 0.0, 1.0)
            else:
                leg.lift += (1.0 - leg.lift) * rate
        self._pose_jaws(dt, snap)
        self._pose_heads(dt, snap)
        self._pose_snake(dt, snap)

    def _planted_foot(self, leg: Leg, root: Vec2, ground: Vec2, normal: Vec2) -> Vec2:
        """Its foot on the plane through `ground` facing `normal`: planted, or
        swinging forward a step above it."""
        p = (self.phase + leg.phase_offset) % 1.0
        span = STANCE * STRIDE
        if p < STANCE:
            ahead, lift = span * (0.5 - p / STANCE), 0.0
        else:
            u = (p - STANCE) / (1.0 - STANCE)
            ahead, lift = span * (-0.5 + smoothstep(u)), math.sin(math.pi * u) * STEP_HEIGHT
        base = root - normal * (root - ground).dot(normal)
        forward = along(normal) * self.facing
        return base + forward * (1.0 + ahead * self.gait) + normal * (lift * self.gait)

    def _pose_jaws(self, dt: float, snap: bool) -> None:
        rate = 1.0 if snap else min(1.0, dt * 14.0)
        lion = 1.0 if self.prowl.pouncing else self._lion_idle.jaw
        self.lion_jaw += (lion - self.lion_jaw) * rate
        goat_idle = self._goat_idle.jaw if self.goat.state is Fire.READY else 0.0
        self.goat_jaw = max(self.goat.jaw, goat_idle)
        snake_idle = self._snake_idle.jaw if self.snake.state is Strike.REST else 0.0
        self.snake_jaw = max(self.snake.jaw, snake_idle)

    def _pose_heads(self, dt: float, snap: bool) -> None:
        t = self.clock
        rate = 1.0 if snap else min(1.0, dt * 10.0)
        bob = math.sin(self.phase * math.tau * 2.0 + 0.8) * 0.7 * self.gait
        self.lion_head = self.shoulder + self.local(
            LION_HEAD + Vec2(0.0, bob - 1.2 * self.lion_jaw)
        )
        self.lion_angle = self.angle + self.facing * (0.32 - 0.25 * self.lion_jaw)

        neck = self.goat.neck(self) * NECK_LENGTH
        goat = self.goat_root + neck + self.local(Vec2(0.0, 0.6 * math.sin(t * 1.3)))
        aim = self.goat.aim if self.goat.aim is not None else self.forward
        self.goat_head = self.goat_head.lerp(goat, rate * 0.8)
        self.goat_angle += wrap_angle(aim.angle() - self.goat_angle) * rate

    def _rest_tail(self) -> list[Vec2]:
        """The serpent's resting curve where it is now, weaving, rearing back as it
        hisses."""
        t = self.clock
        root = self.hip + self.local(Vec2(-1.0, -1.0))
        hiss = self.snake_jaw if self.snake.state is Strike.REST else 0.0
        rest = []
        for i, point in enumerate(SNAKE_REST):
            u = i / (SNAKE_SEGMENTS - 1)
            weave = math.sin(t * 1.6 - i * 0.45) * 1.6 * u
            rear = Vec2(-3.0, -2.0) * (hiss * smoothstep(clamp((u - 0.55) / 0.45, 0.0, 1.0)))
            rest.append(root + self.local(point - SNAKE_REST[0] + Vec2(0.4 * weave, weave) + rear))
        return rest

    def _pose_snake(self, dt: float, snap: bool) -> None:
        """Each segment eases toward its place on the resting curve and the chain is
        pulled back to its segment spacing; mid-strike the chain bends from its root
        to put its head where the strike says."""
        rest = self._rest_tail()
        if snap or not self.tail:
            self.tail = rest
        else:
            goal = self.snake.head_goal(rest[-1])
            relax = min(1.0, (3.0 if goal is not None else 7.0) * dt)
            tail = self.tail
            tail[0] = rest[0]
            for i in range(1, SNAKE_SEGMENTS):
                pulled = tail[i].lerp(rest[i], relax)
                offset = pulled - tail[i - 1]
                length = offset.length()
                if length > 1e-6:
                    tail[i] = tail[i - 1] + offset * (SNAKE_SPACING / length)
            if goal is not None:
                self.tail = fabrik(tail, goal, iterations=6)
        heading = (self.tail[-1] - self.tail[-2]).angle()
        if not self.snake.active:
            heading -= self.facing * (0.7 - 0.4 * self.snake_jaw)
        rate = 1.0 if snap else min(1.0, dt * (25.0 if self.snake.active else 10.0))
        self.snake_angle += wrap_angle(heading - self.snake_angle) * rate

    # ----- death -----------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        """Stop everything and slump, knocked along a little by the killing blow."""
        self.dead = True
        self.down_time = 0.0
        self.velocity = push * 0.2 + self.prowl.velocity * 0.5
        self.prowl.loose()
        self.snake.reset()
        if self.goat.state is not Fire.COOLDOWN:
            self.goat.state, self.goat.target = Fire.COOLDOWN, None
        self.gait = 0.0

    def update_dead(self, dt: float) -> None:
        self.clock += dt
        self.down_time += dt
        self.goat.step_flames(dt, self)
        ground = self._ground_below(Vec2(self.body.x, self.body.y))
        rest = ground - LYING_HEIGHT
        down = self.body.y >= rest - 0.5 and self.velocity.y >= 0.0
        if down:
            if self.velocity.length() > 0.0:
                self.world.debris.burst(
                    Vec2(self.body.x, ground), Vec2(0.0, -1.0), 6, 120.0, spread=2.5, puffs=8
                )
            self.velocity = ZERO
            self.body = Vec2(self.body.x, rest)
        else:
            drag = math.exp(-1.5 * dt)
            self.velocity = Vec2(self.velocity.x * drag, self.velocity.y + FALL_GRAVITY * dt)
            self.body += self.velocity * dt
            if self.body.y > rest:
                self.body = Vec2(self.body.x, rest)
        slump = UPRIGHT.rotated(self.facing * 0.06)
        turn = wrap_angle(slump.angle() - self.look_up.angle()) * min(1.0, dt * 4.0)
        self.look_up = self.look_up.rotated(turn)
        self._pose_limp(dt, ground)

    def _ground_below(self, point: Vec2) -> float:
        """The floor or the top of the highest window under `point`."""
        tops = [
            box.top
            for box in self.world.boxes
            if box.left <= point.x <= box.right and box.top >= point.y - 2.0
        ]
        return min([self.world.floor_y, *tops])

    def _pose_limp(self, dt: float, ground: float) -> None:
        """Legs splayed, the heads sagging to the ground, the serpent laid out behind."""
        rate = min(1.0, dt * 6.0)
        side = 1.0 if self.forward.x >= 0.0 else -1.0
        for leg in self.legs:
            root = (self.shoulder if leg.front else self.hip) + self.local(Vec2(0.0, LEG_DROP))
            out = (1.0 if leg.front else -1.0) * side
            target = Vec2(root.x + out * 13.0, ground)
            bend = -self.facing if leg.front else self.facing
            foot = leg.foot.lerp(target, rate)
            leg.root, leg.knee, leg.foot = two_bone_points(root, UPPER_LEG, LOWER_LEG, foot, bend)
            leg.lift += (0.0 - leg.lift) * rate
        lion = Vec2(self.shoulder.x + side * 12.0, ground - 4.0)
        self.lion_head = self.lion_head.lerp(lion, rate)
        sag = (0.0 if side > 0 else math.pi) + side * 0.25
        self.lion_angle += wrap_angle(sag - self.lion_angle) * rate
        goat = Vec2(self.goat_root.x - side * 6.0, ground - 15.0)
        self.goat_head = self.goat_head.lerp(goat, rate * 0.7)
        self.goat_angle += wrap_angle(sag - self.goat_angle) * rate
        self.goat.aim = Vec2.from_angle(self.goat_angle)
        self.goat.facing = self.facing
        self.lion_jaw += (0.3 - self.lion_jaw) * rate
        self.goat_jaw += (0.3 - self.goat_jaw) * rate
        self.snake_jaw += (0.3 - self.snake_jaw) * rate
        tail = self.tail
        tail[0] = self.hip + self.local(Vec2(-1.0, -1.0))
        for i in range(1, len(tail)):
            x = tail[0].x - side * SNAKE_SPACING * i * 0.9
            lie = Vec2(x, self._ground_below(Vec2(x, tail[0].y)) - 2.0)
            pulled = tail[i].lerp(lie, rate * 0.6)
            offset = pulled - tail[i - 1]
            length = offset.length()
            if length > 1e-6:
                tail[i] = tail[i - 1] + offset * (SNAKE_SPACING / length)
        heading = (tail[-1] - tail[-2]).angle()
        self.snake_angle += wrap_angle(heading - self.snake_angle) * rate


def _near_segment(point: Vec2, a: Vec2, b: Vec2) -> float:
    ab = b - a
    length = ab.dot(ab)
    if length < 1e-9:
        return point.distance_to(a)
    t = clamp((point - a).dot(ab) / length, 0.0, 1.0)
    return point.distance_to(a + ab * t)
