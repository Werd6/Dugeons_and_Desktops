"""Minotaur combat payloads and hit geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman


@dataclass
class Thrown:
    victim: Stickman
    origin: Vec2
    velocity: Vec2
    ground_y: float
    age: float = 0.0


def segment_distance(point: Vec2, start: Vec2, end: Vec2) -> float:
    segment = end - start
    length = segment.length_sq()
    amount = 0.0 if length < 1e-9 else clamp((point - start).dot(segment) / length, 0.0, 1.0)
    return point.distance_to(start + segment * amount)
