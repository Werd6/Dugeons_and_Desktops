"""Cloud of Leeching Blood: window-clipped mist which drains monsters."""

from __future__ import annotations

from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep

DURATION = 7.0
RADIUS = 92.0
DAMAGE = 1
HIT_INTERVAL = 1.0
SUMMON_TIME = 0.55
DRAIN_FLASH = 0.45


@dataclass
class BloodCloud:
    owner: object
    center: Vec2
    age: float = 0.0
    ticks: int = 0
    drain_flash: float = 0.0

    @property
    def expired(self) -> bool:
        return self.age >= DURATION

    @property
    def strength(self) -> float:
        grow = smoothstep(clamp(self.age / SUMMON_TIME, 0.0, 1.0))
        fade = smoothstep(clamp((DURATION - self.age) / 0.8, 0.0, 1.0))
        return grow * fade

    def update(self, dt: float) -> None:
        previous = self.age
        self.age = min(DURATION, self.age + dt)
        self.drain_flash = max(0.0, self.drain_flash - dt)
        active_age = max(0.0, self.age - SUMMON_TIME)
        previous_active = max(0.0, previous - SUMMON_TIME)
        due = int((active_age + 1e-9) / HIT_INTERVAL)
        previous_due = int((previous_active + 1e-9) / HIT_INTERVAL)
        for _ in range(max(0, due - max(self.ticks, previous_due))):
            self._drain_enemies()
            self.ticks += 1

    def _drain_enemies(self) -> None:
        world = self.owner.world
        drained = False
        for monster, point in world.monsters_near(self.center, RADIUS):
            if any(box.contains(point) for box in world.boxes):
                continue
            before = getattr(monster, "hp", None)
            away = (point - self.center).normalized()
            world.hurt_monster(
                monster,
                DAMAGE,
                point,
                away * 10.0 + Vec2(0.0, -8.0),
                ranged=True,
                attacker=self.owner,
            )
            after = getattr(monster, "hp", before)
            if before is not None and after is not None and after < before:
                if self.owner.animated:
                    self.owner.heal(DAMAGE)
                drained = True
        if drained:
            self.drain_flash = DRAIN_FLASH
