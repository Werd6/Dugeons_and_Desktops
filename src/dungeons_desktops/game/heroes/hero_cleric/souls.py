"""Fallen adventurer souls flying to and orbiting the Hero Cleric."""

import math
from dataclasses import dataclass, field

from dungeons_desktops.core.geometry import Vec2

SOUL_SPEED = 520.0
ORBIT_SPEED = 1.9
ORBIT_RADIUS_X = 31.0
ORBIT_RADIUS_Y = 14.0
AUTO_CAST_AFTER = 3.0
RESURRECTION_RELEASE = 0.35
RESURRECTION_FLASH = 0.75


@dataclass
class Soul:
    original_variant: str
    point: Vec2
    angle: float
    flying: bool = True
    orbit_age: float = 0.0
    trail: list[Vec2] = field(default_factory=list)

    def update(self, dt: float, center: Vec2, index: int, count: int) -> None:
        if not self.flying:
            self.angle += ORBIT_SPEED * dt
            self.orbit_age += dt
            self.point = orbit_point(center, self.angle, index, count)
            return
        target = orbit_point(center, self.angle, index, count)
        offset = target - self.point
        distance = offset.length()
        self.trail.append(self.point)
        del self.trail[:-8]
        step = SOUL_SPEED * dt
        if distance <= step:
            self.point = target
            self.flying = False
            self.orbit_age = 0.0
            self.trail.clear()
        elif distance > 0:
            self.point += offset * (step / distance)


def orbit_point(center: Vec2, angle: float, index: int, count: int) -> Vec2:
    spacing = index * math.tau / max(1, count)
    phase = angle + spacing
    depth = 0.85 + 0.15 * math.sin(phase)
    return center + Vec2(
        math.cos(phase) * ORBIT_RADIUS_X * depth,
        math.sin(phase) * ORBIT_RADIUS_Y - 4.0,
    )
