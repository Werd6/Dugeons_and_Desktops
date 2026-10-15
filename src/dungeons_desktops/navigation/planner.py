"""Shortest-time routes over terrain surfaces.

Moves along a surface are WALK (walkable), CLIMB (wall side) or HANG (hand over
hand along a ceiling). Moves between surfaces:

- MANTLE: from hands-on-the-lip at the top of a climbable side up onto the walkable surface.
- GRAB: between a walkable surface and the bottom of a climbable side resting on it.
- DROP: off a ledge, a dangling wall bottom, or a ceiling onto a walkable surface below.
- JUMP: up from a walkable surface to a ledge, wall bottom or ceiling within jump height.
- SWING: between a ceiling and a wall side at a corner (round a box's bottom edge, or
  where a wall meets the underside above it), or between two ceilings that meet.

Letting go while hanging (from a wall bottom or a ceiling) may fall much further
than walking off a ledge (`max_hang_drop` against `max_drop`): it is how windows
floating out of jumping reach are reached, and left again.

The planner precomputes the surface graph (surface ends and transition points)
once; each query adds its start and goal and runs Dijkstra on traversal time.
"""

from __future__ import annotations

import heapq
import math
from bisect import bisect_left, insort
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.navigation.terrain import Surface, SurfaceKind, Terrain

CORNER_SLACK = 2.0
"""How close (px) a wall must be to a ceiling's end to swing between them."""


class Move(Enum):
    WALK = "walk"
    CLIMB = "climb"
    HANG = "hang"
    MANTLE = "mantle"
    GRAB = "grab"
    JUMP = "jump"
    DROP = "drop"
    SWING = "swing"


ALONG_MOVES = frozenset({Move.WALK, Move.CLIMB, Move.HANG})
"""Moves along a single surface (the rest go from one surface to another)."""


@dataclass(frozen=True)
class MoveSettings:
    walk_speed: float = 65.0
    climb_speed: float = 40.0
    hang_speed: float = 45.0
    mantle_time: float = 0.7
    grab_time: float = 0.3
    swing_time: float = 0.6
    max_drop: float = 240.0
    max_hang_drop: float = 1000.0
    max_jump: float = 60.0
    gravity: float = 700.0
    edge_clearance: float = 10.0
    hop_penalty: float = 0.0
    """Seconds added to a jump or drop when choosing a route (not to its timing), plus
    `hop_height_penalty` a pixel of its height: high, and it climbs rather than leaps
    wherever it can, and hops the shortest way across where it can't."""
    hop_height_penalty: float = 0.0


@dataclass(frozen=True)
class Anchor:
    surface: Surface
    point: Vec2


@dataclass(frozen=True)
class RouteStep:
    move: Move
    start: Vec2
    end: Vec2
    duration: float
    surface: Surface
    from_surface: Surface


@dataclass(frozen=True)
class Route:
    steps: tuple[RouteStep, ...]

    @property
    def duration(self) -> float:
        return sum(step.duration for step in self.steps)


@dataclass(frozen=True)
class Transition:
    source: Surface
    source_point: Vec2
    target: Surface
    target_point: Vec2
    move: Move
    duration: float


Node = tuple[int, float]


class Planner:
    def __init__(self, terrain: Terrain, settings: MoveSettings | None = None) -> None:
        self.terrain = terrain
        self.settings = settings or MoveSettings()
        self.surfaces = terrain.surfaces
        self._by_id = {surface.id: surface for surface in self.surfaces}
        self.transitions: tuple[Transition, ...] = tuple(self._find_transitions())
        self._coords: dict[int, list[float]] = {}
        self._out: dict[Node, list[tuple[Node, float, Move]]] = {}
        self._neighbors: dict[int, set[int]] = {s.id: set() for s in self.surfaces}
        coords: dict[int, set[float]] = {s.id: {_key(s.low), _key(s.high)} for s in self.surfaces}
        for t in self.transitions:
            a = (t.source.id, _key(t.source.coord(t.source_point)))
            b = (t.target.id, _key(t.target.coord(t.target_point)))
            coords[a[0]].add(a[1])
            coords[b[0]].add(b[1])
            self._out.setdefault(a, []).append((b, t.duration, t.move))
            self._neighbors[a[0]].add(b[0])
        self._coords = {sid: sorted(values) for sid, values in coords.items()}
        self._reach_cache: dict[int, frozenset[int]] = {}

    def anchor_near(
        self, point: Vec2, max_distance: float = math.inf, walk_only: bool = False
    ) -> Anchor | None:
        best: Anchor | None = None
        best_distance = max_distance
        for surface in self.surfaces:
            if walk_only and not surface.walkable:
                continue
            closest = surface.closest_point(point)
            distance = closest.distance_to(point)
            if distance <= best_distance:
                best, best_distance = Anchor(surface, closest), distance
        return best

    def reachable(self, start: Surface) -> frozenset[int]:
        """Ids of every surface some route from `start` gets to (including itself)."""
        cached = self._reach_cache.get(start.id)
        if cached is not None:
            return cached
        seen = {start.id}
        stack = [start.id]
        while stack:
            for neighbor in self._neighbors.get(stack.pop(), ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        result = frozenset(seen)
        self._reach_cache[start.id] = result
        return result

    def owns(self, surface: Surface) -> bool:
        """True if `surface` belongs to this planner's terrain (not a stale one)."""
        return self._by_id.get(surface.id) is surface

    def plan(self, start: Anchor, goal: Anchor) -> Route | None:
        start_node = (start.surface.id, _key(start.surface.coord(start.point)))
        goal_node = (goal.surface.id, _key(goal.surface.coord(goal.point)))
        if goal.surface.id not in self.reachable(start.surface):
            return None
        extra: dict[int, list[float]] = {}
        for sid, coord in (start_node, goal_node):
            line = extra.setdefault(sid, list(self._coords[sid]))
            index = bisect_left(line, coord)
            if index >= len(line) or line[index] != coord:
                insort(line, coord)

        previous: dict[Node, tuple[Node, float, Move]] = {}
        best = {start_node: 0.0}
        queue: list[tuple[float, Node]] = [(0.0, start_node)]
        while queue:
            cost, node = heapq.heappop(queue)
            if node == goal_node:
                break
            if cost > best.get(node, math.inf):
                continue
            for neighbor, edge_cost, move in self._edges(node, extra):
                total = cost + edge_cost
                if move in (Move.JUMP, Move.DROP) and self.settings.hop_penalty > 0.0:
                    height = abs(self._point(neighbor).y - self._point(node).y)
                    total += self.settings.hop_penalty + self.settings.hop_height_penalty * height
                if total < best.get(neighbor, math.inf) - 1e-12:
                    best[neighbor] = total
                    previous[neighbor] = (node, edge_cost, move)
                    heapq.heappush(queue, (total, neighbor))
        if goal_node not in best:
            return None
        return Route(self._build_steps(start_node, goal_node, previous))

    def _edges(
        self, node: Node, extra: dict[int, list[float]]
    ) -> Iterator[tuple[Node, float, Move]]:
        sid, coord = node
        surface = self._by_id[sid]
        move, speed = self._along(surface)
        line = extra.get(sid) or self._coords[sid]
        index = bisect_left(line, coord)
        if index > 0:
            yield (sid, line[index - 1]), (coord - line[index - 1]) / speed, move
        if index + 1 < len(line):
            yield (sid, line[index + 1]), (line[index + 1] - coord) / speed, move
        yield from self._out.get(node, ())

    def _along(self, surface: Surface) -> tuple[Move, float]:
        s = self.settings
        if surface.walkable:
            return Move.WALK, s.walk_speed
        if surface.hanging:
            return Move.HANG, s.hang_speed
        return Move.CLIMB, s.climb_speed

    def _point(self, node: Node) -> Vec2:
        return self._by_id[node[0]].point_at(node[1])

    def _build_steps(self, start_node, goal_node, previous) -> tuple[RouteStep, ...]:
        chain = []
        node = goal_node
        while node != start_node:
            parent, cost, move = previous[node]
            chain.append((parent, node, cost, move))
            node = parent
        chain.reverse()

        steps: list[RouteStep] = []
        for parent, node, cost, move in chain:
            start, end = self._point(parent), self._point(node)
            target, source = self._by_id[node[0]], self._by_id[parent[0]]
            last = steps[-1] if steps else None
            same_direction = (
                last is not None
                and last.move is move
                and move in ALONG_MOVES
                and last.surface.id == target.id
                and (end - start).dot(last.end - last.start) > 0
            )
            if same_direction:
                steps[-1] = RouteStep(
                    move, last.start, end, last.duration + cost, target, last.from_surface
                )
            else:
                steps.append(RouteStep(move, start, end, cost, target, source))
        return tuple(steps)

    # ----- transitions ---------------------------------------------------------

    def _find_transitions(self) -> list[Transition]:
        s = self.settings
        walks = [x for x in self.surfaces if x.walkable]
        sides = [x for x in self.surfaces if x.wall]
        ceilings = [x for x in self.surfaces if x.hanging]
        found: list[Transition] = []

        def both_ways(a: Surface, pa: Vec2, b: Surface, pb: Vec2, move: Move, time: float):
            found.append(Transition(a, pa, b, pb, move, time))
            found.append(Transition(b, pb, a, pa, move, time))

        for side in sides:
            for walk in walks:
                if walk.contains(side.lip):
                    both_ways(
                        side,
                        side.start,
                        walk,
                        walk.closest_point(side.lip),
                        Move.MANTLE,
                        s.mantle_time,
                    )
            resting = [w for w in walks if w.contains(side.end)]
            for walk in resting:
                both_ways(
                    side, side.end, walk, walk.closest_point(side.end), Move.GRAB, s.grab_time
                )
            if not resting:
                found.extend(
                    self._falls(
                        side,
                        side.end,
                        side.end.x + side.normal.x * s.edge_clearance,
                        s.max_hang_drop,
                    )
                )

        for walk in walks:
            found.extend(self._falls(walk, walk.start, walk.start.x - s.edge_clearance))
            found.extend(self._falls(walk, walk.end, walk.end.x + s.edge_clearance))

        for ceiling in ceilings:
            for side in sides:
                corner = self._corner(ceiling, side)
                if corner is not None:
                    both_ways(ceiling, corner[0], side, corner[1], Move.SWING, s.swing_time)
            for other in ceilings:
                meet = (
                    other.id != ceiling.id
                    and abs(other.low - ceiling.high) <= CORNER_SLACK
                    and abs(other.start.y - ceiling.start.y) <= self._hang_depth() * 0.5
                )
                if meet:
                    both_ways(ceiling, ceiling.end, other, other.start, Move.SWING, s.grab_time)
            found.extend(self._ceiling_drops(ceiling, walks))
        return found

    def _hang_depth(self) -> float:
        return self.terrain.hang_depth or 0.0

    def _inset(self, surface: Surface) -> float:
        return min(self.settings.edge_clearance, surface.length * 0.5)

    def _corner(self, ceiling: Surface, side: Surface) -> tuple[Vec2, Vec2] | None:
        """Where a hanger under `ceiling` and a climber on `side` swap, if they meet at
        a corner: round the bottom edge of the wall's own box (the wall stands above
        the grip line) or where the wall goes down from the underside (inside corner)."""
        x = side.start.x
        at_low = abs(x - ceiling.low) <= CORNER_SLACK
        at_high = abs(x - ceiling.high) <= CORNER_SLACK
        if not (at_low or at_high):
            return None
        inset = self._inset(ceiling)
        hang_x = ceiling.low + inset if at_low else ceiling.high - inset
        hang = ceiling.point_at(hang_x)
        grip = ceiling.grip
        left_of_box = side.kind is SurfaceKind.LEFT
        outside = (left_of_box and at_low) or (not left_of_box and at_high)
        if outside:
            if abs(side.wall_bottom - grip) > CORNER_SLACK:
                return None
            return hang, side.end
        if side.wall_bottom <= grip + CORNER_SLACK:
            return None
        feet = min(max(hang.y, side.low), side.high)
        reaches_grip = side.wall_top <= grip + CORNER_SLACK
        if not reaches_grip and abs(feet - hang.y) > self._hang_depth():
            return None
        return hang, side.point_at(feet)

    def _ceiling_drops(self, ceiling: Surface, walks: list[Surface]) -> list[Transition]:
        """Letting go of `ceiling` above each walkable surface it overhangs."""
        spots: set[float] = set()
        for walk in walks:
            if walk.start.y <= ceiling.start.y + 1.0:
                continue
            low, high = max(ceiling.low, walk.low), min(ceiling.high, walk.high)
            if high < low:
                continue
            clear = min(self.settings.edge_clearance, (high - low) * 0.5)
            spots.update(_key(x) for x in (low + clear, high - clear, (low + high) * 0.5))
        found: list[Transition] = []
        for x in sorted(spots):
            found.extend(self._falls(ceiling, ceiling.point_at(x), x, self.settings.max_hang_drop))
        return found

    def _falls(
        self,
        source: Surface,
        point: Vec2,
        landing_x: float,
        max_height: float | None = None,
    ) -> list[Transition]:
        """DROP from `point` to the first walkable surface below, and JUMP back if low enough."""
        s = self.settings
        below = [
            w
            for w in self.surfaces
            if w.walkable and w.start.y > point.y + 1.0 and w.low <= landing_x <= w.high
        ]
        if not below:
            return []
        landing_surface = min(below, key=lambda w: w.start.y)
        landing = landing_surface.point_at(landing_x)
        height = landing.y - point.y
        limit = s.max_drop if max_height is None else max_height
        if height > limit or not self.terrain.column_clear(landing_x, point.y, landing.y):
            return []
        fall_time = math.sqrt(2.0 * height / s.gravity)
        result = [Transition(source, point, landing_surface, landing, Move.DROP, fall_time + 0.2)]
        if height <= s.max_jump:
            result.append(
                Transition(
                    landing_surface, landing, source, point, Move.JUMP, fall_time * 1.4 + 0.3
                )
            )
        return result


def _key(value: float) -> float:
    return round(value, 4)
