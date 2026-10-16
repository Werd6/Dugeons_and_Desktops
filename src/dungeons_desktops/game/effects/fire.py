"""A body set on fire: flames lick up from every limb, the body writhes and chars
black, and the fire dies down as the body fades out."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from random import Random

from dungeons_desktops.core.geometry import Vec2

BURN_TIME = 6.0
"""Seconds from catching fire until the body has burned away."""
WRITHE_TIME = 2.2
WRITHE_SPEED = 140.0
CHAR_TIME = 1.2
EMBER_RATE = 70.0
EMBER_LIFE = (0.35, 0.7)
EMBER_RISE = 70.0
EMBER_SIZE = (1.0, 2.0)


@dataclass(eq=False)
class Ember:
    position: Vec2
    velocity: Vec2
    life: float
    size: float
    age: float = 0.0


@dataclass(eq=False)
class Burn:
    time: float = 0.0
    embers: list[Ember] = field(default_factory=list)
    _carry: float = 0.0
    _writhe: float = 0.0

    @property
    def intensity(self) -> float:
        """1 while it rages, easing to 0 over the last 40% of the burn."""
        return max(0.0, min(1.0, (BURN_TIME - self.time) / (0.4 * BURN_TIME)))

    @property
    def char(self) -> float:
        """0 for fresh skin, 1 once burned black."""
        return min(1.0, self.time / CHAR_TIME)

    @property
    def writhing(self) -> bool:
        return self.time < WRITHE_TIME

    def update(self, dt: float, points: list[Vec2], random: Random, floor_y: float) -> Vec2 | None:
        """Advance the flames over `points` (spots along the body). Returns a jolt to
        apply to the body while it writhes, or None."""
        self.time += dt
        alive = []
        for ember in self.embers:
            ember.age += dt
            ember.velocity = ember.velocity * math.exp(-2.0 * dt) + Vec2(0.0, -EMBER_RISE * dt)
            ember.position += ember.velocity * dt
            if ember.age < ember.life and ember.position.y < floor_y:
                alive.append(ember)
        self.embers = alive

        self._carry += EMBER_RATE * self.intensity * dt
        while self._carry >= 1.0 and points:
            self._carry -= 1.0
            spot = random.choice(points)
            jitter = Vec2(random.uniform(-1.5, 1.5), random.uniform(-1.5, 1.5))
            velocity = Vec2(random.gauss(0.0, 12.0), -random.uniform(15.0, 45.0))
            self.embers.append(
                Ember(
                    spot + jitter,
                    velocity,
                    random.uniform(*EMBER_LIFE),
                    random.uniform(*EMBER_SIZE) * (0.5 + 0.5 * self.intensity),
                )
            )

        if not self.writhing:
            return None
        self._writhe -= dt
        if self._writhe > 0.0:
            return None
        self._writhe = random.uniform(0.15, 0.35)
        fade = 1.0 - self.time / WRITHE_TIME
        angle = random.uniform(-math.pi, 0.0)
        return Vec2.from_angle(angle, WRITHE_SPEED * fade)
