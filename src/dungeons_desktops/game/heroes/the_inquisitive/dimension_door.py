"""The Lich's repositioning rules, adapted to a gnome targeting defenders."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.lich.actor import (
    CAST_IDEAL,
    CAST_MAX,
    CAST_MIN,
    CAST_SLACK,
    CLUSTER_DOOR,
    CLUSTER_GROWTH,
    CLUSTER_RADIUS,
    DOOR_CROWD,
    DOOR_MIN_JUMP,
    DOOR_RANGE,
    DOOR_ROUTE_TIME,
)
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.heroes.the_inquisitive.actor import Iggy

HEIGHT = 25.0
HALF_WIDTH = 7.5


def valid_landing(hero: Iggy, anchor: Anchor) -> bool:
    surface, point = anchor.surface, anchor.point
    if not hero.planner.owns(surface) or not surface.walkable or not surface.contains(point):
        return False
    if hero.world.ceiling is not None and point.y - HEIGHT < hero.world.ceiling:
        return False
    return not any(
        box.left < point.x + HALF_WIDTH and box.right > point.x - HALF_WIDTH
        and box.top < point.y - 0.1 and box.bottom > point.y - HEIGHT
        for box in hero.world.boxes
    )


def door_spot(hero: Iggy, target: object) -> Anchor | None:
    aim = hero.world.locate(target)
    if aim is None:
        return None
    choices = []
    for surface in hero.planner.surfaces:
        if not surface.walkable or surface.length < HALF_WIDTH * 2:
            continue
        rise = surface.start.y - 9 - aim.y
        if abs(rise) > CAST_MAX:
            continue
        reach = math.sqrt(max(0, CAST_IDEAL ** 2 - rise ** 2))
        for side in (-1, 1):
            for offset in (0, -20, 20, -40, 40):
                x = aim.x + side * reach + offset
                if not surface.low + HALF_WIDTH <= x <= surface.high - HALF_WIDTH:
                    continue
                anchor = Anchor(surface, Vec2(x, surface.start.y))
                chest = anchor.point - Vec2(0, 9)
                distance = chest.distance_to(aim)
                if (
                    not CAST_MIN <= distance <= CAST_MAX
                    or anchor.point.distance_to(hero.contact()) < DOOR_MIN_JUMP
                    or not valid_landing(hero, anchor)
                    or hero.world.monsters_near(chest, DOOR_CROWD)
                ):
                    continue
                steps = max(1, int(distance / 6))
                blocked = any(
                    box.contains(chest.lerp(aim, i / steps))
                    for i in range(1, steps) for box in hero.world.boxes
                )
                score = abs(distance - CAST_IDEAL) + (80 if blocked else 0)
                score += abs(anchor.point.y - aim.y) * 0.05
                choices.append((score, anchor))
    return min(choices, key=lambda pair: pair[0])[1] if choices else None


def choose_door(hero: Iggy) -> tuple[object, Anchor] | None:
    enemies = hero.world.monsters_near(hero.center(), math.inf)
    if not enemies:
        return None
    nearest, nearest_point = enemies[0]
    groups = [
        [(foe, at) for foe, at in enemies if at.distance_to(point) <= CLUSTER_RADIUS]
        for _, point in enemies
    ]
    group = max(groups, key=lambda group: (len(group), -group[0][1].distance_to(hero.center())))
    crowd = (
        len(group) >= CLUSTER_DOOR and len(group) >= len(groups[0]) + CLUSTER_GROWTH
        and all(foe is not nearest for foe, _ in group)
    )
    target, point = nearest, nearest_point
    if crowd:
        middle = Vec2(
            sum(at.x for _, at in group) / len(group), sum(at.y for _, at in group) / len(group)
        )
        target, point = min(group, key=lambda pair: pair[1].distance_to(middle))
    distance = point.distance_to(hero.center())
    if distance <= CAST_MAX + CAST_SLACK:
        return None
    landing = door_spot(hero, target)
    if landing is None:
        return None
    if not crowd and distance <= DOOR_RANGE:
        route = hero.planner.plan(hero.follower.current_anchor(), landing)
        if route is not None and route.duration <= DOOR_ROUTE_TIME:
            return None
    return target, landing


def carry_anchor(hero: Iggy, anchor: Anchor, change: TerrainChange) -> Anchor | None:
    if change.removed(anchor.surface.box):
        return None
    point = anchor.point + (change.delta_for(anchor.surface.box) or Vec2(0, 0))
    box = change.new_index(anchor.surface.box)
    surface = next((
        surface for surface in hero.planner.surfaces
        if surface.kind is anchor.surface.kind and surface.box == box
        and surface.contains(point, 2)
    ), None)
    return Anchor(surface, surface.closest_point(point)) if surface is not None else None
