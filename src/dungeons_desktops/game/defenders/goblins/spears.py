"""Thrown goblin spears: they arc under gravity point-first, wound the first stickman
they touch, and otherwise stick quivering in whatever window or floor they hit."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Rect, Vec2

GRAVITY = 520.0
STUCK_TIME = 3.0
FADE_TIME = 0.8
MAX_FLIGHT = 4.0


@dataclass(eq=False)
class Spear:
    position: Vec2
    """The tip."""
    velocity: Vec2
    length: float
    angle: float = 0.0
    age: float = 0.0
    stuck: float | None = None
    """Seconds since it stuck in the ground, or None while flying."""

    @property
    def fade(self) -> float:
        if self.stuck is None:
            return 0.0
        return max(0.0, min(1.0, (self.stuck - STUCK_TIME) / FADE_TIME))

    @property
    def quiver(self) -> float:
        """Sideways wobble of a freshly stuck spear, in radians."""
        if self.stuck is None:
            return 0.0
        return 0.25 * math.exp(-self.stuck * 6.0) * math.sin(self.stuck * 60.0)


class Spears:
    def __init__(self) -> None:
        self.spears: list[Spear] = []

    def throw(self, tip: Vec2, velocity: Vec2, length: float) -> None:
        self.spears.append(Spear(tip, velocity, length, velocity.angle()))

    def update[T](
        self,
        dt: float,
        boxes: Sequence[Rect],
        floor_y: float,
        width: float,
        hit: Callable[[Vec2], T | None],
    ) -> list[tuple[Spear, T]]:
        """Move spears; returns (spear, whatever `hit` found) for each that struck a body
        this step. Those spears are gone."""
        struck: list[tuple[Spear, T]] = []
        kept = []
        for spear in self.spears:
            spear.age += dt
            if spear.stuck is not None:
                spear.stuck += dt
                if spear.stuck < STUCK_TIME + FADE_TIME:
                    kept.append(spear)
                continue
            spear.velocity += Vec2(0.0, GRAVITY * dt)
            spear.position += spear.velocity * dt
            spear.angle = spear.velocity.angle()
            target = hit(spear.position)
            if target is not None:
                struck.append((spear, target))
                continue
            if spear.position.y >= floor_y or any(b.contains(spear.position) for b in boxes):
                spear.position = Vec2(spear.position.x, min(spear.position.y, floor_y + 2.0))
                spear.stuck = 0.0
            if spear.age < MAX_FLIGHT and -50.0 <= spear.position.x <= width + 50.0:
                kept.append(spear)
        self.spears = kept
        return struck
