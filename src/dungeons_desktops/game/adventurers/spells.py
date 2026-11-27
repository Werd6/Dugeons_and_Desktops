"""The adventurers' ranged attacks and blessings: magic missiles, arrows, heal pulses.

Missiles and arrows that reach a monster are reported by `update` as `SpellHit`s;
the world turns each one into damage.

- A magic missile is three purple darts weaving along a sine wave about the line to
  their target, a third of a wave apart, converging as they arrive. They home in on
  the monster they were cast at and burst into sparks there, hitting it if it's
  still there to hit.
- A sorcerer's fire spark uses the same homing flight and hit handling as a
  magic missile, with one straight, fiery dart.
- Arrows fly ballistic and stick where they land, or break on (and hit) a monster.
- A heal pulse is a white ring spreading out from a cleric.
- A druid's vine lashes up out of the ground at his feet and snakes straight to its
  target, through windows and earth alike (it can reach a burrowing worm), hits it
  as it gets there, then withers away.

A thrall's missiles, arrows and vines are `hostile`: they go after the free
adventurers (found with `update`'s `locate_prey` and `prey_at`) instead of monsters.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from random import Random

from dungeons_desktops.core.geometry import Rect, Vec2

MISSILE_SPEED = 260.0
MISSILE_DARTS = 3
MISSILE_WAVES = 1.5
"""Full sine waves along the flight."""
MISSILE_SWAY = 16.0
"""Peak sideways distance of the darts from the line to the target."""
DART_TRAIL = 6
ARROW_GRAVITY = 420.0
ARROW_STUCK_TIME = 2.5
ARROW_FLIGHT_LIMIT = 4.0
"""Seconds before an arrow that never landed (off the screen) is dropped."""
PULSE_TIME = 0.7
VINE_GROW = 0.28
"""Seconds for a vine to reach its target (it hits then)."""
VINE_TIME = 0.9
VINE_WAVES = 1.5
VINE_SWAY = 5.0
SPARK_LIFE = 0.45

Locate = Callable[[object], Vec2 | None]
"""Where a monster is now, or None once it's gone."""
MonsterAt = Callable[[Vec2], object | None]
"""The monster covering a point, if any."""
Grip = Callable[[object, Vec2], Vec2 | None]
"""The part of a monster (even underground) nearest a point, or None once it's gone."""


def _no_one(_: object) -> None:
    return None


@dataclass
class SpellHit:
    monster: object
    point: Vec2
    velocity: Vec2
    """Which way the missile or arrow was going, for the knock back."""
    hostile: bool = False
    """Cast by a thrall: `monster` is the adventurer it hit."""
    owner: object = None
    """Who cast, shot or called it."""
    kind: str = "magic"
    """The projectile effect, used for impact behavior such as life drain."""


@dataclass
class Missile:
    origin: Vec2
    target: Vec2
    monster: object
    hostile: bool = False
    age: float = 0.0
    darts: list[list[Vec2]] = field(default_factory=list)
    """Each dart's recent positions, newest last."""
    owner: object = None
    kind: str = "magic"

    @property
    def flight(self) -> float:
        if self.kind == "life_drain":
            return max(0.16, self.origin.distance_to(self.target) / 680.0)
        return max(0.25, self.origin.distance_to(self.target) / MISSILE_SPEED)

    def dart(self, index: int, t: float) -> Vec2:
        line = self.target - self.origin
        if self.kind == "fire":
            return self.origin + line * t
        side = line.normalized().rotated(math.pi / 2)
        if self.kind == "life_drain":
            wave = math.sin(math.tau * 2.7 * t + math.sin(t * 31.0) * 1.3)
            fork = 0.45 * math.sin(math.tau * 7.1 * t + 0.8)
            sway = 13.0 * math.sin(math.pi * t) * (wave + fork)
            return self.origin + line * t + side * sway
        phase = 2.0 * math.pi * index / MISSILE_DARTS
        wave = math.sin(2.0 * math.pi * MISSILE_WAVES * t + phase)
        return self.origin + line * t + side * (MISSILE_SWAY * math.sin(math.pi * t) * wave)


@dataclass
class Arrow:
    position: Vec2
    velocity: Vec2
    hostile: bool = False
    age: float = 0.0
    stuck: float | None = None
    """Seconds since it stuck, or None while flying."""
    heading: Vec2 = Vec2(1.0, 0.0)
    """Which way it points once stuck."""
    owner: object = None


@dataclass
class Vine:
    root: Vec2
    target: Vec2
    monster: object
    phase: float
    hostile: bool = False
    age: float = 0.0
    struck: bool = False
    owner: object = None

    @property
    def reach(self) -> float:
        """How much of the way to the target it has grown (0..1, back to 0 as it withers)."""
        if self.age < VINE_GROW:
            return math.sin(0.5 * math.pi * self.age / VINE_GROW)
        wither = (self.age - VINE_GROW) / (VINE_TIME - VINE_GROW)
        return 1.0 - max(0.0, wither - 0.5) * 2.0

    def path(self, count: int = 14) -> list[Vec2]:
        """Points from the root to the tip, swaying to either side of the straight line."""
        line = self.target - self.root
        side = line.normalized().rotated(math.pi / 2)
        reach = self.reach
        points = []
        for i in range(count + 1):
            t = reach * i / count
            wave = math.sin(2.0 * math.pi * VINE_WAVES * t + self.phase + 3.0 * self.age)
            points.append(self.root + line * t + side * (VINE_SWAY * math.sin(math.pi * t) * wave))
        return points


@dataclass
class Pulse:
    center: Vec2
    radius: float
    age: float = 0.0


@dataclass
class Spark:
    position: Vec2
    velocity: Vec2
    color: str
    age: float = 0.0


class Spells:
    def __init__(self, random: Random) -> None:
        self.random = random
        self.missiles: list[Missile] = []
        self.arrows: list[Arrow] = []
        self.pulses: list[Pulse] = []
        self.vines: list[Vine] = []
        self.sparks: list[Spark] = []

    def cast_missile(
        self,
        origin: Vec2,
        monster: object,
        at: Vec2,
        hostile: bool = False,
        owner: object = None,
        *,
        kind: str = "magic",
    ) -> None:
        missile = Missile(origin, at, monster, hostile, owner=owner, kind=kind)
        single = kind in ("fire", "life_drain")
        missile.darts = [[origin] for _ in range(1 if single else MISSILE_DARTS)]
        self.missiles.append(missile)

    def shoot(
        self, origin: Vec2, velocity: Vec2, hostile: bool = False, owner: object = None
    ) -> None:
        self.arrows.append(Arrow(origin, velocity, hostile, owner=owner))

    def vine(
        self, root: Vec2, monster: object, at: Vec2, hostile: bool = False, owner: object = None
    ) -> None:
        phase = self.random.uniform(0.0, math.tau)
        self.vines.append(Vine(root, at, monster, phase, hostile, owner=owner))

    def pulse(self, center: Vec2, radius: float) -> None:
        self.pulses.append(Pulse(center, radius))

    def sparkle(self, point: Vec2, color: str, count: int, speed: float) -> None:
        for _ in range(count):
            angle = self.random.uniform(0.0, 2.0 * math.pi)
            velocity = Vec2.from_angle(angle, speed * self.random.uniform(0.3, 1.0))
            self.sparks.append(Spark(point, velocity, color))

    def update(
        self,
        dt: float,
        locate: Locate,
        monster_at: MonsterAt,
        boxes: Sequence[Rect],
        floor_y: float,
        grip: Grip | None = None,
        locate_prey: Locate | None = None,
        prey_at: MonsterAt | None = None,
    ) -> list[SpellHit]:
        """Advance everything; returns the monsters (and, for hostile spells, the
        adventurers) hit this step."""
        prey_locate = locate_prey or _no_one
        hits = self._update_missiles(dt, locate, prey_locate)
        hits += self._update_arrows(dt, monster_at, prey_at or _no_one, boxes, floor_y)
        hits += self._update_vines(dt, grip, prey_locate)
        for pulse in self.pulses:
            pulse.age += dt
        self.pulses = [p for p in self.pulses if p.age < PULSE_TIME]
        drag = math.exp(-3.0 * dt)
        for spark in self.sparks:
            spark.age += dt
            spark.velocity = spark.velocity * drag
            spark.position += spark.velocity * dt
        self.sparks = [s for s in self.sparks if s.age < SPARK_LIFE]
        return hits

    def _update_missiles(self, dt: float, locate: Locate, locate_prey: Locate) -> list[SpellHit]:
        flying, hits = [], []
        for missile in self.missiles:
            missile.age += dt
            now = (locate_prey if missile.hostile else locate)(missile.monster)
            if now is not None:
                missile.target = now
            t = min(1.0, missile.age / missile.flight)
            for index, trail in enumerate(missile.darts):
                trail.append(missile.dart(index, t))
                keep = 18 if missile.kind == "life_drain" else DART_TRAIL
                del trail[:-keep]
            if t < 1.0:
                flying.append(missile)
            else:
                self.sparkle(missile.target, missile.kind, 14, 140.0)
                if now is not None:
                    heading = (missile.target - missile.origin).normalized()
                    velocity = heading * MISSILE_SPEED
                    hits.append(
                        SpellHit(
                            missile.monster,
                            missile.target,
                            velocity,
                            missile.hostile,
                            missile.owner,
                            missile.kind,
                        )
                    )
        self.missiles = flying
        return hits

    def _update_arrows(
        self,
        dt: float,
        monster_at: MonsterAt,
        prey_at: MonsterAt,
        boxes: Sequence[Rect],
        floor_y: float,
    ) -> list[SpellHit]:
        kept, hits = [], []
        for arrow in self.arrows:
            if arrow.stuck is not None:
                arrow.stuck += dt
                if arrow.stuck < ARROW_STUCK_TIME:
                    kept.append(arrow)
                continue
            arrow.age += dt
            if arrow.age > ARROW_FLIGHT_LIMIT:
                continue
            arrow.velocity += Vec2(0.0, ARROW_GRAVITY * dt)
            arrow.position += arrow.velocity * dt
            monster = (prey_at if arrow.hostile else monster_at)(arrow.position)
            if monster is not None:
                self.sparkle(arrow.position, "wood", 6, 90.0)
                hits.append(
                    SpellHit(monster, arrow.position, arrow.velocity, arrow.hostile, arrow.owner)
                )
                continue
            point = arrow.position
            if point.y >= floor_y or any(box.contains(point) for box in boxes):
                arrow.stuck = 0.0
                arrow.heading = arrow.velocity.normalized()
            kept.append(arrow)
        self.arrows = kept
        return hits

    def _update_vines(self, dt: float, grip: Grip | None, locate_prey: Locate) -> list[SpellHit]:
        growing, hits = [], []
        for vine in self.vines:
            vine.age += dt
            if not vine.struck:
                if vine.hostile:
                    now = locate_prey(vine.monster)
                else:
                    now = grip(vine.monster, vine.root) if grip is not None else None
                if now is not None:
                    vine.target = now
                if vine.age >= VINE_GROW:
                    vine.struck = True
                    self.sparkle(vine.target, "leaf", 10, 110.0)
                    if now is not None:
                        lash = (vine.target - vine.root).normalized() * 200.0
                        hits.append(
                            SpellHit(vine.monster, vine.target, lash, vine.hostile, vine.owner)
                        )
            if vine.age < VINE_TIME:
                growing.append(vine)
        self.vines = growing
        return hits
