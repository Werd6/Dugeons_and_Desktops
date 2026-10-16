"""Generic actor positioning, routes, and terrain-change handling."""

from __future__ import annotations

import math

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.actors.movement import RouteFollower
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor, Move, Planner, Route, RouteStep
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.locomotion import LocomotionDriver, UpperBodyLayer
from dungeons_desktops.rig.skeleton import BoneTransform, Pose, forward_kinematics

BODY_RADIUS = 4.0
GOAL_SNAP = 80.0
REANCHOR_DISTANCE = 12.0
ZERO = Vec2(0.0, 0.0)
_GONE = -1


def _distance_to_segment(point: Vec2, a: Vec2, b: Vec2) -> float:
    ab = b - a
    length_sq = ab.length_sq()
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, (point - a).dot(ab) / length_sq))
    return point.distance_to(a + ab * t)


def out_of_boxes(point: Vec2, boxes: list[Rect], margin: float = 2.0) -> Vec2:
    """Return the nearest point outside a box when ``point`` is enclosed."""
    for box in boxes:
        if box.contains(point):
            point = min(
                (
                    Vec2(box.left - margin, point.y),
                    Vec2(box.right + margin, point.y),
                    Vec2(point.x, box.top - margin),
                    Vec2(point.x, box.bottom + margin),
                ),
                key=point.distance_to,
            )
    return point


def _through(box: int | None, changes: list[TerrainChange]) -> int | None:
    for change in changes:
        if box == _GONE or change.removed(box):
            return _GONE
        box = change.new_index(box)
    return box


def surface_below(planner: Planner, point: Vec2) -> Anchor:
    """Return the walkable point directly below ``point``, or the nearest one."""
    below = [
        surface
        for surface in planner.surfaces
        if surface.walkable
        and surface.low - 1.0 <= point.x <= surface.high + 1.0
        and surface.start.y >= point.y - 4.0
    ]
    if below:
        surface = min(below, key=lambda candidate: candidate.start.y)
        return Anchor(surface, surface.closest_point(Vec2(point.x, surface.start.y)))
    return planner.anchor_near(point, walk_only=True)


class Actor:
    """Shared route-following base for adventurers and defenders."""

    def __init__(
        self,
        world: World,
        layout: BipedLayout,
        anchor: Anchor,
        upper: UpperBodyLayer | None = None,
    ) -> None:
        self.world = world
        self.layout = layout
        self.follower = RouteFollower(anchor)
        self.locomotion = LocomotionDriver(layout, self.follower.command(), upper=upper)
        self.goal: Vec2 | None = None
        self.goal_reachable = True
        self.needs_replan = False
        self._pending_changes: list[TerrainChange] = []
        self.velocity = ZERO
        self._last_contact = anchor.point

    @property
    def planner(self) -> Planner:
        return self.world.planner

    @property
    def animated(self) -> bool:
        return True

    @property
    def facing(self) -> int:
        return self.locomotion.facing

    def pose(self) -> Pose:
        return self.locomotion.pose

    def transforms(self) -> dict[str, BoneTransform]:
        return forward_kinematics(self.layout.skeleton, self.pose())

    def contact(self) -> Vec2:
        return self.follower.contact()

    def center(self) -> Vec2:
        return self.transforms()[self.layout.torso].start

    def say(self, message: str) -> None:
        self.world.say(self, message)

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        transforms = self.transforms()
        head = transforms[self.layout.head].end
        scale = self.layout.scale
        if head.distance_to(point) <= self.layout.head_radius + 2.0 * scale + margin:
            return True
        return any(
            _distance_to_segment(point, transform.start, transform.end)
            <= BODY_RADIUS * scale + margin
            for transform in transforms.values()
        )

    def _track_velocity(self, dt: float) -> None:
        contact = self.contact()
        measured = (contact - self._last_contact) / dt if dt > 0 else ZERO
        self.velocity = self.velocity.lerp(measured, min(1.0, dt * 10.0))
        self._last_contact = contact

    def move_goal_with_box(self, change: TerrainChange) -> None:
        if self.goal is None:
            return
        anchor = self.planner.anchor_near(self.goal, 1.0)
        if anchor is None:
            return
        delta = change.delta_for(anchor.surface.box)
        if delta is not None:
            self.goal += delta

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.follower.in_transition:
            box = _through(self.follower.step.surface.box, self._pending_changes)
            self._pending_changes.append(change)
            self.needs_replan = True
            delta = None if box is _GONE else change.delta_for(box)
            if delta is not None:
                self.follower.carry_transition(delta)
            return
        old = self.follower.current_anchor()
        box = old.surface.box
        delta = change.delta_for(box)
        if change.removed(box):
            self.lost_support(old.point + (delta or ZERO))
            return
        self.reanchor(delta or ZERO, delta is not None, change.new_index(box))

    def reanchor(self, delta: Vec2, carried: bool, box: int | None = None) -> None:
        old = self.follower.current_anchor()
        contact = old.point + delta
        anchor = self._matching_anchor(old, contact, old.surface.box if box is None else box)
        if anchor is None:
            self.lost_support(contact)
            return
        if carried:
            self.locomotion.shift(delta)
        self.follower.reset(anchor)
        self.replan()

    def lost_support(self, contact: Vec2) -> None:
        raise NotImplementedError

    def drop_from(self, start: Vec2) -> None:
        anchor = self.follower.current_anchor()
        height = max(0.0, anchor.point.y - start.y)
        duration = math.sqrt(2.0 * height / self.planner.settings.gravity) + 0.2
        step = RouteStep(Move.DROP, start, anchor.point, duration, anchor.surface, anchor.surface)
        self.follower.set_route(Route((step,)))

    def _matching_anchor(self, old: Anchor, contact: Vec2, box: int | None) -> Anchor | None:
        same = [
            surface
            for surface in self.planner.surfaces
            if surface.kind is old.surface.kind
            and surface.box == box
            and surface.contains(contact, 2.0)
        ]
        if same:
            return Anchor(same[0], same[0].closest_point(contact))
        return self.planner.anchor_near(contact, REANCHOR_DISTANCE)

    def set_goal(self, point: Vec2) -> None:
        anchor = self.planner.anchor_near(point, GOAL_SNAP)
        if anchor is None:
            self.say("Too far from any surface - click closer to a box or the floor")
            return
        self.goal = anchor.point
        if self.follower.in_transition:
            self.needs_replan = True
        else:
            self.replan()

    def replan(self) -> None:
        if self.goal is None:
            return
        start = self.follower.current_anchor()
        goal = self.planner.anchor_near(self.goal, REANCHOR_DISTANCE)
        route = self.planner.plan(start, goal) if goal is not None else None
        self.goal_reachable = route is not None
        self.follower.reset(start)
        if route is None:
            self.say("No route there")
            return
        self.follower.set_route(route)
        moves = " > ".join(dict.fromkeys(step.move.value for step in route.steps)) or "here"
        self.say(f"Route: {moves}  ({route.duration:.1f}s)")

    def halt(self) -> None:
        if not self.follower.in_transition:
            self.follower.reset(self.follower.current_anchor())

    def _replan_if_needed(self) -> None:
        if self.needs_replan and not self.follower.in_transition:
            self.needs_replan = False
            changes, self._pending_changes = self._pending_changes, []
            old = self.follower.current_anchor()
            box = old.surface.box
            if not self.planner.owns(old.surface):
                box = _through(box, changes)
            if box is _GONE:
                self.lost_support(old.point)
                return
            self.reanchor(ZERO, carried=False, box=box)
