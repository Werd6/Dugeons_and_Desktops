"""A slow soft-bodied hunter that crawls over every connected surface.

It cannot jump. It slides over floors, walls, and ceilings toward the nearest free
adventurer, using a spring-coupled particle spine for its visible motion. In reach it
lurches forward and engulfs its quarry. A captive floats inside and keeps using their
normal weapon while digestion hurts them; on death the body becomes a fading skeleton.
From a wall or ceiling the ooze lets go when an adventurer passes below, falling onto
them and engulfing them when it lands.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.actors.movement import RouteFollower
from dungeons_desktops.game.defenders.displacer.actor import along
from dungeons_desktops.navigation.planner import ALONG_MOVES, Anchor, Move, MoveSettings
from dungeons_desktops.navigation.terrain import Surface, TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.world.simulation import SimWorld

OOZE_HP = 30

WIDTH = 86.0
HALF_WIDTH = WIDTH / 2.0
HEIGHT = 50.0
BODY_OFFSET = 23.0
SLIDE_SPEED = 18.0
CLIMB_SPEED = 14.0
HANG_SPEED = 12.0
WAVE_LENGTH = 45.0
SPRING = 90.0
COUPLING = 16.0
DAMPING = 9.0
REPLAN_EVERY = 0.45
GOAL_SNAP = 90.0
ENGULF_REACH = 39.0
LURCH_TIME = 0.55
LURCH_HIT = 0.3
LURCH_DISTANCE = 17.0
DIGEST_EVERY = 1.0
DIGEST_DAMAGE = 1
DROP_WIDTH = 34.0
GRAVITY = 900.0
SKELETON_FADE = 3.0
CORNER_MOVES = frozenset({Move.GRAB, Move.MANTLE, Move.SWING})

MOVES = MoveSettings(
    walk_speed=SLIDE_SPEED,
    climb_speed=CLIMB_SPEED,
    hang_speed=HANG_SPEED,
    mantle_time=0.75,
    grab_time=0.7,
    swing_time=0.8,
    max_drop=0.0,
    max_hang_drop=0.0,
    max_jump=0.0,
    gravity=GRAVITY,
    edge_clearance=4.0,
)

REST_SPINE = (
    Vec2(-40.0, -7.0),
    Vec2(-35.0, -19.0),
    Vec2(-25.0, -35.0),
    Vec2(-11.0, -46.0),
    Vec2(5.0, -49.0),
    Vec2(21.0, -42.0),
    Vec2(34.0, -28.0),
    Vec2(41.0, -15.0),
)


@dataclass
class SoftPoint:
    position: Vec2
    velocity: Vec2 = Vec2(0.0, 0.0)


@dataclass
class DissolvingSkeleton:
    offset: Vec2
    facing: int
    age: float = 0.0

    @property
    def fade(self) -> float:
        return clamp(self.age / SKELETON_FADE, 0.0, 1.0)


class OozeRig:
    """A spring-coupled particle spine driven by a wave traveling toward the face."""

    def __init__(self) -> None:
        self.nodes = [SoftPoint(point) for point in REST_SPINE]

    def update(self, dt: float, phase: float, motion: float, lurch: float = 0.0) -> None:
        positions = [node.position for node in self.nodes]
        targets: list[Vec2] = []
        last = len(REST_SPINE) - 1
        for index, rest in enumerate(REST_SPINE):
            progress = index / last
            wave = math.sin(phase - progress * math.tau)
            squeeze = math.cos(phase - progress * math.tau)
            targets.append(
                Vec2(
                    rest.x
                    + motion * (2.6 * wave + 1.5 * progress)
                    + LURCH_DISTANCE * lurch * progress**2,
                    rest.y
                    + motion * (3.2 * squeeze - 1.5 * wave * (1.0 - progress))
                    + 4.0 * lurch * (1.0 - progress),
                )
            )

        drag = math.exp(-DAMPING * dt)
        for index, node in enumerate(self.nodes):
            neighbors = []
            if index:
                neighbors.append(positions[index - 1] - REST_SPINE[index - 1])
            if index < last:
                neighbors.append(positions[index + 1] - REST_SPINE[index + 1])
            neighbor_offset = (
                sum(neighbors, Vec2(0.0, 0.0)) / len(neighbors)
                if neighbors
                else Vec2(0.0, 0.0)
            )
            own_offset = positions[index] - REST_SPINE[index]
            force = (targets[index] - positions[index]) * SPRING
            force += (neighbor_offset - own_offset) * COUPLING
            node.velocity = (node.velocity + force * dt) * drag
            node.position = node.position + node.velocity * dt

    def points(self) -> tuple[Vec2, ...]:
        return tuple(node.position for node in self.nodes)


class Ooze(Mortal):
    max_hp = OOZE_HP
    linger = 3.0

    def __init__(self, world: SimWorld, anchor: Anchor, facing: int = 1) -> None:
        self.world = world
        self.damage = 0
        self.dead = False
        self.down_time = 0.0
        self.follower: RouteFollower | None = RouteFollower(anchor)
        self.position = anchor.point
        self.up = anchor.surface.normal
        self.facing = 1 if facing >= 0 else -1
        self.velocity = Vec2(0.0, 0.0)
        self.speed = 0.0
        self.phase = 0.0
        self.time = 0.0
        self.rig = OozeRig()
        self.target: Stickman | None = None
        self._replan = 0.0
        self.lurch_time = 0.0
        self.lurch_target: Stickman | None = None
        self._lurched = False
        self.engulfed: list[Stickman] = []
        self._digest: dict[Stickman, float] = {}
        self.skeletons: list[DissolvingSkeleton] = []
        self.drop_target: Stickman | None = None

    @property
    def support(self) -> Surface | None:
        return self.follower.current_anchor().surface if self.follower is not None else None

    def center(self) -> Vec2:
        return self.to_world(Vec2(0.0, -BODY_OFFSET))

    def local_frame(self, local_x: float = 0.0) -> tuple[Vec2, Vec2]:
        """Return the local forward and outward axes at one slice of the body.

        During a corner transition the leading slices adopt the new surface before
        the trailing slices. That lets the soft rig wrap around the corner instead of
        rotating as one rigid silhouette.
        """
        up = self.up
        follower = self.follower
        step = follower.step if follower is not None else None
        if step is not None and step.move in CORNER_MOVES:
            progress = clamp(follower.elapsed / max(step.duration, 1e-6), 0.0, 1.0)
            progress = smoothstep(clamp(progress + local_x / WIDTH, 0.0, 1.0))
            blended = step.from_surface.normal.lerp(step.surface.normal, progress)
            if blended.length() > 0.2:
                up = blended.normalized()
        return along(up) * float(self.facing), up

    def to_world(self, local: Vec2) -> Vec2:
        side, up = self.local_frame(local.x)
        return self.position + side * local.x + up * (-local.y)

    def to_local(self, point: Vec2) -> Vec2:
        offset = point - self.position
        side = along(self.up) * float(self.facing)
        return Vec2(offset.dot(side), -offset.dot(self.up))

    def spine(self) -> tuple[Vec2, ...]:
        return tuple(self.to_world(point) for point in self.rig.points())

    def parts(self) -> list[Vec2]:
        return [self.center(), *self.spine()[1::2]]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        local = self.to_local(point)
        if not -HALF_WIDTH - margin <= local.x <= HALF_WIDTH + LURCH_DISTANCE + margin:
            return False
        height = HEIGHT * math.sqrt(max(0.0, 1.0 - (local.x / (HALF_WIDTH + 2.0)) ** 2))
        return -height - margin <= local.y <= margin

    @property
    def lurch(self) -> float:
        if self.lurch_time <= 0.0:
            return 0.0
        return math.sin(math.pi * clamp(self.lurch_time / LURCH_TIME, 0.0, 1.0))

    def engulfed_feet(self, stickman: Stickman) -> Vec2:
        slot = self.engulfed.index(stickman) if stickman in self.engulfed else 0
        bob = math.sin(self.time * 2.3 + slot) * 2.5
        return self.to_world(Vec2(slot * 8.0 - 4.0, -10.0 - bob))

    def update(self, dt: float) -> None:
        self.time += dt
        self._update_skeletons(dt)
        self._digest_captives(dt)
        before = self.center()
        if self.follower is None:
            self._fall(dt)
        elif self.lurch_time > 0.0:
            self._lurch(dt)
        else:
            below = self._prey_below()
            if below is not None and self.support is not None and not self.support.walkable:
                self._drop(below)
            else:
                self._hunt(dt)
        moved = self.center().distance_to(before)
        self.speed = moved / dt if dt > 0.0 else 0.0
        self.phase += moved / WAVE_LENGTH * math.tau
        self.rig.update(dt, self.phase, min(1.0, self.speed / SLIDE_SPEED), self.lurch)

    def _free_prey(self) -> list[Stickman]:
        return [man for man in self.world.stickmen if man.prey and man not in self.engulfed]

    def _hunt(self, dt: float) -> None:
        prey = self._free_prey()
        self.target = min(
            prey, key=lambda man: man.center().distance_to(self.center()), default=None
        )
        if self.target is None:
            return
        if not self.engulfed and self.target.center().distance_to(self.center()) <= ENGULF_REACH:
            self._start_lurch(self.target)
            return
        self._replan -= dt
        follower = self.follower
        assert follower is not None
        if self._replan <= 0.0 and not follower.in_transition:
            self._replan = REPLAN_EVERY
            self._route_to(self.target.contact())
        old = self.position
        follower.update(dt)
        self._settle()
        ahead = (self.position - old).dot(along(self.up))
        if abs(ahead) > 0.05:
            self.facing = 1 if ahead > 0.0 else -1

    def _route_to(self, point: Vec2) -> bool:
        follower = self.follower
        assert follower is not None
        goal = self.world.ooze_planner.anchor_near(point, GOAL_SNAP)
        if goal is None:
            return False
        start = follower.current_anchor()
        route = self.world.ooze_planner.plan(start, goal)
        if route is None or any(step.move in (Move.JUMP, Move.DROP) for step in route.steps):
            return False
        follower.reset(start)
        follower.set_route(route)
        return True

    def _settle(self) -> None:
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is None or step.move in ALONG_MOVES:
            anchor = follower.current_anchor()
            self.position, self.up = anchor.point, anchor.surface.normal
            return
        progress = clamp(follower.elapsed / max(step.duration, 1e-6), 0.0, 1.0)
        eased = smoothstep(progress)
        self.position = step.start.lerp(step.end, eased)
        up = step.from_surface.normal.lerp(step.surface.normal, eased)
        self.up = up.normalized() if up.length() > 0.2 else step.surface.normal

    def _start_lurch(self, target: Stickman) -> None:
        follower = self.follower
        if follower is not None:
            follower.reset(follower.current_anchor())
        local = self.to_local(target.center())
        if abs(local.x) > 1.0:
            self.facing = 1 if local.x > 0.0 else -1
        self.lurch_time = 1e-6
        self.lurch_target = target
        self._lurched = False

    def _lurch(self, dt: float) -> None:
        self.lurch_time += dt
        target = self.lurch_target
        if not self._lurched and self.lurch_time >= LURCH_HIT:
            self._lurched = True
            if target is not None and target.prey:
                if target.center().distance_to(self.center()) <= ENGULF_REACH + LURCH_DISTANCE:
                    self._engulf(target)
        if self.lurch_time >= LURCH_TIME:
            self.lurch_time = 0.0
            self.lurch_target = None

    def _engulf(self, target: Stickman) -> None:
        if target in self.engulfed or not target.prey:
            return
        self.engulfed.append(target)
        self._digest[target] = DIGEST_EVERY
        target.engulf(self)

    def _digest_captives(self, dt: float) -> None:
        for man in list(self.engulfed):
            if man not in self.world.stickmen or not man.animated:
                self._skeletonize(man)
                continue
            self._digest[man] -= dt
            if self._digest[man] <= 0.0:
                self._digest[man] += DIGEST_EVERY
                man.hurt_from(
                    self,
                    DIGEST_DAMAGE,
                    man.center(),
                    Vec2(0.0, 0.0),
                    "ooze",
                    "Dissolved inside an ooze!",
                    bleed=False,
                )
                if not man.animated:
                    self._skeletonize(man)

    def _skeletonize(self, man: Stickman) -> None:
        if man in self.engulfed:
            self.engulfed.remove(man)
        self._digest.pop(man, None)
        man.engulfed_by = None
        if man in self.world.stickmen:
            self.world.stickmen.remove(man)
        self.skeletons.append(DissolvingSkeleton(Vec2(-4.0, -23.0), man.facing))

    def _update_skeletons(self, dt: float) -> None:
        for skeleton in self.skeletons:
            skeleton.age += dt
        self.skeletons = [skeleton for skeleton in self.skeletons if skeleton.age < SKELETON_FADE]

    def _prey_below(self) -> Stickman | None:
        if self.support is None or self.support.walkable:
            return None
        body = self.center()
        below = [
            man
            for man in self._free_prey()
            if man.center().y > body.y + 10.0 and abs(man.center().x - body.x) <= DROP_WIDTH
        ]
        return min(below, key=lambda man: man.center().y, default=None)

    def _drop(self, target: Stickman) -> None:
        self.drop_target = target
        self.position = self.center() + Vec2(0.0, BODY_OFFSET)
        self.up = Vec2(0.0, -1.0)
        self.follower = None
        self.velocity = Vec2(0.0, 20.0)

    def _fall(self, dt: float) -> None:
        before = self.position
        self.velocity += Vec2(0.0, GRAVITY * dt)
        after = before + self.velocity * dt
        crossed = [
            surface
            for surface in self.world.ooze_planner.surfaces
            if surface.walkable
            and surface.low - HALF_WIDTH <= after.x <= surface.high + HALF_WIDTH
            and before.y <= surface.start.y <= after.y
        ]
        if not crossed:
            self.position = after
            return
        surface = min(crossed, key=lambda item: item.start.y)
        anchor = Anchor(surface, surface.closest_point(after))
        self.follower = RouteFollower(anchor)
        self.position = anchor.point
        self.up = surface.normal
        self.velocity = Vec2(0.0, 0.0)
        target, self.drop_target = self.drop_target, None
        if (
            target is not None
            and target.prey
            and abs(target.center().x - self.position.x) <= HALF_WIDTH
        ):
            self._engulf(target)

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.follower is None:
            if change.shift is not None:
                self.position += change.shift
            return
        old = self.follower.current_anchor()
        delta = change.delta_for(old.surface.box) or Vec2(0.0, 0.0)
        point = old.point + delta
        box = change.new_index(old.surface.box)
        matches = [
            surface
            for surface in self.world.ooze_planner.surfaces
            if surface.kind is old.surface.kind and surface.box == box
        ]
        if change.removed(old.surface.box) or not matches:
            self.position = self.center() + Vec2(0.0, BODY_OFFSET)
            self.up = Vec2(0.0, -1.0)
            self.follower = None
            self.velocity = Vec2(0.0, 0.0)
            return
        surface = min(matches, key=lambda item: item.closest_point(point).distance_to(point))
        anchor = Anchor(surface, surface.closest_point(point))
        self.follower = RouteFollower(anchor)
        self.position, self.up = anchor.point, surface.normal
        self._replan = 0.0

    def die(self, point: Vec2, push: Vec2) -> None:
        self.dead = True
        self.down_time = 0.0
        self.release_captives()
        self.position = self.center() + Vec2(0.0, BODY_OFFSET)
        self.up = Vec2(0.0, -1.0)
        self.follower = None
        self.velocity = push * 0.15

    def release_captives(self) -> None:
        """Put every living captive back on reachable ground."""
        for man in list(self.engulfed):
            man.free_from_ooze(self.center())
        self.engulfed.clear()
        self._digest.clear()

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        self.time += dt
        self._update_skeletons(dt)
        if self.follower is None:
            self._fall(dt)
        self.rig.update(dt, self.phase, 0.0)
