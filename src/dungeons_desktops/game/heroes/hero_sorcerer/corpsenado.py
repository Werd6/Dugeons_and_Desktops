"""A roaming storm of grave wind, bones, and skulls."""

from __future__ import annotations

from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, clamp

DURATION = 10.0
PATROL_DISTANCE = 145.0
SPEED = 70.0
DAMAGE_RADIUS = 48.0
DAMAGE = 2
HIT_INTERVAL = 0.5
SUMMON_TIME = 0.45


@dataclass
class Corpsenado:
    """A horizontal patrol which damages every monster caught in its funnel."""

    owner: object
    position: Vec2
    left: float
    right: float
    direction: int
    age: float = 0.0
    ticks: int = 0

    @classmethod
    def summon(cls, owner: object, point: Vec2) -> Corpsenado:
        margin = DAMAGE_RADIUS * 0.55
        left = max(margin, point.x - PATROL_DISTANCE)
        right = min(owner.world.width - margin, point.x + PATROL_DISTANCE)
        if right < left:
            left = right = clamp(point.x, margin, owner.world.width - margin)
        facing = 1 if point.x >= owner.center().x else -1
        return cls(owner, Vec2(clamp(point.x, left, right), point.y), left, right, facing)

    @property
    def expired(self) -> bool:
        return self.age >= DURATION

    @property
    def strength(self) -> float:
        grow = clamp(self.age / SUMMON_TIME, 0.0, 1.0)
        fade = clamp((DURATION - self.age) / 0.6, 0.0, 1.0)
        return grow * fade

    def update(self, dt: float) -> None:
        previous = self.age
        self.age = min(DURATION, self.age + dt)
        if previous >= DURATION:
            return

        active_dt = max(0.0, self.age - max(previous, SUMMON_TIME))
        travel = SPEED * active_dt
        x = self.position.x + self.direction * travel
        if x >= self.right:
            x = self.right
            self.direction = -1
        elif x <= self.left:
            x = self.left
            self.direction = 1
        self.position = Vec2(x, self.position.y)

        active_age = max(0.0, self.age - SUMMON_TIME)
        previous_active = max(0.0, previous - SUMMON_TIME)
        due = int((active_age + 1e-9) / HIT_INTERVAL)
        previous_due = int((previous_active + 1e-9) / HIT_INTERVAL)
        for _ in range(max(0, due - max(self.ticks, previous_due))):
            self._damage_enemies()
            self.ticks += 1

    def _damage_enemies(self) -> None:
        world = self.owner.world
        for monster, point in world.monsters_near(self.position, DAMAGE_RADIUS):
            away = (point - self.position).normalized()
            world.hurt_monster(
                monster,
                DAMAGE,
                point,
                away * 28.0 + Vec2(self.direction * 18.0, -18.0),
                ranged=True,
                attacker=self.owner,
            )
