"""Follows a planned route over time and tells the locomotion rig what to do.

The follower owns where the character is (its contact point and surface). The
rig only turns that into a pose. Steps along a surface (WALK, CLIMB, HANG) can be
interrupted for replanning at any moment; transitions between surfaces (MANTLE,
GRAB, SWING, JUMP, DROP) always finish first.
"""

from __future__ import annotations

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.navigation.planner import ALONG_MOVES, Anchor, Move, Route, RouteStep
from dungeons_desktops.navigation.terrain import Surface
from dungeons_desktops.rig.locomotion import DEFAULT_BLEND, LocomotionInput, PoseMode, Wall

TRANSITION_MOVES = frozenset({Move.MANTLE, Move.GRAB, Move.SWING, Move.JUMP, Move.DROP})


def surface_key(surface: Surface) -> tuple:
    return (surface.kind, surface.box)


def wall_of(surface: Surface) -> Wall:
    return Wall(surface.start.x, surface.wall_top, surface.wall_bottom)


class RouteFollower:
    def __init__(self, anchor: Anchor) -> None:
        self.anchor = anchor
        self.route: Route | None = None
        self.index = 0
        self.elapsed = 0.0
        self.facing = anchor.surface.facing if anchor.surface.wall else 1

    @property
    def step(self) -> RouteStep | None:
        return self.route.steps[self.index] if self.route is not None else None

    @property
    def moving(self) -> bool:
        return self.route is not None

    @property
    def in_transition(self) -> bool:
        step = self.step
        return step is not None and step.move in TRANSITION_MOVES

    def remaining_steps(self) -> tuple[RouteStep, ...]:
        return self.route.steps[self.index :] if self.route is not None else ()

    def reset(self, anchor: Anchor) -> None:
        self.anchor = anchor
        self.route = None
        self.index = 0
        self.elapsed = 0.0
        if anchor.surface.wall:
            self.facing = anchor.surface.facing

    def set_route(self, route: Route | None) -> None:
        self.route = route if route is not None and route.steps else None
        self.index = 0
        self.elapsed = 0.0

    def carry_transition(self, delta: Vec2) -> None:
        """The surface the current transition lands on moved by `delta`: land there
        instead, and stop after it (the rest of the route is on the old terrain)."""
        step = self.step
        if step is None or step.move not in TRANSITION_MOVES:
            return
        moved = RouteStep(
            step.move, step.start, step.end + delta, step.duration, step.surface, step.from_surface
        )
        elapsed = self.elapsed
        self.set_route(Route((moved,)))
        self.elapsed = elapsed

    def current_anchor(self) -> Anchor:
        """Where the character is right now, if it is on a surface."""
        step = self.step
        if step is not None and step.move in ALONG_MOVES:
            return Anchor(step.surface, self.contact())
        return self.anchor

    def contact(self) -> Vec2:
        step = self.step
        if step is None:
            return self.anchor.point
        t = self._progress(step)
        if step.move in ALONG_MOVES:
            return step.start.lerp(step.end, t)
        if step.move in (Move.MANTLE, Move.GRAB, Move.SWING):
            return step.end
        dx, dy = step.end.x - step.start.x, step.end.y - step.start.y
        if step.move is Move.DROP:
            return Vec2(step.start.x + dx * min(1.0, t * 1.6), step.start.y + dy * t * t)
        return Vec2(step.start.x + dx * smoothstep(t), step.start.y + dy * (1.0 - (1.0 - t) ** 2))

    def update(self, dt: float) -> LocomotionInput:
        if self.route is not None:
            self.elapsed += dt
            while self.route is not None and self.elapsed >= self.route.steps[self.index].duration:
                finished = self.route.steps[self.index]
                self.elapsed -= finished.duration
                self.anchor = Anchor(finished.surface, finished.end)
                self.index += 1
                if self.index >= len(self.route.steps):
                    self.route = None
                    self.index = 0
                    self.elapsed = 0.0
        return self.command()

    def command(self) -> LocomotionInput:
        step = self.step
        if step is None:
            return self._on_surface(self.anchor.surface, self.anchor.point)

        contact = self.contact()
        if step.move in (Move.WALK, Move.HANG):
            self._face_along(step)
            return self._on_surface(step.surface, contact)
        if step.move is Move.CLIMB:
            return self._on_surface(step.surface, contact)
        if step.move in (Move.MANTLE, Move.GRAB, Move.SWING):
            side = step.surface if step.surface.wall else step.from_surface
            if side.wall:
                self.facing = side.facing
            if step.surface.hanging:
                self._face_along(step)
            return self._on_surface(step.surface, contact, blend=step.duration)

        target = step.surface
        if target.wall:
            self.facing = target.facing
        else:
            self._face_along(step)
        return LocomotionInput(
            PoseMode.AIR,
            contact,
            self.facing,
            ("air", id(step)),
            rising=step.move is Move.JUMP,
        )

    def _face_along(self, step: RouteStep) -> None:
        dx = step.end.x - step.start.x
        if abs(dx) > 1e-9:
            self.facing = 1 if dx > 0 else -1

    def _on_surface(self, surface: Surface, contact: Vec2, blend: float = DEFAULT_BLEND):
        if surface.walkable:
            return LocomotionInput(
                PoseMode.WALK, contact, self.facing, surface_key(surface), blend=blend
            )
        if surface.hanging:
            return LocomotionInput(
                PoseMode.HANG,
                contact,
                self.facing,
                surface_key(surface),
                blend=blend,
                grip=surface.grip,
            )
        self.facing = surface.facing
        return LocomotionInput(
            PoseMode.CLIMB,
            contact,
            self.facing,
            surface_key(surface),
            wall=wall_of(surface),
            blend=blend,
        )

    def _progress(self, step: RouteStep) -> float:
        return 1.0 if step.duration <= 0.0 else clamp(self.elapsed / step.duration, 0.0, 1.0)
