"""Three summoned hammers join every third successful melee strike."""

from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2

HAMMER_COUNT = 3
HAMMER_DAMAGE = 2
HAMMER_INTERVAL = 0.09
HEAL_AMOUNT = 2
SMITE_TIME = 0.8


@dataclass
class Smite:
    target: object | None
    point: Vec2
    age: float = 0.0
    confirmed: bool = False
    hits: int = 0

    def update(self, hero, dt: float) -> None:
        self.age += dt
        point = hero.world.closest_part(self.target, hero.center())
        if point is not None:
            self.point = point
        if not self.confirmed:
            return
        while self.hits < HAMMER_COUNT:
            if self.age + 1e-9 < hero.weapon.hit_time + self.hits * HAMMER_INTERVAL:
                break
            self.hits += 1
            if hero.world.locate(self.target) is not None:
                hero.world.hurt_monster(
                    self.target, HAMMER_DAMAGE, self.point,
                    Vec2(hero.facing * 30, -25), attacker=hero,
                )
