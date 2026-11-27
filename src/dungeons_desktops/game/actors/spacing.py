"""Shared surface-aware spacing for routed actor packs."""

from collections.abc import Callable, Iterable
from dataclasses import replace

from dungeons_desktops.navigation.planner import Anchor, Planner, Route
from dungeons_desktops.navigation.terrain import Surface


def spread_positions(positions: list[float], low: float, high: float, gap: float) -> list[float]:
    """Closest ordered positions with space between neighbors, bounded by the surface.

    Pool overlapping groups around their average so an isolated actor stays put.
    Very short surfaces use the available room without pushing anyone off an edge.
    """
    if len(positions) < 2:
        return positions[:]
    gap = min(gap, (high - low) / (len(positions) - 1))
    groups: list[tuple[float, int]] = []
    for index, position in enumerate(positions):
        groups.append((position - index * gap, 1))
        while len(groups) > 1 and groups[-2][0] / groups[-2][1] > groups[-1][0] / groups[-1][1]:
            total, count = groups.pop()
            previous, size = groups.pop()
            groups.append((previous + total, size + count))
    ceiling = high - (len(positions) - 1) * gap
    result = []
    for total, count in groups:
        base = min(ceiling, max(low, total / count))
        for _ in range(count):
            result.append(base + len(result) * gap)
    return result


def separate_pack(
    members: Iterable,
    planner: Planner,
    dt: float,
    movable: set,
    gap_for: Callable[[Surface], float],
    speed: float,
) -> None:
    """Gently separate supported pack members without discarding outward routes."""
    groups: dict[int, list] = {}
    for actor in members:
        if actor.dead or actor.held or actor.follower.in_transition:
            continue
        anchor = actor.follower.current_anchor()
        if planner.owns(anchor.surface):
            groups.setdefault(anchor.surface.id, []).append(actor)
    for actors in groups.values():
        surface = actors[0].follower.current_anchor().surface
        actors.sort(key=lambda actor: surface.coord(actor.contact()))
        positions = [surface.coord(actor.contact()) for actor in actors]
        targets = spread_positions(positions, surface.low, surface.high, gap_for(surface))
        for actor, position, target in zip(actors, positions, targets, strict=True):
            if actor not in movable:
                continue
            limit = speed * dt
            distance = min(limit, max(-limit, target - position))
            if abs(distance) < 1e-6:
                continue
            point = surface.point_at(position + distance)
            delta = point - actor.contact()
            remaining = actor.follower.remaining_steps()
            actor.follower.reset(Anchor(surface, point))
            if remaining:
                step = remaining[0]
                if (step.end - point).dot(delta) >= 0.0:
                    length = step.start.distance_to(step.end)
                    duration = step.duration * point.distance_to(step.end) / max(length, 1e-6)
                    first = replace(step, start=point, duration=duration)
                    actor.follower.set_route(Route((first, *remaining[1:])))
                else:
                    actor._replan_wait = 0.0
            actor.locomotion.shift(delta)
            actor._last_contact += delta


def reserve_opening(actor, anchor: Anchor, gap: float) -> Anchor:
    """Reserve the nearest available interval around ``anchor`` for one pack member."""
    surface = anchor.surface
    occupied = []
    for other in actor.pack.goblins:
        if other is actor or other.dead or other.held:
            continue
        here = other.follower.current_anchor()
        if not other.follower.in_transition and here.surface is surface:
            occupied.append(surface.coord(here.point))
        if other.follower.moving and other.goal is not None:
            goal = actor.planner.anchor_near(other.goal, 1.0)
            if goal is not None and goal.surface is surface:
                occupied.append(surface.coord(goal.point))
    desired = surface.coord(anchor.point)
    openings = []
    cursor = surface.low
    for position in sorted(occupied):
        end = min(surface.high, position - gap)
        if cursor <= end:
            openings.append(min(end, max(cursor, desired)))
        cursor = max(cursor, position + gap)
    if cursor <= surface.high:
        openings.append(min(surface.high, max(cursor, desired)))
    if not openings:
        return actor.follower.current_anchor()
    here = surface.coord(actor.contact())
    closest = min(openings, key=lambda position: (abs(position - desired), abs(position - here)))
    return Anchor(surface, surface.point_at(closest))
