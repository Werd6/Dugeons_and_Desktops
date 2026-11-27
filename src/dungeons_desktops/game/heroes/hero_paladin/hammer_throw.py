"""On taking damage, throw the carried hammer at the nearest foe outside melee."""

from __future__ import annotations

import math
from enum import Enum

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.hero_paladin.weapon import THROW_RELEASE

THROW_DAMAGE = 4
THROW_SPEED = 620.0
RETURN_SPEED = 820.0
SPIN_SPEED = math.tau * 3


class Phase(Enum):
    WINDUP = "windup"
    OUTWARD = "outward"
    RETURN = "return"


class HammerThrow:
    def __init__(self, hero) -> None:
        self.hero = hero
        self.pending = False
        self.phase: Phase | None = None
        self.target: object | None = None
        self.age = 0.0
        self.limit = 0.0
        self.point = Vec2(0, 0)
        self.direction = Vec2(1, 0)
        self.angle = 0.0
        self.trail: list[Vec2] = []

    @property
    def active(self) -> bool:
        return self.phase is not None

    @property
    def flying(self) -> bool:
        return self.phase in (Phase.OUTWARD, Phase.RETURN)

    def _allowed(self) -> bool:
        hero = self.hero
        return (
            hero.animated and not hero.thrall and not hero.paralysed and hero.blind <= 0
            and hero.lure is None and hero.reeled is None and hero.engulfed_by is None
            and hero.dragging_limb is None
        )

    def _target(self) -> tuple[object, Vec2] | None:
        hero = self.hero
        center = hero.center()
        candidates = [
            (monster, point) for monster in hero.world.monsters()
            if (point := hero.world.closest_part(monster, center)) is not None
            and not hero.in_melee_range(point)
        ]
        return min(candidates, key=lambda pair: pair[1].distance_to(center), default=None)

    def request(self) -> None:
        if self.active or not self._allowed() or self._target() is None:
            return
        self.pending = True
        self.prepare()

    def prepare(self) -> None:
        """Start before normal auto-attacks, but let an existing swing finish first."""
        hero = self.hero
        if not self._allowed():
            self.cancel()
            return
        if not self.pending or self.active or hero.weapon.busy or not hero._can_act():
            return
        self.pending = False
        found = self._target()
        if found is None:
            return
        self.target, point = found
        self.phase, self.age = Phase.WINDUP, 0.0
        hero._resume_route = hero._resume_route or (
            not hero.wander and hero.goal is not None and hero.follower.moving
        )
        hero.halt()
        hero._face(point, hero.weapon)
        hero.trail.clear()
        hero.weapon.throwing = True
        hero.weapon.start()

    def hand(self) -> Vec2:
        return self.hero.transforms()[self.hero.weapon.hand_chain.bones[-1]].end

    def update(self, dt: float) -> None:
        if not self.active:
            return
        if not self._allowed():
            self.cancel()
            return
        hero = self.hero
        self.age += dt
        if self.phase is Phase.WINDUP:
            if self.age + 1e-9 < THROW_RELEASE:
                return
            found = self._target()
            if found is None:
                self.cancel()
                return
            self.target, aim = found
            self.point = self.hand()
            self.direction = (aim - self.point).normalized()
            self.angle = self.direction.angle()
            self.phase, self.age = Phase.OUTWARD, 0.0
            self.limit = self.point.distance_to(aim) / THROW_SPEED + 2
            hero.weapon.hammer_away = True
            self.trail = [self.point]
            return
        self.angle += SPIN_SPEED * dt
        if self.phase is Phase.OUTWARD:
            aim = hero.world.closest_part(self.target, self.point)
            if aim is None or self.age >= self.limit:
                self._return()
                return
            if self._move(aim, THROW_SPEED * dt):
                self._return()
                hero.world.hurt_monster(
                    self.target, THROW_DAMAGE, aim, self.direction * 60,
                    ranged=True, attacker=hero,
                )
                hero.world.spells.sparkle(aim, "holy", 8, 80)
        elif self._move(self.hand(), RETURN_SPEED * dt) or self.age >= self.limit:
            self.cancel()

    def _move(self, aim: Vec2, distance: float) -> bool:
        delta = aim - self.point
        if delta.length() > 1e-6:
            self.direction = delta.normalized()
        arrived = delta.length() <= distance
        self.point = aim if arrived else self.point + self.direction * distance
        self.trail.append(self.point)
        del self.trail[:-8]
        return arrived

    def _return(self) -> None:
        self.phase, self.age = Phase.RETURN, 0.0
        self.limit = self.point.distance_to(self.hand()) / RETURN_SPEED + 2

    def cancel(self) -> None:
        if self.active:
            self.hero.weapon.cancel()
        self.pending = False
        self.phase = self.target = None
        self.hero.weapon.throwing = self.hero.weapon.hammer_away = False
        self.trail.clear()
