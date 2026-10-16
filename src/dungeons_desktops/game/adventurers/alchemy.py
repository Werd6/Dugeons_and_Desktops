"""Lobbed vials that burst on impact, and the aiming that lands them on a moving target."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.effects.ballistics import (
    GRAVITY,
)

SUBSTEP = 3.0


def _blocked(point: Vec2, boxes: Sequence[Rect], floor_y: float) -> bool:
    return point.y >= floor_y or any(box.contains(point) for box in boxes)


@dataclass
class Vial:
    position: Vec2
    velocity: Vec2
    hostile: bool = False
    """Thrown by a thrall: bursts on, and blasts, the free adventurers instead."""
    spin: float = 0.0
    age: float = 0.0
    owner: object = None
    """Who threw it."""


@dataclass
class Explosion:
    center: Vec2
    radius: float
    hostile: bool = False
    age: float = 0.0
    owner: object = None


class Vials:
    def __init__(self, blast_radius: float = 30.0, explosion_time: float = 0.4) -> None:
        self.blast_radius = blast_radius
        self.explosion_time = explosion_time
        self.flying: list[Vial] = []
        self.explosions: list[Explosion] = []

    def throw(
        self, origin: Vec2, velocity: Vec2, hostile: bool = False, owner: object = None
    ) -> None:
        self.flying.append(Vial(origin, velocity, hostile, owner=owner))

    def update(
        self,
        dt: float,
        boxes: Sequence[Rect],
        floor_y: float,
        width: float,
        hits_body: Callable[[Vec2, bool], bool],
    ) -> list[Explosion]:
        """`hits_body(point, hostile)`: whether a vial at `point` bursts on a body (a
        monster's, or a free adventurer's for a hostile one)."""
        for explosion in self.explosions:
            explosion.age += dt
        self.explosions = [e for e in self.explosions if e.age < self.explosion_time]

        started = []
        flying = []
        for vial in self.flying:
            vial.age += dt
            vial.spin += dt * 14.0
            burst = self._advance(vial, dt, boxes, floor_y, hits_body)
            if burst is not None:
                started.append(Explosion(burst, self.blast_radius, vial.hostile, owner=vial.owner))
            elif -50.0 <= vial.position.x <= width + 50.0 and vial.age < 5.0:
                flying.append(vial)
        self.flying = flying
        self.explosions.extend(started)
        return started

    @staticmethod
    def _advance(
        vial: Vial,
        dt: float,
        boxes: Sequence[Rect],
        floor_y: float,
        hits_body: Callable[[Vec2, bool], bool],
    ) -> Vec2 | None:
        vial.velocity += Vec2(0.0, GRAVITY * dt)
        travel = vial.velocity * dt
        steps = max(1, int(travel.length() / SUBSTEP) + 1)
        step = travel / steps
        for _ in range(steps):
            point = vial.position + step
            if _blocked(point, boxes, floor_y):
                return vial.position
            vial.position = point
            if hits_body(point, vial.hostile):
                return point
        return None
