"""Lingering poison clouds vented by the Hero Alchemist's back canister."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep

if TYPE_CHECKING:
    from dungeons_desktops.game.heroes.hero_alchemist.actor import HeroAlchemist

POISON_COOLDOWN = 12.0
POISON_DURATION = 6.0
POISON_RADIUS = 90.0
POISON_DAMAGE = 1
POISON_TICK = 1.0
CLOUD_GROW = 0.7
VENT_TIME = 0.7
VENT_RELEASE = 0.3


@dataclass
class PoisonCloud:
    owner: HeroAlchemist
    center: Vec2
    age: float = 0.0
    ticks: int = 0

    @property
    def radius(self) -> float:
        growth = smoothstep(clamp(self.age / CLOUD_GROW, 0.0, 1.0))
        return POISON_RADIUS * growth

    @property
    def expired(self) -> bool:
        return self.age >= POISON_DURATION

    def update(self, dt: float) -> None:
        previous = self.age
        self.age = min(POISON_DURATION, self.age + dt)
        due = int((self.age + 1e-9) / POISON_TICK)
        previous_due = int((previous + 1e-9) / POISON_TICK)
        for _ in range(max(0, due - max(self.ticks, previous_due))):
            self._damage_enemies()
            self.ticks += 1

    def _damage_enemies(self) -> None:
        world = self.owner.world
        for monster, point in world.monsters_near(self.center, self.radius):
            away = (point - self.center).normalized()
            world.hurt_monster(
                monster,
                POISON_DAMAGE,
                point,
                away * 12.0 + Vec2(0.0, -4.0),
                ranged=True,
                attacker=self.owner,
            )
