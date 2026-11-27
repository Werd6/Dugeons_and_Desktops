"""Floating along a stickman's routes: what the mind flayer
share.

A `Floater` routes exactly like a stickman (its `planner`: across window tops, up and
down window sides, along undersides, jumps and drops) but never climbs or walks: it
poses itself over the spot its route puts it at (`feet`), hovering `hover` over a top,
floating `wall_gap` out from a side, hanging `ceiling_gap` under an underside, and
glides smoothly from one to the next, leaning into the way it's going. It hunts a
quarry (`_seek`), and with nobody about it wanders off to a random reachable spot now
and then.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.base import GOAL_SNAP, Actor, surface_below
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import ALONG_MOVES, Anchor, Move
from dungeons_desktops.navigation.terrain import Surface

if TYPE_CHECKING:
    from dungeons_desktops.game.actors.hunting import Hunt
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.rig.biped import BipedLayout

GLIDE = {
    Move.CLIMB: stick_figure.MOVES.walk_speed / stick_figure.MOVES.climb_speed,
    Move.HANG: stick_figure.MOVES.walk_speed / stick_figure.MOVES.hang_speed,
}
"""It floats up a wall or along an underside as fast as it floats across a top, not at
a climbing stickman's crawl."""


class Floater(Actor):
    pace = 0.7
    """How fast it gets through its routes, relative to a stickman walking."""
    hover = 4.0
    """How high its bottom floats over a top or the floor."""
    wall_gap = 12.0
    """How far out from a window side its body floats."""
    ceiling_gap = 5.0
    """How far below an underside the top of its head floats."""
    settle_rate = 14.0
    """How quickly its body eases onto the spot its route puts it at."""
    max_lean = 0.32
    lean_rate = 6.0
    turn_speed = 6.0
    """Sideways speed above which it faces the way it's going."""
    replan_every = 0.5
    wander_wait = (2.0, 4.0)
    patience = 3.0
    """How long it keeps trying for a quarry it can't route to before giving up on him."""
    wanders = True

    def __init__(self, world: World, layout: BipedLayout, anchor: Anchor, height: float) -> None:
        super().__init__(world, layout, anchor)
        self.height = height
        """Its bottom to the top of its head."""
        self._replan_wait = 0.0
        self._wander_wait = 0.0
        self.stranded = False
        """Whether the last try for its quarry found no route to him."""
        self.feet = self._float_target()
        """Its bottom: where its body floats right now."""
        self.drift = Vec2(0.0, 0.0)
        """How fast its body is floating."""
        self.lean = 0.0
        """Radians its body tilts toward +x."""
        self._facing = self.follower.facing

    # ----- floating ------------------------------------------------------------

    def _place(self, surface: Surface, contact: Vec2) -> Vec2:
        """Where its feet float for a stickman's `contact` on `surface`."""
        if surface.wall:
            return Vec2(contact.x + surface.normal.x * self.wall_gap, contact.y - self.hover)
        if surface.hanging:
            return Vec2(contact.x, surface.grip + self.ceiling_gap + self.height)
        return Vec2(contact.x, contact.y - self.hover)

    def _float_target(self) -> Vec2:
        """Where its route has it now; a jump, drop, climb-over or swing is a straight,
        eased glide from where it left to where it lands."""
        follower = self.follower
        step = follower.step
        if step is None or step.move in ALONG_MOVES:
            anchor = follower.current_anchor()
            return self._place(anchor.surface, anchor.point)
        t = 1.0 if step.duration <= 0.0 else clamp(follower.elapsed / step.duration, 0.0, 1.0)
        start = self._place(step.from_surface, step.start)
        return start.lerp(self._place(step.surface, step.end), smoothstep(t))

    def _glide(self, dt: float, free: bool, look_at: Vec2 | None) -> None:
        """Ease the body onto its route spot, lean into the drift, and (when `free` to)
        face the way it's going, or out from a wall it hangs on (toward `look_at` if
        that's off to one side)."""
        before = self.feet
        self.feet = before.lerp(self._float_target(), min(1.0, dt * self.settle_rate))
        moved = (self.feet - before) / dt if dt > 0.0 else Vec2(0.0, 0.0)
        self.drift = self.drift.lerp(moved, min(1.0, dt * 10.0))
        speed = stick_figure.MOVES.walk_speed * self.pace
        lean = clamp(self.drift.x / speed, -1.0, 1.0) * self.max_lean
        self.lean += (lean - self.lean) * min(1.0, dt * self.lean_rate)
        if not free:
            return
        if abs(self.drift.x) > self.turn_speed:
            self._facing = 1 if self.drift.x > 0 else -1
        elif self.follower.current_anchor().surface.wall and not self.follower.in_transition:
            wall = self.follower.current_anchor().surface
            if look_at is not None and abs(look_at.x - self.feet.x) > 1.0:
                self._facing = 1 if look_at.x > self.feet.x else -1
            else:
                self._facing = 1 if wall.normal.x > 0 else -1

    def _face(self, point: Vec2) -> None:
        if abs(point.x - self.feet.x) > 1.0:
            self._facing = 1 if point.x > self.feet.x else -1

    def reanchor(self, delta: Vec2, carried: bool, box: int | None = None) -> None:
        super().reanchor(delta, carried, box)
        if carried:
            self.feet += delta

    def _pace(self) -> float:
        step = self.follower.step
        return self.pace * (GLIDE.get(step.move, 1.0) if step is not None else 1.0)

    # ----- heading out -----------------------------------------------------------

    def _seek(self, target: Stickman | None, hunt: Hunt) -> None:
        """Route to `target` (giving up on him through `hunt` if there's no way), or with
        nobody to go for, wander now and then."""
        self.stranded = False
        if target is not None:
            if not self._go(target.contact()):
                self.stranded = True
                hunt.unreachable(self.replan_every, self.patience)
            else:
                hunt.reached()
            return
        if not self.wanders or self.follower.moving:
            return
        self._wander_wait -= self.replan_every
        if self._wander_wait > 0.0:
            return
        random = self.world.random
        self._wander_wait = random.uniform(*self.wander_wait)
        start = self.follower.current_anchor()
        reachable = self.planner.reachable(start.surface)
        spots = [s for s in self.planner.surfaces if s.walkable and s.id in reachable]
        if spots:
            surface = random.choices(spots, weights=[s.length + 1.0 for s in spots])[0]
            self._go(surface.point_at(random.uniform(surface.low, surface.high)))

    def _go(self, point: Vec2) -> bool:
        anchor = self.planner.anchor_near(point, GOAL_SNAP)
        if anchor is None:
            return False
        start = self.follower.current_anchor()
        if anchor.surface is start.surface and anchor.point.distance_to(start.point) < 2.0:
            self.halt()
            return True
        route = self.planner.plan(start, anchor)
        if route is None:
            return False
        self.goal = anchor.point
        self.follower.reset(start)
        self.follower.set_route(route)
        return True

    def _travel(self, dt: float, target: Stickman | None, hunt: Hunt, rooted: bool) -> None:
        """Replan toward the quarry every so often and float along the route, unless
        `rooted` (busy with something where it is)."""
        self._replan_if_needed()
        if rooted:
            return
        self._replan_wait -= dt
        if self._replan_wait <= 0.0 and not self.follower.in_transition:
            self._replan_wait = self.replan_every
            self._seek(target, hunt)
        self.follower.update(dt * self._pace())

    # ----- terrain -------------------------------------------------------------

    def lost_support(self, contact: Vec2) -> None:
        anchor = surface_below(self.planner, contact)
        self.follower.reset(anchor)
        if anchor.point.y - contact.y > 2.0:
            self.drop_from(contact)
