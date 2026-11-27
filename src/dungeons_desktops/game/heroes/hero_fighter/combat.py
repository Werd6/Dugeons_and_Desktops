"""Combat data and released effects for The Soulforger."""

from __future__ import annotations

from dataclasses import dataclass, field

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.adventurers.actor import MELEE_PUSH
from dungeons_desktops.navigation.planner import Anchor

MARK_CAST_TIME = 0.25
MARK_REACQUIRE = 2.0
MARK_SPEED = 2.0
MARK_DAMAGE_BONUS = 1

THROW_COOLDOWN = 8.0
THROW_WINDUP = 0.35
THROW_RANGE = 360.0
THROW_MIN_RANGE = 90.0
THROW_SPEED = 560.0
THROW_DAMAGE = 4
THROW_HIT_RADIUS = 16.0
THROW_MARGIN = 45.0

LEAP_COOLDOWN = 10.0
LEAP_RANGE = 160.0
LEAP_TIME = 0.32
LEAP_HEIGHT = 20.0
LEAP_OFFSET = 30.0
FLURRY_TIME = 0.8
FLURRY_HITS = 6
FLURRY_DAMAGE = 1
FLURRY_REACH = 58.0
FLURRY_SEQUENCE = (
    "trident_stab",
    "shield_slice",
    "trident_slice",
    "shield_slice",
    "trident_stab",
    "shield_slice",
)

SHIELD_COOLDOWN = 4.0
SHIELD_RANGE = 50.0
SHIELD_TRAVEL = 0.2
SHIELD_DAMAGE = 2
SHIELD_PUSH = 240.0


@dataclass
class CombatLeap:
    start: Vec2
    landing: Anchor
    age: float = 0.0

    def feet(self) -> Vec2:
        progress = clamp(self.age / LEAP_TIME, 0.0, 1.0)
        feet = self.start.lerp(self.landing.point, smoothstep(progress))
        return feet - Vec2(0.0, 4.0 * LEAP_HEIGHT * progress * (1.0 - progress))


@dataclass
class SpectralTrident:
    position: Vec2
    direction: Vec2
    hit: set[object] = field(default_factory=set)

    def update(self, owner: object, dt: float) -> bool:
        """Advance and damage each crossed monster once; return whether it remains."""
        travel = self.direction * (THROW_SPEED * dt)
        steps = max(1, int(travel.length() / 2.5) + 1)
        step = travel / steps
        for _ in range(steps):
            self.position += step
            for monster, point in owner.world.monsters_near(
                self.position, THROW_HIT_RADIUS
            ):
                if monster in self.hit:
                    continue
                self.hit.add(monster)
                owner.world.hurt_monster(
                    monster,
                    owner.damage_against(monster, THROW_DAMAGE),
                    point,
                    self.direction * 180.0 + Vec2(0.0, -50.0),
                    ranged=True,
                    attacker=owner,
                )
        ceiling = owner.world.ceiling
        top = -200.0 if ceiling is None else ceiling
        left = getattr(owner.world, "left", 0.0)
        return (
            left - THROW_MARGIN <= self.position.x <= owner.world.width + THROW_MARGIN
            and top - THROW_MARGIN <= self.position.y <= owner.world.floor_y + THROW_MARGIN
        )


@dataclass
class SpectralShield:
    target: object
    origin: Vec2
    position: Vec2
    age: float = 0.0

    def update(self, owner: object, dt: float) -> bool:
        """Fly to the marked target and strike it; return whether it remains."""
        self.age += dt
        point = owner.world.closest_part(self.target, self.position)
        if point is None:
            return False
        progress = clamp(self.age / SHIELD_TRAVEL, 0.0, 1.0)
        self.position = self.origin.lerp(point, smoothstep(progress))
        if progress < 1.0:
            return True
        away = (point - owner.center()).normalized()
        if away.length() == 0.0:
            away = Vec2(float(owner.facing), 0.0)
        owner.world.hurt_monster(
            self.target,
            owner.damage_against(self.target, SHIELD_DAMAGE),
            point,
            away * SHIELD_PUSH + Vec2(0.0, -80.0),
            attacker=owner,
        )
        owner.world.spells.sparkle(point, "holy", 10, 120.0)
        return False


def final_push(facing: int) -> Vec2:
    return Vec2(facing * MELEE_PUSH, -MELEE_PUSH * 0.4)
