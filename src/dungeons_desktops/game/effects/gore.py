"""Blood: droplets that spray out, fall, and leave splats where they land on a window
or the floor. Splats ride nowhere; they just fade."""

from __future__ import annotations

import math
from dataclasses import dataclass
from random import Random

from dungeons_desktops.core.geometry import Rect, Vec2

GRAVITY = 650.0
DROP_LIFE = 2.0
SPLAT_LIFE = 3.5
MAX_SPLATS = 250


@dataclass(eq=False)
class Drop:
    position: Vec2
    velocity: Vec2
    size: float
    age: float = 0.0


@dataclass(eq=False)
class Splat:
    position: Vec2
    width: float
    age: float = 0.0


class Gore:
    def __init__(self, random: Random) -> None:
        self.random = random
        self.drops: list[Drop] = []
        self.splats: list[Splat] = []

    def spray(self, point: Vec2, direction: Vec2, count: int, speed: float) -> None:
        """`count` droplets fanning out around `direction` (any length), plus some
        that go every which way."""
        random = self.random
        aim = direction.angle() if direction.length() > 1e-6 else -math.pi / 2
        for i in range(count):
            wild = i % 3 == 0
            angle = random.uniform(-math.pi, math.pi) if wild else aim + random.gauss(0.0, 0.5)
            velocity = Vec2.from_angle(angle, speed * random.uniform(0.3, 1.0))
            self.drops.append(Drop(point, velocity, random.uniform(0.7, 1.7)))

    def update(self, dt: float, boxes: list[Rect], floor_y: float) -> None:
        alive = []
        for drop in self.drops:
            drop.age += dt
            drop.velocity = drop.velocity + Vec2(0.0, GRAVITY * dt)
            before = drop.position
            drop.position = before + drop.velocity * dt
            landed = self._landing(before, drop.position, boxes, floor_y)
            if landed is not None:
                self.splats.append(Splat(landed, drop.size * self.random.uniform(1.6, 3.0)))
            elif drop.age < DROP_LIFE:
                alive.append(drop)
        self.drops = alive
        for splat in self.splats:
            splat.age += dt
        self.splats = [s for s in self.splats if s.age < SPLAT_LIFE][-MAX_SPLATS:]

    @staticmethod
    def _landing(before: Vec2, after: Vec2, boxes: list[Rect], floor_y: float) -> Vec2 | None:
        """Where a falling drop crossed a window top or the floor this step."""
        if after.y <= before.y:
            return None
        if after.y >= floor_y:
            return Vec2(after.x, floor_y)
        for box in boxes:
            if before.y <= box.top < after.y and box.left <= after.x <= box.right:
                return Vec2(after.x, box.top)
        return None
