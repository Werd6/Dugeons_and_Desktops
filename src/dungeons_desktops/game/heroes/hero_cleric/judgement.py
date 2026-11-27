"""Divine Judgement: a coordinated prayer followed by sustained sunlight."""

from __future__ import annotations

from dataclasses import dataclass, field

from dungeons_desktops.core.geometry import Vec2

JUDGEMENT_COOLDOWN = 15.0
JUDGEMENT_RANGE = 260.0
PRAYER_TIME = 0.8
BASE_BEAM_TIME = 2.0
ALLY_BEAM_BONUS = 0.5
TICK_INTERVAL = 1.0
TICK_DAMAGE = 3


@dataclass
class DivineJudgement:
    target: object
    point: Vec2
    prayers: list[object] = field(default_factory=list)
    age: float = 0.0
    beam_age: float = 0.0
    ticks: int = 0

    @property
    def beam_duration(self) -> float:
        return BASE_BEAM_TIME + ALLY_BEAM_BONUS * len(self.prayers)

    @property
    def active(self) -> bool:
        return self.age >= PRAYER_TIME and self.beam_age < self.beam_duration

    @property
    def done(self) -> bool:
        return self.beam_age >= self.beam_duration

    def update(self, hero, dt: float) -> None:
        point = hero.world.closest_part(self.target, self.point)
        if point is None:
            self.beam_age = self.beam_duration
            return
        self.point = point
        self.age += dt
        if self.age < PRAYER_TIME:
            return

        previous = self.beam_age
        self.beam_age = min(self.beam_duration, self.beam_age + dt)
        due = int((self.beam_age + 1e-9) / TICK_INTERVAL)
        previous_due = int((previous + 1e-9) / TICK_INTERVAL)
        for _ in range(max(0, due - max(self.ticks, previous_due))):
            point = hero.world.closest_part(self.target, self.point)
            if point is None:
                self.beam_age = self.beam_duration
                break
            self.point = point
            hero.world.hurt_monster(
                self.target,
                TICK_DAMAGE,
                point,
                Vec2(0.0, 35.0),
                ranged=True,
                attacker=hero,
            )
            self.ticks += 1
