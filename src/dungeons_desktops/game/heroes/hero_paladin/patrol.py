"""Clockwise patrol waypoints projected onto the currently reachable terrain."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.navigation.planner import Anchor

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman

SECTORS = 8
ANGLE_STEP = math.tau / SECTORS
RADIUS_FRACTION = 0.42
ARRIVAL_DISTANCE = 36.0


class Patrol:
    def __init__(self) -> None:
        self.sector: int | None = None

    def advance(self, hero: Stickman) -> bool:
        """Pick the next sector around the screen, using ordinary climbing/walking routes."""
        world = hero.world
        top = world.ceiling if world.ceiling is not None else 0.0
        center = Vec2((world.left + world.width) / 2, (top + world.floor_y) / 2)
        rx = max(1.0, (world.width - world.left) * RADIUS_FRACTION)
        ry = max(1.0, (world.floor_y - top) * RADIUS_FRACTION)
        start = hero.follower.current_anchor()
        reachable = hero.planner.reachable(start.surface)
        surfaces = [s for s in hero.planner.surfaces if s.id in reachable and s.length > 1]
        if not surfaces:
            return False
        if self.sector is None:
            offset = start.point - center
            angle = math.atan2(offset.y / ry, offset.x / rx)
            self.sector = (math.floor(angle / ANGLE_STEP) + 1) % SECTORS
        for _ in range(SECTORS):
            angle = self.sector * ANGLE_STEP
            self.sector = (self.sector + 1) % SECTORS
            waypoint = center + Vec2(math.cos(angle) * rx, math.sin(angle) * ry)
            anchors = [Anchor(s, s.closest_point(waypoint)) for s in surfaces]
            goal = min(anchors, key=lambda anchor: anchor.point.distance_to(waypoint))
            # Several sectors can collapse onto one ledge; skip those already reached.
            if goal.point.distance_to(start.point) < ARRIVAL_DISTANCE:
                continue
            route = hero.planner.plan(start, goal)
            if route is None or not route.steps:
                continue
            hero.goal = hero._wander_destination = goal.point
            hero.goal_reachable = True
            hero.follower.reset(start)
            hero.follower.set_route(route)
            return True
        return False
