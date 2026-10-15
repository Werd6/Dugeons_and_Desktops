"""The intellect devourer: a brain on four clawed legs that bursts out of a dead
thrall's skull and goes after the nearest free adventurer.

It gets around like a goblin (the goblin planner: across window tops, up and down
window sides, along undersides upside down, jumps and drops), scuttling at its own
`CRAWL_SPEED`, and pounces: a ballistic leap at its quarry once he's within
`POUNCE_RANGE`, or whenever it can't route to him but he's within `LEAP_RANGE`. Mid-air
it clings to any window side or underside it hits, or lands on a top or the floor. A
bite does `DEVOURER_DAMAGE` and it springs back off him to go again. With `DEVOURER_HP`
gone it drops off whatever it was on and lies on its back, legs in the air.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.creatures import goblin
from dungeons_desktops.navigation.planner import ALONG_MOVES, Anchor, Move, Planner
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.systems.hunt import Hunt
from dungeons_desktops.systems.mortal import DEVOURER_HP, Mortal
from dungeons_desktops.systems.movement import RouteFollower

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman
    from dungeons_desktops.systems.world import SimWorld

GRAVITY = 900.0
CRAWL_SPEED = {Move.WALK: 95.0, Move.CLIMB: 70.0, Move.HANG: 70.0}
"""Pixels a second along a top, up or down a side, and along an underside."""
SPEED_OF = {
    Move.WALK: goblin.MOVES.walk_speed,
    Move.CLIMB: goblin.MOVES.climb_speed,
    Move.HANG: goblin.MOVES.hang_speed,
}
"""The goblin speeds its routes are timed for."""
STRIDE = 9.0
BODY_HEIGHT = 5.5
"""Brain center out from its feet."""
BODY_RADIUS = 5.5
REPLAN_EVERY = 0.4
GOAL_SNAP = 80.0
POUNCE_RANGE = 60.0
LEAP_RANGE = 150.0
LEAP_COOLDOWN = 1.2
CLING_REACH = 24.0
"""How far from where it hits a window a surface may be for it to cling on."""
DEVOURER_DAMAGE = 1
BITE_MARGIN = 3.0
BITE_COOLDOWN = 0.9
RECOIL = Vec2(110.0, -170.0)
ZERO = Vec2(0.0, 0.0)
UPRIGHT = Vec2(0.0, -1.0)


class Devourer(Mortal):
    max_hp = DEVOURER_HP
    linger = 2.5

    def __init__(
        self, world: SimWorld, position: Vec2, velocity: Vec2 = ZERO, facing: int = 1
    ) -> None:
        self.world = world
        self.position = position
        """Between its feet."""
        self.velocity = velocity
        self.facing = facing
        self.up = UPRIGHT
        """Away from the surface its feet are on (straight up in the air)."""
        self.forward = Vec2(float(facing), 0.0)
        """The way it's crawling, along that surface."""
        self.follower: RouteFollower | None = None
        """Its route while it's on a surface; None in the air."""
        self.hunt = Hunt()
        self.target: Stickman | None = None
        self.phase = 0.0
        self.leap_wait = 0.4
        self.bite_wait = 0.0
        self._replan_wait = 0.0

    @property
    def planner(self) -> Planner:
        return self.world.goblin_planner

    def center(self) -> Vec2:
        return self.position + self.up * BODY_HEIGHT

    @property
    def airborne(self) -> bool:
        return self.follower is None

    @property
    def support(self) -> Surface | None:
        """The surface it's on, if any."""
        return self.follower.current_anchor().surface if self.follower is not None else None

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.leap_wait -= dt
        self.bite_wait -= dt
        target = self.target = self.hunt.update(dt, self.center(), self.world.stickmen)
        if self.follower is None:
            self._fly(dt, cling=True)
        else:
            self._crawl(dt, target)
        if target is not None and self.bite_wait <= 0.0:
            self._bite(target)

    def _crawl(self, dt: float, target: Stickman | None) -> None:
        follower = self.follower
        assert follower is not None
        settled = not follower.in_transition
        if target is not None and settled:
            to = target.center() - self.center()
            if self.leap_wait <= 0.0 and to.length() <= POUNCE_RANGE:
                self._leap(target.center())
                return
            self._replan_wait -= dt
            if self._replan_wait <= 0.0:
                self._replan_wait = REPLAN_EVERY
                if self._go(target.contact()):
                    self.hunt.reached()
                else:
                    self.hunt.unreachable(REPLAN_EVERY, 2.0)
                    if self.leap_wait <= 0.0 and to.length() <= LEAP_RANGE:
                        self._leap(target.center())
                        return
        before = self.position
        step = follower.step
        pace = 1.0
        if step is not None and step.move in CRAWL_SPEED:
            pace = CRAWL_SPEED[step.move] / SPEED_OF[step.move]
        follower.update(dt * pace)
        self._settle()
        moved = self.position - before
        self.phase += moved.length() / STRIDE
        along = Vec2(-self.up.y, self.up.x)
        heading = moved.dot(along) if moved.length() > 0.05 else self.forward.dot(along)
        if abs(heading) < 1e-9:
            heading = along.x * self.facing or 1.0
        self.forward = along if heading > 0 else -along
        if abs(self.forward.x) > 0.5:
            self.facing = 1 if self.forward.x > 0 else -1

    def _go(self, point: Vec2) -> bool:
        follower = self.follower
        assert follower is not None
        anchor = self.planner.anchor_near(point, GOAL_SNAP)
        if anchor is None:
            return False
        start = follower.current_anchor()
        if anchor.surface is start.surface and anchor.point.distance_to(start.point) < 2.0:
            follower.reset(start)
            return True
        route = self.planner.plan(start, anchor)
        if route is None:
            return False
        follower.reset(start)
        follower.set_route(route)
        return True

    def _on(self, surface: Surface, contact: Vec2) -> tuple[Vec2, Vec2]:
        """Its feet and up direction for a goblin's `contact` on `surface`: on the side
        of a window it clings flat to the side, under one it hangs upside down."""
        if surface.hanging:
            return Vec2(contact.x, surface.grip), surface.normal
        if surface.wall:
            return contact, surface.normal
        return contact, UPRIGHT

    def _settle(self) -> None:
        """Feet and up from its route: along a surface, on it; between two, an eased
        crawl over the corner (or the arc of a jump or drop)."""
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is None or step.move in ALONG_MOVES:
            anchor = follower.current_anchor()
            self.position, self.up = self._on(anchor.surface, anchor.point)
            return
        t = 1.0 if step.duration <= 0.0 else clamp(follower.elapsed / step.duration, 0.0, 1.0)
        start, up_start = self._on(step.from_surface, step.start)
        end, up_end = self._on(step.surface, step.end)
        if step.move in (Move.JUMP, Move.DROP):
            arc = follower.contact() - step.start.lerp(step.end, t)
            self.position = start.lerp(end, t) + arc
        else:
            self.position = start.lerp(end, smoothstep(t))
        up = up_start.lerp(up_end, smoothstep(t))
        if up.length() < 0.3:
            up = up_start if t < 0.5 else up_end
        self.up = up.normalized()

    def _leap(self, aim: Vec2) -> None:
        start = self.center()
        self._loose()
        flight = clamp(start.distance_to(aim) / 320.0, 0.3, 0.6)
        self.velocity = (aim - start - Vec2(0.0, 0.5 * GRAVITY * flight * flight)) * (1.0 / flight)
        self.facing = 1 if aim.x >= start.x else -1
        self.leap_wait = LEAP_COOLDOWN

    def _loose(self) -> None:
        """Off its surface and into the air, the brain where it was."""
        center = self.center()
        self.follower = None
        self.up = UPRIGHT
        self.forward = Vec2(float(self.facing), 0.0)
        self.position = center - UPRIGHT * BODY_HEIGHT
        self.velocity = ZERO

    def _attach(self, anchor: Anchor) -> None:
        self.follower = RouteFollower(anchor)
        self.velocity = ZERO
        self._replan_wait = 0.0
        self._settle()
        along = Vec2(-self.up.y, self.up.x)
        self.forward = along if along.x * self.facing >= 0 else -along

    def _fly(self, dt: float, cling: bool) -> None:
        world = self.world
        before = self.position
        self.velocity += Vec2(0.0, GRAVITY * dt)
        after = before + self.velocity * dt
        if not world.left + 2.0 <= after.x <= world.width - 2.0:
            after = Vec2(clamp(after.x, world.left + 2.0, world.width - 2.0), after.y)
            self.velocity = Vec2(0.0, self.velocity.y)
        if world.ceiling is not None and after.y < world.ceiling + 2.0 * BODY_HEIGHT:
            after = Vec2(after.x, world.ceiling + 2.0 * BODY_HEIGHT)
            self.velocity = Vec2(self.velocity.x, max(0.0, self.velocity.y))
        if self.velocity.y >= 0.0:
            crossed = [
                s
                for s in self._walkable()
                if s.low - 1.0 <= after.x <= s.high + 1.0
                and before.y <= s.start.y + 0.5
                and after.y >= s.start.y
            ]
            if crossed:
                surface = min(crossed, key=lambda s: s.start.y)
                self._attach(Anchor(surface, surface.closest_point(Vec2(after.x, surface.start.y))))
                return
        for box in world.boxes:
            body = after + UPRIGHT * BODY_HEIGHT
            if not (box.contains(after) or box.contains(body)) or box.contains(before):
                continue
            if cling:
                anchor = self.planner.anchor_near(after, CLING_REACH)
                if anchor is not None and anchor.surface.box is not None:
                    self._attach(anchor)
                    return
            if before.y - BODY_HEIGHT * 2.0 >= box.bottom - 1.0:
                after = Vec2(after.x, box.bottom + BODY_HEIGHT * 2.0 + 0.5)
                self.velocity = Vec2(self.velocity.x, max(0.0, self.velocity.y))
            else:
                after = Vec2(before.x, after.y)
                self.velocity = Vec2(0.0, self.velocity.y)
        if after.y >= world.floor_y:
            floor = [s for s in self._walkable() if abs(s.start.y - world.floor_y) < 0.5]
            if floor:
                nearest = min(floor, key=lambda s: abs(clamp(after.x, s.low, s.high) - after.x))
                self._attach(Anchor(nearest, nearest.closest_point(Vec2(after.x, world.floor_y))))
                return
            after = Vec2(after.x, world.floor_y)
        self.position = after

    def _walkable(self) -> list[Surface]:
        return [s for s in self.planner.surfaces if s.walkable]

    def _bite(self, target: Stickman) -> None:
        if not target.hits(self.center(), BITE_MARGIN):
            return
        push = Vec2(self.facing * 120.0, -60.0)
        target.hurt(
            DEVOURER_DAMAGE, self.center(), push, "devourer", "Devoured by an intellect devourer!"
        )
        self.bite_wait = BITE_COOLDOWN
        away = 1 if self.center().x >= target.center().x else -1
        self._loose()
        self.velocity = Vec2(away * RECOIL.x, RECOIL.y)

    # ----- terrain -------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        """Ride the window it's on; fall if it closes or moves out from under it."""
        if self.follower is None:
            return
        anchor = self.follower.current_anchor()
        box = anchor.surface.box
        if change.removed(box):
            self._loose()
            return
        point = anchor.point + (change.delta_for(box) or ZERO)
        moved = self.planner.anchor_near(point, 12.0)
        if moved is None:
            self.position = self.position + (point - anchor.point)
            self._loose()
            return
        self._attach(moved)

    # ----- death ---------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        self.dead = True
        self.down_time = 0.0
        self._loose()
        self.velocity = push * 0.4 + Vec2(0.0, -80.0)

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        if self.follower is None:
            self._fly(dt, cling=False)
