"""The elementals' specials, one per form, and the effects they leave behind.

A special (`TidalSurge`, `SeismicSlam`, `Whirlwind`, `Fireball`) is something the
elemental does where it is: `ready` says whether it would land on its quarry now, and
once started, `update` runs it (the elemental stays put, `charge` rising through the
windup) until it's done. What it sets loose - a wave, a shockwave, a fireball, a
burning patch, people caught up in a whirlwind - is an effect: it lives in the
elemental's `effects` and runs its course even if the elemental changes form or dies.

- Water, tidal surge: its crest rears up and a wave rolls out along its surface,
  sweeping everyone in its path flat and along (and off the window's edge).
- Earth, seismic slam: both fists come down and a shockwave runs both ways along its
  surface, knocking everyone it reaches flat.
- Air, whirlwind: it spins up into a tornado and dashes straight at its quarry, any
  way at all, catching up everyone it passes and flinging them out the far side.
- Fire, fireball: it lobs a fireball that bursts in a blast and leaves the ground
  burning for a while.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.systems.flames import Flame, emit, step_flames

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman
    from dungeons_desktops.systems.elementals import Elemental
    from dungeons_desktops.systems.world import SimWorld

UP = Vec2(0.0, -1.0)

SURGE_RANGE = 200.0
SURGE_WINDUP = 0.5
SURGE_COOLDOWN = 6.0
SURGE_SPEED = 220.0
SURGE_REACH = 220.0
SURGE_DAMAGE = 1
SURGE_FLING = 230.0
SURGE_DOWN = 1.2
SURGE_STUN = 0.5
SURGE_FRONT = 14.0
"""How deep the wave's front is: anyone this far behind it or just ahead gets swept."""

SLAM_RANGE = 140.0
SLAM_WINDUP = 0.6
SLAM_RECOVER = 0.3
SLAM_COOLDOWN = 7.0
SHOCK_SPEED = 300.0
SHOCK_REACH = 140.0
SLAM_DAMAGE = 2
SLAM_FLING = 170.0
SLAM_DOWN = 0.8
SLAM_STUN = 1.2

WHIRL_RANGE = 200.0
WHIRL_SPIN = 0.4
WHIRL_COOLDOWN = 6.0
WHIRL_SPEED = 300.0
WHIRL_PAST = 60.0
WHIRL_CATCH = 22.0
"""How close to its middle the tornado catches someone."""
WHIRL_CARRY = 0.3
WHIRL_DAMAGE = 1
WHIRL_FLING = 300.0
WHIRL_DOWN = 1.0
WHIRL_STUN = 1.0

FIREBALL_RANGE = 320.0
FIREBALL_WINDUP = 0.5
FIREBALL_COOLDOWN = 5.0
FIREBALL_SPEED = 260.0
FIREBALL_GRAVITY = 500.0
FIREBALL_LIFE = 3.0
FIREBALL_BLAST = 36.0
FIREBALL_DAMAGE = 2
FIREBALL_FLING = 140.0
PATCH_HALF = 24.0
PATCH_LIFE = 3.0
PATCH_DAMAGE = 1
PATCH_EVERY = 1.0
"""Seconds between the burns a patch gives someone standing in it."""

SOURCE = {
    "water": "water elemental",
    "earth": "earth elemental",
    "air": "air elemental",
    "fire": "fire elemental",
}
DEATHS = {
    "water": "Swept away by the water elemental!",
    "earth": "Flattened by the earth elemental!",
    "air": "Hurled by the air elemental!",
    "fire": "Burned up by the fire elemental!",
}


def on_ground(surface: Surface, stickman: Stickman, slack: float = 2.0) -> bool:
    """Whether `stickman` is up and standing on `surface` (a window top or the floor),
    whichever planner it came from."""
    if not stickman.prey:
        return False
    contact = stickman.contact()
    return (
        surface.low - slack <= contact.x <= surface.high + slack
        and abs(contact.y - surface.start.y) <= 4.0
    )


def clear_line(world: SimWorld, a: Vec2, b: Vec2) -> bool:
    """No window in the way between `a` and `b`."""
    steps = max(2, int(a.distance_to(b) / 8.0))
    for k in range(1, steps):
        point = a.lerp(b, k / steps)
        if any(box.contains(point) for box in world.boxes):
            return False
    return True


def _hurt(world, kind: str, stickman: Stickman, amount: int, point: Vec2, push: Vec2) -> bool:
    return stickman.hurt(amount, point, push, SOURCE[kind], DEATHS[kind])


# ----- effects ---------------------------------------------------------------------------


@dataclass(eq=False)
class Wave:
    """A tidal surge rolling along a window top or the floor."""

    x: float
    y: float
    low: float
    high: float
    box: int | None
    direction: int
    travelled: float = 0.0
    age: float = 0.0
    swept: set = field(default_factory=set)

    @property
    def size(self) -> float:
        """0..1: it builds up, then breaks and runs out."""
        t = self.travelled / SURGE_REACH
        return clamp(min(t * 5.0, 1.0) * (1.0 - max(0.0, t - 0.75) * 4.0), 0.0, 1.0)

    def update(self, world: SimWorld, dt: float) -> bool:
        self.age += dt
        step = SURGE_SPEED * dt
        self.x += self.direction * step
        self.travelled += step
        front = self.x
        for stickman in world.stickmen:
            if stickman in self.swept or not stickman.prey:
                continue
            contact = stickman.contact()
            if abs(contact.y - self.y) > 6.0:
                continue
            ahead = (contact.x - front) * self.direction
            if -SURGE_FRONT <= ahead <= 4.0:
                self.swept.add(stickman)
                push = Vec2(self.direction * SURGE_FLING, -40.0)
                if not _hurt(world, "water", stickman, SURGE_DAMAGE, contact, push):
                    behind = Vec2(contact.x - self.direction * 30.0, contact.y + 6.0)
                    stickman.knock_down(behind, SURGE_FLING, SURGE_DOWN, SURGE_STUN)
        for stickman in self.swept:
            if stickman.ragdoll is not None and not stickman.animated:
                center = stickman.center()
                carried = Vec2(front - self.direction * 5.0, self.y - 14.0)
                stickman.ragdoll.carry(carried - center, Vec2(self.direction * SURGE_SPEED, 0.0))
        edge = self.high if self.direction > 0 else self.low
        return self.travelled < SURGE_REACH and (edge - self.x) * self.direction > -6.0

    def terrain_changed(self, change: TerrainChange) -> bool:
        if change.removed(self.box):
            return False
        delta = change.delta_for(self.box)
        if delta is not None:
            self.x += delta.x
            self.y += delta.y
            self.low += delta.x
            self.high += delta.x
        new = change.new_index(self.box)
        self.box = self.box if new is None else new
        return True


@dataclass(eq=False)
class Shockwave:
    """A seismic slam's shockwave running both ways along a surface."""

    x: float
    y: float
    low: float
    high: float
    box: int | None
    radius: float = 0.0
    shaken: set = field(default_factory=set)
    _next_burst: float = 0.0

    def update(self, world: SimWorld, dt: float) -> bool:
        self.radius += SHOCK_SPEED * dt
        reach = min(self.radius, SHOCK_REACH)
        for stickman in world.stickmen:
            if stickman in self.shaken or not stickman.prey:
                continue
            contact = stickman.contact()
            if abs(contact.y - self.y) > 4.0 or not self.low - 2.0 <= contact.x <= self.high + 2.0:
                continue
            if abs(contact.x - self.x) <= reach:
                self.shaken.add(stickman)
                push = Vec2(math.copysign(SLAM_FLING, contact.x - self.x), -80.0)
                if not _hurt(world, "earth", stickman, SLAM_DAMAGE, contact, push):
                    stickman.knock_down(
                        Vec2(self.x, self.y + 20.0), SLAM_FLING, SLAM_DOWN, SLAM_STUN
                    )
        while self._next_burst <= reach:
            for side in (-1.0, 1.0):
                x = self.x + side * self._next_burst
                if self.low <= x <= self.high:
                    world.debris.burst(Vec2(x, self.y), UP, 3, 120.0, chunks=1, puffs=1)
            self._next_burst += 20.0
        return self.radius < SHOCK_REACH

    def terrain_changed(self, change: TerrainChange) -> bool:
        if change.removed(self.box):
            return False
        delta = change.delta_for(self.box)
        if delta is not None:
            self.x += delta.x
            self.y += delta.y
            self.low += delta.x
            self.high += delta.x
        new = change.new_index(self.box)
        self.box = self.box if new is None else new
        return True


@dataclass(eq=False)
class Caught:
    """Someone the whirlwind caught up: carried along a moment, then flung out."""

    stickman: Stickman
    direction: Vec2
    age: float = 0.0
    position: Vec2 | None = None

    def update(self, world: SimWorld, dt: float) -> bool:
        self.age += dt
        if self.age < WHIRL_CARRY:
            if self.position is None:
                self.position = self.stickman.center()
            self.position += self.direction * (WHIRL_SPEED * dt)
            ragdoll = self.stickman.ragdoll
            if ragdoll is not None:
                ragdoll.carry(self.position - self.stickman.center(), self.direction * WHIRL_SPEED)
            return True
        ragdoll = self.stickman.ragdoll
        if ragdoll is not None:
            fling = self.direction * WHIRL_FLING + Vec2(0.0, -120.0)
            ragdoll.apply_impulse(self.stickman.center(), fling, 40.0)
        return False

    def terrain_changed(self, change: TerrainChange) -> bool:
        return True


@dataclass(eq=False)
class FireballShot:
    owner: Elemental
    """Whose `effects` the burning patch it leaves joins."""
    position: Vec2
    velocity: Vec2
    age: float = 0.0
    flames: list[Flame] = field(default_factory=list)
    _due: float = 0.0
    burst: bool = False

    def update(self, world: SimWorld, dt: float) -> bool:
        self.age += dt
        self.flames, _ = step_flames(self.flames, dt, world.floor_y)
        if self.burst:
            return bool(self.flames)
        self.velocity += Vec2(0.0, FIREBALL_GRAVITY * dt)
        self.position += self.velocity * dt
        trail = (self.velocity * -1.0).normalized()
        self._due = emit(
            self.flames,
            self._due,
            60.0,
            dt,
            self.position,
            trail,
            40.0,
            world.random,
            spread=0.6,
            size=0.7,
        )
        hit = any(s.prey and s.hits(self.position, 3.0) for s in world.stickmen)
        box = next((b for b in world.boxes if b.contains(self.position)), None)
        if hit or box is not None or self.position.y >= world.floor_y or self.age > FIREBALL_LIFE:
            self._burst(world, box)
        return True

    def _burst(self, world: SimWorld, box) -> None:
        self.burst = True
        point = self.position
        for stickman in world.stickmen:
            if not stickman.prey or stickman.center().distance_to(point) > FIREBALL_BLAST:
                continue
            push = (stickman.center() - point).normalized() * FIREBALL_FLING + Vec2(0.0, -60.0)
            if _hurt(world, "fire", stickman, FIREBALL_DAMAGE, stickman.center(), push):
                stickman.ignite()
            else:
                stickman.knock_down(point, FIREBALL_FLING, 0.5, 0.2)
        for k in range(14):
            way = Vec2.from_angle(-math.pi * k / 13, 1.0)
            self.flames.append(Flame(point, way * 160.0, 0.0, 1.2))
        world.debris.burst(point, UP, 6, 140.0, puffs=4, scale=0.7)
        patch = BurningPatch.at(world, point, box)
        if patch is not None:
            self.owner.effects.append(patch)

    def terrain_changed(self, change: TerrainChange) -> bool:
        return True


@dataclass(eq=False)
class BurningPatch:
    """A stretch of window top or floor left burning by a fireball."""

    x: float
    y: float
    box: int | None
    age: float = 0.0
    flames: list[Flame] = field(default_factory=list)
    _due: float = 0.0
    _next: dict = field(default_factory=dict)

    @staticmethod
    def at(world: SimWorld, point: Vec2, box) -> BurningPatch | None:
        """On the window top the fireball burst on (or just inside), or the floor or top
        below it."""
        if box is not None and point.y - box.top <= 14.0:
            return BurningPatch(point.x, box.top, world.boxes.index(box))
        tops = [
            (b.top, i)
            for i, b in enumerate(world.boxes)
            if b.left <= point.x <= b.right and b.top >= point.y - 4.0
        ]
        top, index = min(tops, default=(world.floor_y, None))
        if top >= world.floor_y:
            top, index = world.floor_y, None
        if top - point.y > 40.0:
            return None
        return BurningPatch(point.x, top, index)

    def update(self, world: SimWorld, dt: float) -> bool:
        self.age += dt
        self.flames, _ = step_flames(self.flames, dt, self.y)
        if self.age < PATCH_LIFE:
            spot = Vec2(self.x + world.random.uniform(-PATCH_HALF, PATCH_HALF), self.y - 1.0)
            fading = 1.0 - max(0.0, self.age - PATCH_LIFE + 0.8) / 0.8
            self._due = emit(
                self.flames,
                self._due,
                70.0 * fading,
                dt,
                spot,
                UP,
                45.0,
                world.random,
                spread=0.4,
                size=0.6,
            )
            for stickman in world.stickmen:
                if not stickman.prey:
                    continue
                contact = stickman.contact()
                if abs(contact.y - self.y) > 6.0 or abs(contact.x - self.x) > PATCH_HALF:
                    continue
                if self.age < self._next.get(stickman, 0.0):
                    continue
                self._next[stickman] = self.age + PATCH_EVERY
                if _hurt(world, "fire", stickman, PATCH_DAMAGE, contact, Vec2(0.0, -60.0)):
                    stickman.ignite()
        return self.age < PATCH_LIFE or bool(self.flames)

    def terrain_changed(self, change: TerrainChange) -> bool:
        if change.removed(self.box):
            return False
        delta = change.delta_for(self.box)
        if delta is not None:
            self.x += delta.x
            self.y += delta.y
            self.flames = [
                Flame(f.position + delta, f.velocity, f.age, f.size) for f in self.flames
            ]
        new = change.new_index(self.box)
        self.box = self.box if new is None else new
        return True


# ----- specials --------------------------------------------------------------------------


class Special:
    windup = 0.5
    cooldown = 6.0
    length = 0.5
    """Seconds it takes from start to done (unless it decides for itself)."""

    def __init__(self, elemental: Elemental, target: Stickman) -> None:
        self.elemental = elemental
        self.target = target
        self.time = 0.0

    @property
    def charge(self) -> float:
        """0..1 through the windup (and 1 while it's under way)."""
        return clamp(self.time / self.windup, 0.0, 1.0)

    @staticmethod
    def ready(elemental: Elemental, target: Stickman) -> bool:
        raise NotImplementedError

    def update(self, dt: float) -> bool:
        """Run it on; True once it's done."""
        raise NotImplementedError

    def cancel(self) -> None:
        """Cut short (by a change of form)."""


class TidalSurge(Special):
    windup = SURGE_WINDUP
    cooldown = SURGE_COOLDOWN

    @staticmethod
    def ready(elemental: Elemental, target: Stickman) -> bool:
        surface = elemental.surface()
        return (
            surface is not None
            and on_ground(surface, target)
            and abs(target.contact().x - elemental.feet.x) <= SURGE_RANGE
        )

    def update(self, dt: float) -> bool:
        e = self.elemental
        self.time += dt
        if self.time < self.windup:
            if self.target.prey:
                e.face(self.target.center())
            return False
        surface = e.surface()
        if surface is not None:
            x = clamp(e.feet.x + e.facing * 10.0, surface.low, surface.high)
            e.effects.append(
                Wave(x, surface.start.y, surface.low, surface.high, surface.box, e.facing)
            )
        return True


class SeismicSlam(Special):
    windup = SLAM_WINDUP
    cooldown = SLAM_COOLDOWN

    @staticmethod
    def ready(elemental: Elemental, target: Stickman | None) -> bool:
        surface = elemental.surface()
        if surface is None:
            return False
        x = elemental.feet.x
        return any(
            on_ground(surface, s) and abs(s.contact().x - x) <= SLAM_RANGE
            for s in elemental.world.stickmen
        )

    def __init__(self, elemental: Elemental, target: Stickman) -> None:
        super().__init__(elemental, target)
        self.slammed = False

    def update(self, dt: float) -> bool:
        e = self.elemental
        self.time += dt
        if self.time < self.windup:
            if self.target is not None and self.target.prey:
                e.face(self.target.center())
            return False
        if not self.slammed:
            self.slammed = True
            surface = e.surface()
            feet = e.feet
            world = e.world
            world.debris.burst(feet, UP, 12, 180.0, ring_radius=16.0, cracks=5, chunks=4, puffs=6)
            if surface is not None:
                e.effects.append(
                    Shockwave(feet.x, surface.start.y, surface.low, surface.high, surface.box)
                )
        return self.time >= self.windup + SLAM_RECOVER


class Whirlwind(Special):
    windup = WHIRL_SPIN
    cooldown = WHIRL_COOLDOWN

    @staticmethod
    def ready(elemental: Elemental, target: Stickman) -> bool:
        center, theirs = elemental.center(), target.center()
        return center.distance_to(theirs) <= WHIRL_RANGE and clear_line(
            elemental.world, center, theirs
        )

    def __init__(self, elemental: Elemental, target: Stickman) -> None:
        super().__init__(elemental, target)
        self.direction = Vec2(float(elemental.facing), 0.0)
        self.span = 0.0
        self.travelled = 0.0
        self.caught: set = set()

    @property
    def spin(self) -> float:
        """0..1: how far it has wound itself up into a tornado (and back down at the end)."""
        if self.time < self.windup:
            return self.time / self.windup
        if self.span > 0.0 and self.travelled >= self.span:
            return 0.0
        return 1.0

    def update(self, dt: float) -> bool:
        e = self.elemental
        self.time += dt
        if self.time < self.windup:
            if self.target.prey:
                offset = self.target.center() - e.center()
                if offset.length() > 1.0:
                    self.direction = offset.normalized()
                    self.span = min(WHIRL_RANGE, offset.length()) + WHIRL_PAST
                e.face(self.target.center())
            return False
        if self.span <= 0.0:
            self.span = WHIRL_PAST
        step = min(WHIRL_SPEED * dt, self.span - self.travelled)
        moved = e.dash(self.direction * step)
        self.travelled += step
        center = e.center()
        for stickman in e.world.stickmen:
            if stickman in self.caught or not stickman.prey:
                continue
            if stickman.center().distance_to(center) <= WHIRL_CATCH:
                self.caught.add(stickman)
                push = self.direction * WHIRL_FLING
                if not _hurt(e.world, "air", stickman, WHIRL_DAMAGE, stickman.center(), push):
                    stickman.knock_down(
                        center - self.direction * 10.0,
                        WHIRL_SPEED,
                        WHIRL_DOWN + WHIRL_CARRY,
                        WHIRL_STUN,
                    )
                    e.effects.append(Caught(stickman, self.direction))
        return self.travelled >= self.span or not moved


class Fireball(Special):
    windup = FIREBALL_WINDUP
    cooldown = FIREBALL_COOLDOWN

    @staticmethod
    def ready(elemental: Elemental, target: Stickman) -> bool:
        distance = elemental.center().distance_to(target.center())
        return distance <= FIREBALL_RANGE and not elemental.in_reach(target, slack=1.5)

    def update(self, dt: float) -> bool:
        e = self.elemental
        self.time += dt
        if self.time < self.windup:
            if self.target.prey:
                e.face(self.target.center())
            return False
        hand = e.hand_raised()
        if self.target.prey:
            aim = self.target.contact() + Vec2(0.0, -12.0)
        else:
            aim = hand + Vec2(e.facing * 120.0, 0.0)
        velocity = arc(hand, aim)
        e.effects.append(FireballShot(e, hand, velocity))
        return True


def arc(origin: Vec2, target: Vec2) -> Vec2:
    """The velocity that lobs a fireball from `origin` down onto `target`."""
    flight = max(0.35, origin.distance_to(target) / FIREBALL_SPEED)
    offset = target - origin
    return Vec2(offset.x / flight, offset.y / flight - 0.5 * FIREBALL_GRAVITY * flight)


SPECIALS: dict[str, type[Special]] = {
    "water": TidalSurge,
    "earth": SeismicSlam,
    "air": Whirlwind,
    "fire": Fireball,
}
