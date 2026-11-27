"""Lobbed vials that burst on impact, and the aiming that lands them on a moving target."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.effects.ballistics import (
    GRAVITY,
)

SUBSTEP = 3.0
CLING_DURATION = 4.0
CLING_TICK = 1.0
CLING_DAMAGE = 1
CLING_SPACING = 14.5
CLING_ATTACHMENTS = (
    Vec2(-14.0, -10.0),
    Vec2(14.0, -10.0),
    Vec2(0.0, 16.0),
    Vec2(-16.0, 8.0),
    Vec2(16.0, 8.0),
    Vec2(0.0, -16.0),
)


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
    target: object = None


@dataclass
class ClingingOoze:
    """A green vial payload stuck to a moving monster."""

    target: object
    position: Vec2
    offset: Vec2
    owner: object = None
    hostile: bool = False
    age: float = 0.0
    next_tick: float = CLING_TICK


class Vials:
    def __init__(self, blast_radius: float = 30.0, explosion_time: float = 0.4) -> None:
        self.blast_radius = blast_radius
        self.explosion_time = explosion_time
        self.flying: list[Vial] = []
        self.explosions: list[Explosion] = []
        self.clinging: list[ClingingOoze] = []

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
        hits_body: Callable[[Vec2, bool], object | None],
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
            impact = self._advance(vial, dt, boxes, floor_y, hits_body)
            if impact is not None:
                point, target = impact
                started.append(
                    Explosion(
                        point,
                        self.blast_radius,
                        vial.hostile,
                        owner=vial.owner,
                        target=target,
                    )
                )
            elif -50.0 <= vial.position.x <= width + 50.0 and vial.age < 5.0:
                flying.append(vial)
        self.flying = flying
        self.explosions.extend(
            burst
            for burst in started
            if getattr(burst.owner, "variant", None) != "hero_alchemist"
        )
        return started

    def cling(
        self,
        target: object,
        point: Vec2,
        anchor: Vec2,
        owner: object = None,
        hostile: bool = False,
    ) -> None:
        impact_offset = point - anchor
        occupied = [ooze.offset for ooze in self.clinging if ooze.target is target]
        offset = impact_offset
        if occupied and any(
            offset.distance_to(existing) < CLING_SPACING for existing in occupied
        ):
            offset = max(
                CLING_ATTACHMENTS,
                key=lambda candidate: min(
                    candidate.distance_to(existing) for existing in occupied
                ),
            )
        self.clinging.append(
            ClingingOoze(target, anchor + offset, offset, owner, hostile)
        )

    def update_clinging(
        self,
        dt: float,
        locate: Callable[[object], Vec2 | None],
        damage: Callable[[ClingingOoze], bool],
    ) -> None:
        active = []
        for ooze in self.clinging:
            anchor = locate(ooze.target)
            if anchor is None:
                continue
            ooze.position = anchor + ooze.offset
            ooze.age += dt
            killed = False
            while ooze.age >= ooze.next_tick and ooze.next_tick <= CLING_DURATION:
                killed = damage(ooze)
                ooze.next_tick += CLING_TICK
                if killed:
                    break
            if not killed and ooze.age < CLING_DURATION:
                active.append(ooze)
        self.clinging = active

    @staticmethod
    def _advance(
        vial: Vial,
        dt: float,
        boxes: Sequence[Rect],
        floor_y: float,
        hits_body: Callable[[Vec2, bool], object | None],
    ) -> tuple[Vec2, object | None] | None:
        vial.velocity += Vec2(0.0, GRAVITY * dt)
        travel = vial.velocity * dt
        steps = max(1, int(travel.length() / SUBSTEP) + 1)
        step = travel / steps
        for _ in range(steps):
            point = vial.position + step
            if _blocked(point, boxes, floor_y):
                return vial.position, None
            vial.position = point
            if target := hits_body(point, vial.hostile):
                return point, target
        return None
