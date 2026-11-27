"""A thrown dagger marks one foe for a teleport and repeated spinning cuts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dungeons_desktops.core.geometry import Vec2

RANGE = 320.0
COOLDOWN = 10.0
THROW_TIME = 0.1
DAGGER_SPEED = 900.0
EMBED_DELAY = 0.3
SPIN_TIME = 2.0
HIT_INTERVAL = 0.25
DAGGER_DAMAGE = 2
SPIN_DAMAGE = 2
SPIN_REACH = 24.0
DAGGER_LIFETIME = 2.0


class Phase(Enum):
    THROW = "throw"
    FLIGHT = "flight"
    EMBEDDED = "embedded"
    SPIN = "spin"


@dataclass
class SpinDagger:
    target: object
    point: Vec2
    direction: Vec2
    age: float = 0.0


class Assassinate:
    def __init__(self, hero) -> None:
        self.hero = hero
        self.phase: Phase | None = None
        self.target: object | None = None
        self.cooldown = 0.0
        self.age = 0.0
        self.point = Vec2(0, 0)
        self.direction = Vec2(1, 0)
        self.offset = Vec2(0, 0)
        self.hits = 0
        self.departure: Vec2 | None = None
        self.flash = 0.0
        self.daggers: list[SpinDagger] = []

    @property
    def active(self) -> bool:
        return self.phase is not None

    @property
    def spinning(self) -> bool:
        return self.phase is Phase.SPIN

    def allowed(self) -> bool:
        hero = self.hero
        return (
            hero.animated and not hero.thrall and not hero.paralysed and hero.blind <= 0
            and hero.lure is None and hero.reeled is None and hero.engulfed_by is None
            and hero.dragging_limb is None
        )

    def start(self) -> bool:
        hero = self.hero
        if (
            self.active or self.cooldown > 0 or not self.allowed()
            or not hero._can_act() or hero.weapon.busy
        ):
            return False
        found = hero.world.nearest_monster(hero.center(), RANGE)
        if found is None:
            return False
        self.target, self.point = found
        self.phase, self.age, self.hits = Phase.THROW, 0.0, 0
        self.cooldown = COOLDOWN
        hero.halt()
        hero._face(self.point, hero.weapon)
        hero.weapon.throwing = True
        hero.weapon.start()
        return True

    def update(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)
        self.flash = max(0.0, self.flash - dt)
        self._update_daggers(dt)
        if not self.active:
            return
        hero = self.hero
        center = hero.world.locate(self.target)
        if not self.allowed() or center is None:
            self.finish()
            return
        self.age += dt
        if self.phase is Phase.THROW:
            if self.age >= THROW_TIME:
                hand = hero.transforms()[hero.weapon.hand_chain.bones[-1]].end
                self.point = hand
                self.phase, self.age = Phase.FLIGHT, 0.0
                hero.reveal()
            return
        if self.phase is Phase.FLIGHT:
            aim = hero.world.closest_part(self.target, self.point)
            if aim is None or self.age > 2.0:
                self.finish()
                return
            delta = aim - self.point
            if delta.length() > 1e-6:
                self.direction = delta.normalized()
            if delta.length() > DAGGER_SPEED * dt:
                self.point += self.direction * (DAGGER_SPEED * dt)
                return
            self.point = aim
            self.offset = aim - center
            self.phase, self.age = Phase.EMBEDDED, 0.0
            if hero.world.hurt_monster(
                self.target, DAGGER_DAMAGE, aim, self.direction * 35,
                ranged=True, attacker=hero,
            ):
                self.finish()
            return
        if self.phase is Phase.EMBEDDED:
            self.point = center + self.offset
            if self.age + 1e-9 >= EMBED_DELAY:
                self.departure = hero.center()
                self.flash = 0.3
                self.phase, self.age = Phase.SPIN, 0.0
                hero.weapon.cancel()
                hero._pose_assassinate(dt)
                hero.reveal()
            return
        hero._pose_assassinate(dt)
        hero.reveal()
        # Count timed hits, so a large update neither loses ticks nor adds damage.
        due = int((min(self.age, SPIN_TIME) + 1e-9) / HIT_INTERVAL)
        while self.hits < due:
            self.hits += 1
            point = hero.world.closest_part(self.target, self.point)
            if point is None:
                self.finish()
                return
            if point.distance_to(self.point) > SPIN_REACH:
                self.daggers.append(SpinDagger(
                    self.target, self.point, (point - self.point).normalized(),
                ))
                continue
            killed = hero.world.hurt_monster(
                self.target, SPIN_DAMAGE, point,
                Vec2(hero.facing * 30, -15), attacker=hero,
            )
            if killed or hero.world.locate(self.target) is None:
                self.finish()
                return
        if self.age + 1e-9 >= SPIN_TIME:
            self.finish()

    def _update_daggers(self, dt: float) -> None:
        """Already-thrown daggers finish their flight even after the spin ends."""
        hero = self.hero
        if not hero.animated:
            self.daggers.clear()
            return
        flying = []
        for dagger in self.daggers:
            dagger.age += dt
            point = hero.world.closest_part(dagger.target, dagger.point)
            if point is None or dagger.age >= DAGGER_LIFETIME:
                continue
            delta = point - dagger.point
            if delta.length() > 1e-6:
                dagger.direction = delta.normalized()
            if delta.length() <= DAGGER_SPEED * dt:
                hero.world.hurt_monster(
                    dagger.target, SPIN_DAMAGE, point, dagger.direction * 35,
                    ranged=True, attacker=hero,
                )
            else:
                dagger.point += dagger.direction * (DAGGER_SPEED * dt)
                flying.append(dagger)
        self.daggers = flying

    def finish(self) -> None:
        spinning = self.spinning
        self.phase = None
        self.target = None
        self.hero.weapon.throwing = False
        self.hero.weapon.cancel()
        if spinning and self.hero.animated:
            self.hero._land_assassinate(self.point)
