"""Bullets: straight-line projectiles that stop at boxes, the floor, or the view edge."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Rect, Vec2

SUBSTEP = 3.0


@dataclass
class Bullet:
    position: Vec2
    velocity: Vec2
    age: float = 0.0


@dataclass
class Spark:
    position: Vec2
    age: float = 0.0


class Projectiles:
    def __init__(self, speed: float = 650.0, life: float = 2.5, spark_life: float = 0.18):
        self.speed = speed
        self.life = life
        self.spark_life = spark_life
        self.bullets: list[Bullet] = []
        self.sparks: list[Spark] = []

    def fire(self, origin: Vec2, direction: Vec2) -> None:
        self.bullets.append(Bullet(origin, direction.normalized() * self.speed))

    def update(self, dt: float, boxes: Sequence[Rect], floor_y: float, width: float) -> None:
        for spark in self.sparks:
            spark.age += dt
        self.sparks = [s for s in self.sparks if s.age < self.spark_life]

        alive = []
        for bullet in self.bullets:
            bullet.age += dt
            hit = self._advance(bullet, dt, boxes, floor_y, width)
            if hit is not None:
                self.sparks.append(Spark(hit))
            elif bullet.age < self.life:
                alive.append(bullet)
        self.bullets = alive

    @staticmethod
    def _advance(
        bullet: Bullet, dt: float, boxes: Sequence[Rect], floor_y: float, width: float
    ) -> Vec2 | None:
        travel = bullet.velocity * dt
        steps = max(1, int(travel.length() / SUBSTEP) + 1)
        step = travel / steps
        for _ in range(steps):
            point = bullet.position + step
            if point.y >= floor_y or any(box.contains(point) for box in boxes):
                return bullet.position
            bullet.position = point
            if not 0.0 <= point.x <= width or point.y < -200.0:
                bullet.age = float("inf")
                return None
        return None
