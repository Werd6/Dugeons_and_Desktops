"""Live protection and idle squad movement, without coupling actors to hero classes."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dungeons_desktops.navigation.planner import Anchor

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman

AURA_RADIUS = 140.0
SQUAD_RADIUS = AURA_RADIUS * 0.8
REPATH_EVERY = 0.5


def protector(ally: Stickman) -> Stickman | None:
    if (
        ally.thrall or ally.gone or ally.hp <= 0
        or not (ally.animated or ally.knocked) or getattr(ally, "is_shadow_clone", False)
    ):
        return None
    guards = [
        hero for hero in getattr(ally.world, "heroes", ())
        if hero is not ally and getattr(hero, "aura_active", False)
    ]
    if not guards:
        return None
    center = ally.center()
    candidates = [
        hero for hero in guards if hero.center().distance_to(center) <= AURA_RADIUS
    ]
    return min(candidates, key=lambda hero: hero.center().distance_to(center), default=None)


def squad_leader(ally: Stickman) -> Stickman | None:
    if ally.thrall or ally.variant == "hero_paladin" or getattr(ally, "is_shadow_clone", False):
        ally._aura_leader = None
        ally._aura_surface_id = None
        return None
    leader = ally._aura_leader
    if (
        leader not in getattr(ally.world, "heroes", ())
        or not getattr(leader, "aura_active", False)
    ):
        leader = ally._aura_leader = protector(ally)
        if leader is None:
            ally._aura_surface_id = None
    return leader


def wander_inside(ally: Stickman, leader: Stickman) -> bool:
    """Choose an idle destination inside the aura on the leader's current surface."""
    start = ally.follower.current_anchor()
    reachable = ally.planner.reachable(start.surface)
    center = leader.center()
    leader_surface = leader.follower.current_anchor().surface
    surface = next(
        (candidate for candidate in ally.planner.surfaces if candidate.id == leader_surface.id),
        None,
    )
    if surface is None or surface.id not in reachable:
        ally.goal = ally._wander_destination = None
        ally._aura_surface_id = None
        ally.halt()
        return False
    gap = abs(surface.start.x - center.x) if surface.wall else abs(surface.start.y - center.y)
    if gap >= SQUAD_RADIUS:
        ally.goal = ally._wander_destination = None
        ally._aura_surface_id = None
        ally.halt()
        return False
    half = math.sqrt(SQUAD_RADIUS ** 2 - gap ** 2)
    coordinate = surface.coord(center)
    low, high = max(surface.low, coordinate - half), min(surface.high, coordinate + half)
    for _ in range(8):
        point = surface.point_at(ally.world.random.uniform(low, high))
        route = ally.planner.plan(start, Anchor(surface, point))
        if route is not None and route.steps:
            ally.goal = ally._wander_destination = point
            ally._aura_surface_id = surface.id
            ally.goal_reachable = True
            ally.follower.reset(start)
            ally.follower.set_route(route)
            return True
    ally.goal = ally._wander_destination = None
    ally._aura_surface_id = surface.id if start.surface.id == surface.id else None
    ally.halt()
    return False


def keep_with_squad(ally: Stickman, dt: float) -> None:
    leader = squad_leader(ally)
    ally._aura_repath = max(0.0, ally._aura_repath - dt)
    if leader is None or ally.follower.in_transition or ally._aura_repath > 0:
        return
    # An explicit destination stays under player control. Only replace idle routes.
    if ally.follower.moving and ally.goal != ally._wander_destination:
        return
    leader_surface_id = leader.follower.current_anchor().surface.id
    wrong_surface = ally._aura_surface_id != leader_surface_id
    outside_aura = (
        ally.goal is not None and ally.goal.distance_to(leader.center()) > SQUAD_RADIUS
    )
    if wrong_surface or outside_aura:
        ally._aura_repath = REPATH_EVERY
        wander_inside(ally, leader)
