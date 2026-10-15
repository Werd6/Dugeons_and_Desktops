"""A breath of fire as a stream of `Flame` particles: spat out of a mouth (`emit`),
drifting up and slowing as they spread (`step_flames`), and burning whoever they
touch (`burn_hits`). The dragon's breath, and the chimera's goat's."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman

FLAME_LIFE = 0.7
FLAME_RISE = 40.0
FLAME_DRAG = 1.5
SPREAD = 0.12
"""Standard deviation (radians) of each flame's direction about the aim."""
BURN_REACH = 26.0
"""Only stickmen whose middle is within this (plus the flame's size) are tested."""
ZERO = Vec2(0.0, 0.0)


@dataclass
class Flame:
    position: Vec2
    velocity: Vec2
    age: float = 0.0
    size: float = 1.0

    @property
    def radius(self) -> float:
        return (2.0 + 7.0 * self.age / FLAME_LIFE) * self.size


def emit(
    flames: list[Flame],
    due: float,
    rate: float,
    dt: float,
    mouth: Vec2,
    aim: Vec2,
    speed: float,
    random: Random,
    carry: Vec2 = ZERO,
    spread: float = SPREAD,
    size: float = 1.0,
) -> float:
    """Flames out of `mouth` along `aim` at `rate` a second; returns the fraction of a
    flame still due."""
    due += rate * dt
    while due >= 1.0:
        due -= 1.0
        direction = aim.rotated(random.gauss(0.0, spread))
        velocity = direction * (speed * random.uniform(0.8, 1.1)) + carry
        flames.append(Flame(mouth, velocity, size=size))
    return due


def step_flames(
    flames: list[Flame],
    dt: float,
    floor: float,
    drag_rate: float = FLAME_DRAG,
    skid: bool = False,
) -> tuple[list[Flame], list[Flame]]:
    """Age and move every flame: the ones still burning, and the ones spent this step
    (burnt out, or down on the floor unless they `skid` along it)."""
    drag = math.exp(-drag_rate * dt)
    alive, spent = [], []
    for flame in flames:
        flame.age += dt
        flame.velocity = flame.velocity * drag + Vec2(0.0, -FLAME_RISE * dt)
        flame.position += flame.velocity * dt
        if skid and flame.position.y >= floor:
            flame.position = Vec2(flame.position.x, floor - 0.5)
            flame.velocity = Vec2(flame.velocity.x, -abs(flame.velocity.y) * 0.15)
        if flame.age < FLAME_LIFE and flame.position.y < floor:
            alive.append(flame)
        else:
            spent.append(flame)
    return alive, spent


def burn_hits(flames: list[Flame], stickmen: list[Stickman]) -> Iterator[tuple[Stickman, Flame]]:
    """Every stickman fair game that a flame touches, with the first flame that does."""
    for stickman in stickmen:
        if not stickman.prey:
            continue
        center = stickman.center()
        for flame in flames:
            near = center.distance_to(flame.position) < BURN_REACH + flame.radius
            if near and stickman.hits(flame.position, flame.radius * 0.6):
                yield stickman, flame
                break
