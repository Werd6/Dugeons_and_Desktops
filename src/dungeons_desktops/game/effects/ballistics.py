"""Shared ballistic aiming for arrows, spears, bombs, and thrown bodies."""

from __future__ import annotations

from collections.abc import Sequence

from dungeons_desktops.core.geometry import Rect, Vec2, clamp

GRAVITY = 600.0


def lob_velocity(
    origin: Vec2,
    target: Vec2,
    target_velocity: Vec2,
    boxes: Sequence[Rect],
    floor_y: float,
    gravity: float = GRAVITY,
    pace: float = 1.0,
) -> Vec2:
    """Find the flattest tested arc which clears the supplied terrain."""
    lobs = _lobs(origin, target, target_velocity, gravity, pace)
    for velocity, flight in lobs:
        if _path_clear(origin, velocity, flight * 0.92, boxes, floor_y, gravity):
            return velocity
    return lobs[0][0]


def has_clear_lob(
    origin: Vec2,
    target: Vec2,
    target_velocity: Vec2,
    boxes: Sequence[Rect],
    floor_y: float,
    gravity: float = GRAVITY,
    pace: float = 1.0,
) -> bool:
    return any(
        _path_clear(origin, velocity, flight * 0.92, boxes, floor_y, gravity)
        for velocity, flight in _lobs(origin, target, target_velocity, gravity, pace)
    )


def _lobs(
    origin: Vec2, target: Vec2, target_velocity: Vec2, gravity: float, pace: float
) -> list[tuple[Vec2, float]]:
    distance = origin.distance_to(target)
    base = clamp(0.45 + distance / 450.0, 0.5, 1.3)
    lobs = []
    for extra in (0.0, 0.2, 0.4, 0.6, 0.8):
        flight = (base + extra) * pace
        aim = target + target_velocity * flight
        velocity = Vec2(
            (aim.x - origin.x) / flight,
            (aim.y - origin.y) / flight - 0.5 * gravity * flight,
        )
        lobs.append((velocity, flight))
    return lobs


def _path_clear(
    origin: Vec2,
    velocity: Vec2,
    duration: float,
    boxes: Sequence[Rect],
    floor_y: float,
    gravity: float,
) -> bool:
    for index in range(1, 41):
        time = duration * index / 40
        point = origin + velocity * time + Vec2(0.0, 0.5 * gravity * time * time)
        if point.y >= floor_y or any(box.contains(point) for box in boxes):
            return False
    return True
