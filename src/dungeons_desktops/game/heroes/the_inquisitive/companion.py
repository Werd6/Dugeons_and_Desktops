"""A small, noncombat familiar that follows Iggy over the same surface routes."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep, wrap_angle
from dungeons_desktops.game.actors.movement import RouteFollower
from dungeons_desktops.navigation.planner import Anchor, Move
from dungeons_desktops.navigation.terrain import Surface, TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.heroes.the_inquisitive.actor import Iggy

FOLLOW_DISTANCE = 14.0
REPLAN_TIME = 0.25
PACE = 1.3
RECALL_DISTANCE = 180.0
PAW_MARGIN = 4.0


def _paws(anchor: Anchor) -> Vec2:
    surface = anchor.surface
    if surface.hanging:
        return Vec2(anchor.point.x, surface.grip)
    if surface.wall:
        return Vec2(surface.start.x, clamp(anchor.point.y, surface.wall_top, surface.wall_bottom))
    return anchor.point


def _angle(surface: Surface) -> float:
    return surface.normal.angle() + math.pi / 2


class CatCompanion:
    """Owned and updated by its hero, never registered as prey or as a monster."""

    def __init__(self, owner: Iggy) -> None:
        self.owner = owner
        self.follower = RouteFollower(self._beside_owner())
        self.feet = _paws(self.follower.anchor)
        self.angle = _angle(self.follower.anchor.surface)
        self.facing = owner.facing
        self.phase = 0.0
        self.motion = 0.0
        self.time = 0.0
        self.opacity = 1.0
        self._replan = 0.0

    @property
    def active(self) -> bool:
        return (
            self.owner.animated and not self.owner.swallowed
            and self.owner.engulfed_by is None and self.owner.reeled is None
        )

    def _beside_owner(self) -> Anchor:
        owner = self.owner
        step = owner.follower.step
        anchor = (
            Anchor(step.surface, step.end)
            if step is not None and owner.follower.in_transition
            else owner.follower.current_anchor()
        )
        if not owner.animated or not owner.planner.owns(anchor.surface):
            anchor = owner.planner.anchor_near(owner.center(), walk_only=True)
        surface = anchor.surface
        direction = (1 if owner.velocity.y > 1 else -1) if surface.wall else owner.facing
        margin = min(PAW_MARGIN, surface.length / 2)
        coordinate = clamp(
            surface.coord(anchor.point) - direction * FOLLOW_DISTANCE,
            surface.low + margin, surface.high - margin,
        )
        return Anchor(surface, surface.point_at(coordinate))

    def _recall(self) -> None:
        self.follower.reset(self._beside_owner())
        self.feet = _paws(self.follower.anchor)
        self.angle = _angle(self.follower.anchor.surface)
        self.motion = 0.0
        self._replan = 0.0

    def update(self, dt: float) -> None:
        self.time += dt
        if not self.active:
            self.opacity = max(0.0, self.opacity - dt * 4)
            self.motion = max(0.0, self.motion - dt * 6)
            return
        if self.opacity == 0:
            self._recall()
        self.opacity = min(1.0, self.opacity + dt * 4)
        goal = self._beside_owner()
        if (
            not self.owner.planner.owns(self.follower.current_anchor().surface)
            or self.feet.distance_to(_paws(goal)) > RECALL_DISTANCE
        ):
            self._recall()
        self._replan -= dt
        if self._replan <= 0 and not self.follower.in_transition:
            self._replan = REPLAN_TIME
            here = self.follower.current_anchor()
            owner_anchor = self.owner.follower.current_anchor()
            close = (
                here.surface is owner_anchor.surface
                and here.point.distance_to(owner_anchor.point) <= FOLLOW_DISTANCE + 1
            )
            self.follower.reset(here)
            if not close:
                self.follower.set_route(self.owner.planner.plan(here, goal))
        previous = self.feet
        self.follower.update(dt * PACE)
        self.feet, self.angle = self._pose()
        delta = self.feet - previous
        distance = delta.length()
        along = delta.dot(Vec2.from_angle(self.angle))
        if abs(along) > 0.001:
            self.facing = 1 if along > 0 else -1
        elif not self.follower.moving:
            toward = (self.owner.center() - self.feet).dot(Vec2.from_angle(self.angle))
            if abs(toward) > 1:
                self.facing = 1 if toward > 0 else -1
        self.phase = (self.phase + distance / 9.0) % 1.0
        moving = min(1.0, distance / max(dt * 20, 1e-6))
        self.motion += (moving - self.motion) * min(1.0, dt * 12)

    def _pose(self) -> tuple[Vec2, float]:
        step = self.follower.step
        if step is None or not self.follower.in_transition:
            anchor = self.follower.current_anchor()
            return _paws(anchor), _angle(anchor.surface)
        t = clamp(self.follower.elapsed / max(step.duration, 1e-6), 0, 1)
        start = _paws(Anchor(step.from_surface, step.start))
        end = _paws(Anchor(step.surface, step.end))
        angle = _angle(step.from_surface)
        angle += wrap_angle(_angle(step.surface) - angle) * smoothstep(t)
        if step.move in (Move.MANTLE, Move.GRAB, Move.SWING):
            # Go around the corner instead of cutting through the solid window.
            wall = step.from_surface if step.from_surface.wall else step.surface
            if wall.wall:
                horizontal = step.surface if step.from_surface.wall else step.from_surface
                corner = Vec2(wall.start.x, horizontal.grip if horizontal.hanging else end.y)
                if not horizontal.hanging:
                    corner = Vec2(wall.start.x, horizontal.start.y)
                point = start.lerp(corner, t * 2) if t < 0.5 else corner.lerp(end, t * 2 - 1)
                normal = Vec2.from_angle(angle - math.pi / 2)
                return point + normal * (math.sin(math.pi * t) * 2.5), angle
            return start.lerp(end, smoothstep(t)), angle
        offset = (start - step.start).lerp(end - step.end, t)
        return self.follower.contact() + offset, angle

    def terrain_changed(self, change: TerrainChange) -> None:
        old = self.follower.current_anchor()
        if change.removed(old.surface.box) or self.follower.in_transition:
            self._recall()
            return
        delta = change.delta_for(old.surface.box) or Vec2(0, 0)
        point = old.point + delta
        box = change.new_index(old.surface.box)
        surface = next((
            surface for surface in self.owner.planner.surfaces
            if surface.kind is old.surface.kind and surface.box == box
            and surface.contains(point, 2)
        ), None)
        if surface is None:
            self._recall()
            return
        self.follower.reset(Anchor(surface, surface.closest_point(point)))
        self.feet, self.angle = self._pose()
        self._replan = 0.0
