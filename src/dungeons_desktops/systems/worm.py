"""The burrow worm: tunnels through windows and lunges out to snap up stickmen.

"Ground" is the inside of any window plus a band just past the screen edges.
The worm steers its head through ground with a wandering turn, never leaving it
on its own: at the edge of the ground it either turns back along it or leaps.

- Hunting: it tunnels toward the nearest standing stickman. Close enough, it
  lunges out at him (catching him ragdolls him), then has a cooldown. Further
  away, it hops into the ground under his feet to get closer.
- Meandering: with nobody to hunt it now and then leaps to another window or a
  screen border, or arcs out of its window and back in.

The body is a follow-the-leader chain of points behind the head. Leaps are
ballistic and end when the head enters ground again; the world's debris system
gets a spray where the worm breaks out and an impact where it lands.

Adventurers can only reach it while it's out of the ground. With `WORM_HP` gone it
dies there: whatever is still in the ground stays put and the rest flops over.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Rect, Vec2, clamp, wrap_angle
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.systems.actors import WORM_DAMAGE
from dungeons_desktops.systems.mortal import WORM_HP, Mortal

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman
    from dungeons_desktops.systems.world import SimWorld

GRAVITY = 900.0
SEGMENTS = 22
SPACING = 5.0
HEAD_RADIUS = 6.0
TAIL_RADIUS = 2.0
GROWTH_PER_MEAL = 0.04
MAX_SIZE = 2.0
SEGMENTS_PER_MEAL = 1
MAX_SEGMENTS = 60
BURROW_SPEED = 85.0
HUNT_SPEED = 125.0
TURN_RATE = 3.5
WANDER_NOISE = 4.0
LOOKAHEAD = 22.0
BORDER_DEPTH = 50.0
HUNT_RANGE = 520.0
STRIKE_RANGE = 230.0
STRIKE_AIM = 1.2
STRIKE_COOLDOWN = 2.0
CATCH_MARGIN = 7.0
BITE_SCALE = 1.4
"""The jaws' reach as a multiple of the head radius: bones inside it are bitten off."""
HOLE_SCALE = 1.6
"""Radius of the hole it leaves going in or out, as a multiple of the head radius."""
CATCH_SPEED = 380.0
MEANDER_WAIT = (5.0, 10.0)
HOP_WAIT = (1.5, 3.0)
MIN_LEAP = 80.0
MAX_LEAP = 650.0
OUT_OF_GROUND_GRACE = 0.15
ZERO = Vec2(0.0, 0.0)


class WormMode(Enum):
    BURROW = "burrow"
    LEAP = "leap"


class Worm(Mortal):
    max_hp = WORM_HP

    def __init__(self, world: SimWorld, head: Vec2, heading: float = 0.0) -> None:
        self.world = world
        back = Vec2.from_angle(heading, -SPACING)
        self.points = [head + back * i for i in range(SEGMENTS)]
        self.heading = heading
        self.mode = WormMode.BURROW
        self.velocity = ZERO
        self.turn = 0.0
        self.cooldown = 1.0
        self.hop_wait = world.random.uniform(*MEANDER_WAIT) * 0.5
        self.target: Stickman | None = None
        self.striking = False
        self.mouth = 0.0
        self.chomp = 0.0
        self.leaps = 0
        self.catches = 0
        self.size = 1.0
        """Thickness multiplier; grows with every meal."""
        self._out_time = 0.0
        self._left_ground = False
        self._leap_time = 0.0
        self._pinned: list[bool] = []
        self._prev: list[Vec2] = []

    @property
    def head(self) -> Vec2:
        return self.points[0]

    def radius(self, index: int) -> float:
        t = index / (len(self.points) - 1)
        return self.size * (TAIL_RADIUS + (HEAD_RADIUS - TAIL_RADIUS) * (1.0 - t) ** 0.6)

    def grow(self) -> None:
        """A meal: a little thicker and a couple of segments longer, up to a limit."""
        self.size = min(MAX_SIZE, self.size + GROWTH_PER_MEAL)
        for _ in range(min(SEGMENTS_PER_MEAL, MAX_SEGMENTS - len(self.points))):
            tail, before = self.points[-1], self.points[-2]
            direction = (tail - before).normalized()
            self.points.append(tail + direction * SPACING)

    # ----- ground --------------------------------------------------------------

    def buried(self, point: Vec2) -> bool:
        """Inside a window, or in the band just past the left, right or bottom edge.

        Above the top edge is open air: stickmen stand there on maximized windows.
        """
        world = self.world
        top = world.ceiling if world.ceiling is not None else 0.0
        within_sides = world.left <= point.x <= world.width
        if within_sides and point.y < top:
            return False
        if within_sides and point.y <= world.floor_y:
            return any(box.contains(point) for box in world.boxes)
        return self._outer_bounds().contains(point)

    def _outer_bounds(self) -> Rect:
        """The screen grown by the border band; nothing exists past it."""
        world = self.world
        top = (world.ceiling if world.ceiling is not None else 0.0) - BORDER_DEPTH
        return Rect(
            world.left - BORDER_DEPTH,
            top,
            world.width - world.left + 2 * BORDER_DEPTH,
            world.floor_y + BORDER_DEPTH - top,
        )

    def terrain_changed(self, change: TerrainChange, boxes: list[Rect]) -> None:
        """Ride along with the window the worm is burrowing in."""
        if self.mode is not WormMode.BURROW:
            return
        if change.shift is not None:
            self._shift(change.shift)
            return
        for old, delta in change.moves.items():
            new = change.new_index(old)
            if new is None:
                continue
            if boxes[new].moved(-delta.x, -delta.y).contains(self.head):
                self._shift(delta)
                return

    def _shift(self, delta: Vec2) -> None:
        self.points = [p + delta for p in self.points]

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.cooldown -= dt
        self.hop_wait -= dt
        self.chomp = max(0.0, self.chomp - dt)
        if self.mode is WormMode.BURROW:
            self._burrow(dt)
        else:
            self._leap(dt)
        self._follow()
        opening = (
            self.mode is WormMode.LEAP
            and self.striking
            and self.chomp == 0.0
            and self.target is not None
            and self.head.distance_to(self.target.center()) < 120.0
        )
        self.mouth += ((1.0 if opening else 0.0) - self.mouth) * min(1.0, dt * 14.0)

    def _choose_target(self) -> Stickman | None:
        head = self.head
        alive = [
            s for s in self.world.stickmen if s.prey and s.center().distance_to(head) <= HUNT_RANGE
        ]
        return min(alive, key=lambda s: s.center().distance_to(head), default=None)

    def _burrow(self, dt: float) -> None:
        head = self.head
        if not self.buried(head):
            self._out_time += dt
            if self._out_time > OUT_OF_GROUND_GRACE:
                self._fall()
            return
        self._out_time = 0.0

        rng = self.world.random
        self.turn = clamp(
            self.turn + rng.gauss(0.0, WANDER_NOISE) * dt - self.turn * 0.5 * dt, -1.5, 1.5
        )
        target = self.target = self._choose_target()
        if target is None:
            command = self.turn
        else:
            error = wrap_angle((target.center() - head).angle() - self.heading)
            command = clamp(error * 3.0, -TURN_RATE, TURN_RATE) * 0.8 + self.turn * 0.3

        ahead = head + Vec2.from_angle(self.heading, LOOKAHEAD)
        if not self.buried(ahead):
            if self._outer_bounds().contains(ahead) and self._try_leap(target):
                return
            left = self.buried(head + Vec2.from_angle(self.heading - 0.7, LOOKAHEAD))
            right = self.buried(head + Vec2.from_angle(self.heading + 0.7, LOOKAHEAD))
            if left and not right:
                command = -TURN_RATE
            elif right and not left:
                command = TURN_RATE
            else:
                command = TURN_RATE if self.turn >= 0.0 else -TURN_RATE

        self.heading = wrap_angle(self.heading + command * dt)
        speed = HUNT_SPEED if target is not None else BURROW_SPEED
        self.points[0] = head + Vec2.from_angle(self.heading, speed * dt)

    def _try_leap(self, target: Stickman | None) -> bool:
        """At the edge of the ground, heading out: strike, hop toward prey, or meander."""
        rng = self.world.random
        head = self.head
        if target is not None:
            aim = target.center()
            facing_it = abs(wrap_angle((aim - head).angle() - self.heading)) < STRIKE_AIM
            distance = head.distance_to(aim)
            if facing_it and self.cooldown <= 0.0 and distance <= STRIKE_RANGE:
                self._launch(aim, target.velocity, strike=True)
                return True
            if facing_it and self.hop_wait <= 0.0 and STRIKE_RANGE < distance <= MAX_LEAP:
                self._launch(target.contact() + Vec2(0.0, 18.0), ZERO, strike=False)
                self.hop_wait = rng.uniform(*HOP_WAIT)
                return True
            return False
        if self.hop_wait <= 0.0:
            destination = self._meander_destination()
            if destination is not None:
                self._launch(destination, ZERO, strike=False)
                self.hop_wait = rng.uniform(*MEANDER_WAIT)
                return True
        return False

    def _meander_destination(self) -> Vec2 | None:
        world, rng, head = self.world, self.world.random, self.head
        for _ in range(10):
            if world.boxes and rng.random() < 0.7:
                box = rng.choice(world.boxes)
                depth = rng.uniform(10.0, max(12.0, min(60.0, box.height - 5.0)))
                point = Vec2(rng.uniform(box.left + 5.0, box.right - 5.0), box.top + depth)
            else:
                side = rng.choice(("bottom", "left", "right"))
                if side == "bottom":
                    point = Vec2(rng.uniform(world.left, world.width), world.floor_y + 20.0)
                else:
                    top = world.ceiling if world.ceiling is not None else 0.0
                    x = world.left - 20.0 if side == "left" else world.width + 20.0
                    point = Vec2(x, rng.uniform(top, world.floor_y))
            distance = point.distance_to(head)
            ahead = (point - head).dot(Vec2.from_angle(self.heading)) > 0.0
            if MIN_LEAP <= distance <= MAX_LEAP and ahead and self.buried(point):
                return point
        return None

    def _launch(self, aim: Vec2, aim_velocity: Vec2, strike: bool) -> None:
        head = self.head
        flight = clamp(0.3 + head.distance_to(aim) / 650.0, 0.35, 1.1)
        aim = aim + aim_velocity * flight
        self.velocity = (aim - head - Vec2(0.0, 0.5 * GRAVITY * flight * flight)) / flight
        self.mode = WormMode.LEAP
        self.striking = strike
        self._left_ground = False
        self._leap_time = 0.0
        self.leaps += 1
        if strike:
            self.cooldown = STRIKE_COOLDOWN

    def _fall(self) -> None:
        """The ground vanished (its window closed): drop until it hits ground again."""
        self.mode = WormMode.LEAP
        self.velocity = Vec2.from_angle(self.heading, 40.0)
        self.striking = False
        self._left_ground = True
        self._leap_time = 0.0

    def _leap(self, dt: float) -> None:
        self._leap_time += dt
        self.velocity += Vec2(0.0, GRAVITY * dt)
        head = self.head + self.velocity * dt
        self.points[0] = head
        self.heading = self.velocity.angle()
        outer = self._outer_bounds()
        if not outer.contains(head):
            inset = 2.0
            self.points[0] = Vec2(
                clamp(head.x, outer.left + inset, outer.right - inset),
                clamp(head.y, outer.top + inset, outer.bottom - inset),
            )
            self.mode = WormMode.BURROW
            middle = Vec2(outer.x + outer.width / 2, outer.y + outer.height / 2)
            self.heading = (middle - head).angle()
            self.striking = False
            return
        grounded = self.buried(head)
        if not self._left_ground:
            if not grounded:
                self._left_ground = True
                self._break_out(head)
            elif self._leap_time > 0.6:
                self.mode = WormMode.BURROW
                return
        elif grounded:
            self._slam(head)
            self.mode = WormMode.BURROW
            self.striking = False
            self._out_time = 0.0
            return
        if self.chomp == 0.0:
            self._catch(head)

    def _break_out(self, head: Vec2) -> None:
        """A geyser of dirt along the leap, with a wider spray and dust around it."""
        debris, size = self.world.debris, self.size
        debris.burst(head, self.velocity, 18, 420.0, spread=0.25, chunks=3, scale=size)
        debris.burst(
            head, self.velocity, 16, 240.0, ring_radius=10.0, cracks=3, puffs=6, scale=size
        )
        debris.hole(head, self.radius(0) * HOLE_SCALE, self.world.boxes, self.world.bottom_border)

    def _slam(self, head: Vec2) -> None:
        """Landing: a crater ring with cracks, a shockwave, rocks and a dust cloud."""
        debris, size = self.world.debris, self.size
        splash = (-self.velocity).normalized() + Vec2(0.0, -0.6)
        debris.burst(
            head,
            splash,
            34,
            320.0,
            ring_radius=18.0,
            cracks=6,
            spread=1.3,
            chunks=7,
            puffs=10,
            scale=size,
        )
        debris.hole(head, self.radius(0) * HOLE_SCALE, self.world.boxes, self.world.bottom_border)

    def _catch(self, head: Vec2) -> None:
        for stickman in self.world.stickmen:
            if stickman.prey and stickman.hits(head, margin=CATCH_MARGIN * self.size):
                fling = self.velocity.normalized() * CATCH_SPEED + Vec2(0.0, -120.0)
                if not stickman.hurt_from(
                    self, WORM_DAMAGE, head, fling, "worm", "Eaten by the worm!", bleed=False
                ):
                    continue
                self._bite_off(stickman, fling)
                self.chomp = 0.35
                self.mouth = 0.0
                self.catches += 1
                self.grow()
                return

    def _bite_off(self, stickman: Stickman, fling: Vec2) -> None:
        """Remove every bone the worm's body overlaps, spraying blood from each."""
        gore = self.world.gore
        bitten = []
        for name, bone in stickman.transforms().items():
            middle = bone.start.lerp(bone.end, 0.5)
            if any(self._overlaps(point) for point in (bone.start, middle, bone.end)):
                bitten.append(name)
                gore.spray(middle, fling, 8, 260.0)
        stickman.severed.update(bitten)
        gore.spray(self.head, fling + Vec2(0.0, -200.0), 22, 340.0)

    def _overlaps(self, point: Vec2) -> bool:
        head = self.radius(0) * BITE_SCALE
        mouth = self.head + Vec2.from_angle(self.heading, head)
        if min(point.distance_to(self.head), point.distance_to(mouth)) < head:
            return True
        return any(
            point.distance_to(segment) < self.radius(i) + 1.0
            for i, segment in enumerate(self.points)
        )

    def _follow(self) -> None:
        points = self.points
        for i in range(1, len(points)):
            offset = points[i] - points[i - 1]
            length = offset.length()
            if length > 1e-6:
                points[i] = points[i - 1] + offset * (SPACING / length)

    # ----- death ---------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        """Go limp: segments still in the ground stay there, the rest keep their
        momentum, plus a shove near `point`."""
        self.dead = True
        self.down_time = 0.0
        self.striking = False
        self.target = None
        step = self.world.step
        self._pinned = [self.buried(p) for p in self.points]
        self._prev = [p - self.velocity * step for p in self.points]
        for i, p in enumerate(self.points):
            falloff = 1.0 - p.distance_to(point) / 40.0
            if falloff > 0.0:
                self._prev[i] -= push * (step * falloff)

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        self.mouth += (0.4 - self.mouth) * min(1.0, dt * 6.0)
        gravity = Vec2(0.0, GRAVITY * dt * dt)
        points, prev = self.points, self._prev
        for i, p in enumerate(points):
            if self._pinned[i]:
                continue
            moved = (p - prev[i]) * 0.98
            prev[i] = p
            points[i] = p + moved + gravity
        for _ in range(4):
            for i in range(1, len(points)):
                self._space(i - 1, i)
            for i, p in enumerate(points):
                if not self._pinned[i]:
                    points[i] = self._rest_on_ground(p, self.radius(i))
        if len(points) > 1:
            self.heading = (points[0] - points[1]).angle()

    def _space(self, a: int, b: int) -> None:
        points = self.points
        offset = points[b] - points[a]
        length = offset.length()
        if length < 1e-6:
            return
        error = offset * ((length - SPACING) / length)
        pinned_a, pinned_b = self._pinned[a], self._pinned[b]
        if pinned_a and pinned_b:
            return
        if pinned_a:
            points[b] -= error
        elif pinned_b:
            points[a] += error
        else:
            points[a] += error * 0.5
            points[b] -= error * 0.5

    def _rest_on_ground(self, point: Vec2, radius: float) -> Vec2:
        """Keep a loose segment out of the floor and on top of windows."""
        world = self.world
        if point.y > world.floor_y - radius:
            point = Vec2(point.x, world.floor_y - radius)
        for box in world.boxes:
            if box.left < point.x < box.right and box.top - radius < point.y < box.top + 12.0:
                point = Vec2(point.x, box.top - radius)
        return point
