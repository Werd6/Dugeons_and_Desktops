"""Minotaur surface transitions and movement interpolation."""

from __future__ import annotations

from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.navigation.planner import Anchor


@dataclass
class Flight:
    start: Vec2
    launch: Vec2
    duration: float
    target: Anchor | None
    aim: Vec2
    kind: str
    from_wall: bool = False
    age: float = 0.0


@dataclass
class Haul:
    start: Vec2
    end: Vec2
    duration: float
    target: Anchor
    kind: str
    from_wall: bool = False
    age: float = 0.0
    speed: float = 0.0


def sign(value: float, default: int = 1) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return default


def approach(value: float, target: float, rate: float) -> float:
    if value < target:
        return min(target, value + rate)
    return max(target, value - rate)


def carry_on(progress: float, carried: float, distance: float) -> float:
    lead = clamp(carried / distance, 0.0, 2.5) if distance > 1e-6 else 0.0
    return (progress**3 - 2.0 * progress**2 + progress) * lead + (
        3.0 * progress**2 - 2.0 * progress**3
    )
