"""Kobolds on foot, and the traps kobolds leave about.

When its drake is killed the kobold rider jumps clear and fights on as a skirmisher:
with his bow drawn he stands and shoots the nearest adventurer in range, and while it
is reloading he runs from anyone who comes close, hopping off window edges to get
away, then turns and shoots again. With nobody in range he closes in.

Every kobold, mounted or not, drops a trap every `TRAP_COOLDOWN` while adventurers
are about. A trap falls to the window top or floor below, arms after a moment, and
snaps shut on the first adventurer to step on it (`TRAP_DAMAGE`).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.actors.hunting import priority_prey
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.defenders.drakes.drake import (
    ARROW_GRAVITY,
    ARROW_SPEED,
    RIDER_HEAD,
    RIDER_TORSO,
    Missile,
    lobbed,
    step_arrows,
)
from dungeons_desktops.navigation.terrain import Surface, TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.world.simulation import SimWorld

KOBOLD_HP = 2

LEG = 4.5
"""Hip height."""
RUN_SPEED = 60.0
ACCELERATION = 8.0
FLEE_RANGE = 140.0
"""Adventurers closer than this send a reloading kobold running."""
APPROACH = 0.6
"""Fraction of his run he closes in at when nobody is in bow range."""
STRIDE = 6.0
GRAVITY = 600.0
FOOT_BOW_RANGE = 420.0
"""How far a kobold on foot can shoot — farther than the mounted bow."""
BOW_COOLDOWN = (1.6, 2.2)
STEADY = 10.0
"""He only looses an arrow once he has slowed below this."""
LYING = 1.5

TRAP_COOLDOWN = 9.0
TRAP_RANGE = 220.0
"""It only bothers laying a trap with an adventurer this close."""
TRAP_ARMING = 0.6
TRAP_REACH = 5.0
TRAP_DAMAGE = 2
TRAP_LIFE = 40.0
TRAP_SNAP = 0.5
"""How long a sprung trap shows shut before it's gone."""
MAX_TRAPS = 15

ZERO = Vec2(0.0, 0.0)


def _surface_under(world: SimWorld, point: Vec2):
    from dungeons_desktops.game.actors.base import surface_below

    return surface_below(world.goblin_planner, point)


@dataclass(eq=False, repr=False)
class Kobold(Mortal):
    world: SimWorld
    foot: Vec2
    """Where he stands (or, in the air, the point between his feet)."""
    variant: str = "red"
    facing: int = 1
    velocity: Vec2 = ZERO
    arrows: list[Missile] = field(default_factory=list)
    max_hp = KOBOLD_HP
    linger = 3.0
    standing = True
    flying = False

    def __post_init__(self) -> None:
        rng = self.world.random
        self.support: Surface | None = None
        self.airborne = True
        self.speed = 0.0
        self.phase = 0.0
        self.gait = 0.0
        self.lean = 0.0
        self.clock = 0.0
        self.aim = Vec2(float(self.facing), -0.4).normalized()
        self.archer_target: Stickman | None = None
        self.bow_cooldown = rng.uniform(0.4, 0.9)
        self.trap_cooldown = rng.uniform(1.0, 4.0)
        self._fx = random.Random(len(self.world.kobolds) * 104729 + 7)
        self.alpha = False
        """True when this kobold leapt from the legendary red pack alpha."""
        if self.velocity.length() < 1e-6:
            self._land_if_down(self.foot)

    # ----- frame (shared with the mounted rider's drawing) -----------------------

    @property
    def seat(self) -> Vec2:
        """His hips."""
        bob = -abs(math.sin(self.phase * math.pi)) * 0.8 * self.gait
        drop = (LEG - LYING) * clamp(self.lean / 1.5, 0.0, 1.0) if self.dead else 0.0
        return self.foot + Vec2(0.0, -LEG + bob + drop)

    @property
    def rider_up(self) -> Vec2:
        return Vec2(0.0, -1.0).rotated(self.facing * self.lean)

    @property
    def rider_shoulder(self) -> Vec2:
        return self.seat + self.rider_up * RIDER_TORSO

    @property
    def rider_head(self) -> Vec2:
        return self.rider_shoulder + self.rider_up * (RIDER_HEAD + 0.6)

    @property
    def bow_hand(self) -> Vec2:
        return self.rider_shoulder + self.aim * 3.2

    @property
    def bow_draw(self) -> float:
        if self.dead or self.archer_target is None:
            return 0.0
        return clamp(1.0 - self.bow_cooldown / 0.8, 0.0, 1.0)

    def legs(self) -> list[tuple[Vec2, Vec2]]:
        """(knee, foot) for the near leg then the far one, striding as he runs."""
        hip = self.seat
        ahead = Vec2(float(self.facing), 0.0)
        legs = []
        for offset in (0.0, 0.5):
            swing = math.sin((self.phase + offset) * math.tau)
            lift = max(0.0, math.cos((self.phase + offset) * math.tau)) * 1.4 * self.gait
            foot = self.foot + ahead * (swing * 2.4 * self.gait) + Vec2(0.0, -lift)
            if self.dead:
                foot = hip + Vec2(-self.facing * 3.5 - offset * 2.0, 1.0)
            knee = hip.lerp(foot, 0.5) + ahead * 1.3
            legs.append((knee, foot))
        return legs

    def center(self) -> Vec2:
        return self.seat.lerp(self.rider_shoulder, 0.5)

    def parts(self) -> list[Vec2]:
        return [self.seat, self.rider_shoulder, self.rider_head]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        return (
            self.seat.distance_to(point) <= 2.5 + margin
            or self.rider_shoulder.distance_to(point) <= 2.5 + margin
            or self.rider_head.distance_to(point) <= RIDER_HEAD + margin
        )

    # ----- simulation ----------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.clock += dt
        self.bow_cooldown -= dt
        if self.airborne:
            self._fall(dt)
        else:
            self._skirmish(dt)
        self._shoot(dt)
        self.trap_cooldown = self.world.traps.lay(self.foot, self.variant, self.trap_cooldown, dt)
        self.arrows = step_arrows(self.world, self.arrows, dt)
        lean = 0.3 * clamp(self.speed * self.facing / RUN_SPEED, -1.0, 1.0)
        self.lean += (lean - self.lean) * min(1.0, dt * 8.0)

    def _prey(self) -> list[Stickman]:
        return [s for s in self.world.stickmen if s.prey]

    def _skirmish(self, dt: float) -> None:
        surface = self.support
        assert surface is not None
        target = self.archer_target
        threats = [s for s in self._prey() if s.contact().distance_to(self.foot) < FLEE_RANGE]
        threat = min(threats, key=lambda s: s.contact().distance_to(self.foot), default=None)
        desired = 0.0
        if threat is not None and not (self.bow_cooldown <= 0.0 and target is not None):
            away = 1 if self.foot.x >= threat.contact().x else -1
            desired = away * RUN_SPEED
        elif target is None and threat is None:
            prey = self._prey()
            nearest = min(prey, key=lambda s: s.contact().distance_to(self.foot), default=None)
            if nearest is not None:
                toward = 1 if nearest.contact().x >= self.foot.x else -1
                desired = toward * RUN_SPEED * APPROACH
        self.speed += (desired - self.speed) * min(1.0, ACCELERATION * dt)
        if abs(self.speed) > 5.0:
            self.facing = 1 if self.speed > 0 else -1
        elif target is not None:
            self.facing = 1 if target.center().x >= self.foot.x else -1
        x = self.foot.x + self.speed * dt
        low, high = surface.low, surface.high
        if not low <= x <= high:
            direction = 1 if x > high else -1
            edge = high if direction > 0 else low
            off = Vec2(edge + direction * 3.0, self.foot.y)
            world = self.world
            blocked = not world.left + 4.0 <= off.x <= world.width - 4.0 or any(
                box.contains(off - Vec2(0.0, 2.0)) for box in world.boxes
            )
            if blocked:
                x = clamp(x, low, high)
                self.speed = 0.0
            else:
                self.foot = off
                self.support = None
                self.airborne = True
                self.velocity = Vec2(direction * RUN_SPEED * 0.8, -60.0)
                return
        self.foot = Vec2(x, surface.start.y)
        self.phase += abs(self.speed) * dt / STRIDE
        moving = min(1.0, abs(self.speed) / 15.0)
        self.gait += (moving - self.gait) * min(1.0, 10.0 * dt)

    def _fall(self, dt: float) -> None:
        world = self.world
        before = self.foot
        self.velocity += Vec2(0.0, GRAVITY * dt)
        moved = before + self.velocity * dt
        self.foot = Vec2(clamp(moved.x, world.left + 4.0, world.width - 4.0), moved.y)
        self.gait += (0.0 - self.gait) * min(1.0, 6.0 * dt)
        self._land_if_down(before)

    def _land_if_down(self, before: Vec2) -> None:
        anchor = _surface_under(self.world, Vec2(self.foot.x, min(before.y, self.foot.y)))
        if anchor is None:
            return
        if self.foot.y >= anchor.point.y - 0.5 and self.velocity.y >= 0.0:
            self.foot = Vec2(
                clamp(self.foot.x, anchor.surface.low, anchor.surface.high), anchor.point.y
            )
            self.support = anchor.surface
            self.airborne = False
            self.velocity = ZERO
            self.speed = 0.0

    def _bow_cadence(self) -> tuple[float, float]:
        low, high = BOW_COOLDOWN
        if self.alpha or (getattr(self, "legendary", False) and self.variant == "red"):
            return (low * 0.5, high * 0.5)
        return BOW_COOLDOWN

    def _shoot(self, dt: float) -> None:
        """Turn the bow on the nearest adventurer in range; loose once it's drawn and
        he has stopped running."""
        shoulder = self.rider_shoulder
        in_range = [
            s for s in self._prey() if s.center().distance_to(shoulder) < FOOT_BOW_RANGE
        ]
        target = min(
            priority_prey(in_range), key=lambda s: s.center().distance_to(shoulder), default=None,
        )
        self.archer_target = target
        if target is None:
            rest = Vec2(float(self.facing), -0.4).normalized()
            self.aim = self.aim.lerp(rest, min(1.0, dt * 6.0)).normalized()
            return
        velocity = lobbed(self.bow_hand, target.center(), ARROW_SPEED, ARROW_GRAVITY)
        want = velocity.normalized()
        self.aim = self.aim.lerp(want, min(1.0, dt * 12.0)).normalized()
        steady = not self.airborne and abs(self.speed) < STEADY
        if self.bow_cooldown <= 0.0 and steady and self.aim.dot(want) > 0.97:
            self.arrows.append(Missile(self.bow_hand + want * 2.0, velocity))
            self.bow_cooldown = self._fx.uniform(*self._bow_cadence())

    # ----- death ---------------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        self.dead = True
        self.down_time = 0.0
        self.archer_target = None
        self.velocity = self.velocity + push * 0.25
        self.speed = 0.0
        self.gait = 0.0
        if self.velocity.y < 0.0 or self.airborne:
            self.airborne = True
            self.support = None

    def update_dead(self, dt: float) -> None:
        self.clock += dt
        self.down_time += dt
        if self.airborne:
            self._fall(dt)
        self.lean += (1.5 - self.lean) * min(1.0, dt * 5.0)
        self.arrows = step_arrows(self.world, self.arrows, dt)

    # ----- terrain -------------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.airborne or self.support is None:
            return
        box = self.support.box
        if change.removed(box):
            self.support = None
            self.airborne = True
            return
        ground = self.foot
        delta = change.delta_for(box)
        if delta is not None:
            ground += delta
            self.foot = ground
        anchor = _surface_under(self.world, ground - Vec2(0.0, 2.0))
        if anchor is None or abs(anchor.point.y - ground.y) > 2.0:
            self.support = None
            self.airborne = True
            return
        self.support = anchor.surface


@dataclass
class Trap:
    position: Vec2
    variant: str
    velocity: Vec2 = ZERO
    falling: bool = True
    box: int | None = None
    age: float = 0.0
    sprung: float | None = None
    """Seconds since it snapped shut, once it has."""

    @property
    def armed(self) -> bool:
        return not self.falling and self.sprung is None and self.age >= TRAP_ARMING


class Traps:
    """Every trap the kobolds have dropped: they outlast the kobold that laid them."""

    def __init__(self, world: SimWorld) -> None:
        self.world = world
        self.traps: list[Trap] = []

    def lay(self, point: Vec2, variant: str, cooldown: float, dt: float) -> float:
        """Tick a kobold's trap `cooldown`; drop a trap from `point` when it's up and
        an adventurer is near. Returns the new cooldown."""
        cooldown -= dt
        if cooldown > 0.0:
            return cooldown
        near = any(
            s.prey and s.contact().distance_to(point) < TRAP_RANGE for s in self.world.stickmen
        )
        if not near:
            return 0.0
        self.drop(point, variant)
        return TRAP_COOLDOWN

    def drop(self, point: Vec2, variant: str) -> Trap:
        trap = Trap(point, variant, Vec2(0.0, -30.0))
        self.traps.append(trap)
        if len(self.traps) > MAX_TRAPS:
            self.traps.pop(0)
        return trap

    def update(self, dt: float) -> None:
        world = self.world
        kept = []
        for trap in self.traps:
            trap.age += dt
            if trap.falling:
                self._fall(trap, dt)
            if trap.sprung is not None:
                trap.sprung += dt
                if trap.sprung < TRAP_SNAP:
                    kept.append(trap)
                continue
            if trap.armed:
                victim = next(
                    (
                        s
                        for s in world.stickmen
                        if s.prey
                        and abs(s.contact().x - trap.position.x) < TRAP_REACH
                        and abs(s.contact().y - trap.position.y) < 4.0
                    ),
                    None,
                )
                if victim is not None:
                    trap.sprung = 0.0
                    push = Vec2(0.0, -120.0)
                    victim.hurt(
                        TRAP_DAMAGE, trap.position, push, "kobold trap", "Caught in a kobold trap!"
                    )
            if trap.age < TRAP_LIFE:
                kept.append(trap)
        self.traps = kept

    def _fall(self, trap: Trap, dt: float) -> None:
        before = trap.position
        trap.velocity += Vec2(0.0, GRAVITY * dt)
        trap.position = before + trap.velocity * dt
        anchor = _surface_under(self.world, Vec2(trap.position.x, min(before.y, trap.position.y)))
        if anchor is not None and trap.position.y >= anchor.point.y and trap.velocity.y >= 0.0:
            trap.position = Vec2(trap.position.x, anchor.point.y)
            trap.falling = False
            trap.velocity = ZERO
            trap.box = anchor.surface.box

    def terrain_changed(self, change: TerrainChange) -> None:
        for trap in self.traps:
            if trap.falling:
                continue
            if trap.box is not None and change.removed(trap.box):
                trap.falling = True
                continue
            delta = change.delta_for(trap.box) if trap.box is not None else None
            if delta is not None:
                trap.position += delta
            anchor = _surface_under(self.world, trap.position - Vec2(0.0, 2.0))
            if anchor is None or abs(anchor.point.y - trap.position.y) > 2.0:
                trap.falling = True
            else:
                trap.box = anchor.surface.box

    def clear(self) -> None:
        self.traps.clear()
