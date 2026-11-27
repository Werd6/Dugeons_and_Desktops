import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.defenders.zombies.spacing import personal_space
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind

DT = 1 / 60


def crowd(kind: SurfaceKind, count: int = 4):
    world = SimWorld([Rect(300, 150, 300, 250)], 700, 1400, seed=12)
    surface = next(candidate for candidate in world.planner.surfaces if candidate.kind is kind)
    point = surface.point_at((surface.low + surface.high) / 2)
    knights = [world.add_graveknight(point) for _ in range(count)]
    for knight in knights:
        knight.follower.reset(Anchor(surface, point))
        knight.locomotion.teleport(knight.follower.command())
        knight._last_contact = point
    return world, surface, knights


@pytest.mark.parametrize(
    "kind", [SurfaceKind.FLOOR, SurfaceKind.LEFT, SurfaceKind.RIGHT, SurfaceKind.CEILING]
)
def test_overlapping_graveknights_separate_on_their_supporting_surface(kind):
    world, surface, knights = crowd(kind)

    for _ in range(480):
        world.graveknight_pack.separate(DT, set(knights))

    positions = sorted(surface.coord(knight.contact()) for knight in knights)
    assert all(
        following - current >= personal_space(surface) - 0.01
        for current, following in zip(positions, positions[1:], strict=False)
    )
    assert all(knight.follower.current_anchor().surface is surface for knight in knights)
    assert all(surface.contains(knight.contact()) for knight in knights)


def test_overcrowded_short_ledge_uses_only_the_available_width():
    world = SimWorld([Rect(400, 300, 36, 150)], 700, 1000, seed=13)
    surface = next(
        candidate
        for candidate in world.planner.surfaces
        if candidate.kind is SurfaceKind.TOP and candidate.box == 0
    )
    point = surface.point_at((surface.low + surface.high) / 2)
    knights = [world.add_graveknight(point) for _ in range(4)]
    for knight in knights:
        knight.follower.reset(Anchor(surface, point))
        knight.locomotion.teleport(knight.follower.command())
        knight._last_contact = point

    for _ in range(480):
        world.graveknight_pack.separate(DT, set(knights))

    positions = sorted(surface.coord(knight.contact()) for knight in knights)
    assert positions[0] >= surface.low and positions[-1] <= surface.high
    assert all(a < b for a, b in zip(positions, positions[1:], strict=False))
    assert positions[-1] - positions[0] == pytest.approx(surface.length, abs=0.01)


def test_held_and_transitioning_graveknights_are_not_moved():
    world, surface, knights = crowd(SurfaceKind.FLOOR, 3)
    held, transitioning, movable = knights
    held.pick_up(held.center())
    transitioning.drop_from(transitioning.contact() - Vec2(0.0, 100.0))
    assert transitioning.follower.in_transition
    before = {knight: knight.contact() for knight in knights}

    world.graveknight_pack.separate(0.5, {movable})

    assert held.contact() == before[held]
    assert transitioning.contact() == before[transitioning]
    assert movable.contact() == before[movable]
    assert movable.follower.current_anchor().surface is surface


def test_spacing_preserves_routes_that_already_lead_out_of_the_stack():
    world, surface, knights = crowd(SurfaceKind.FLOOR, 2)
    for knight, offset in zip(knights, (-100.0, 100.0), strict=True):
        assert knight._go(knight.contact() + Vec2(offset, 0.0))
    destinations = [knight.follower.remaining_steps()[-1].end for knight in knights]

    world.graveknight_pack.separate(DT, set(knights))

    for knight, destination in zip(knights, destinations, strict=True):
        assert knight.follower.moving
        assert knight.follower.remaining_steps()[-1].end == destination
        assert knight.follower.current_anchor().surface is surface


def test_squad_destacks_while_advancing_and_firing():
    world = SimWorld([], 600, 1400, seed=21)
    knights = [world.add_graveknight(Vec2(300.0, 600.0)) for _ in range(4)]
    prey = world.add_stickman(Vec2(800.0, 600.0), "hero_fighter")
    prey.paralyze(30.0)
    fired = False

    for _ in range(8 * 60):
        world.advance(DT)
        fired |= any(arrow.owner in knights for arrow in world.spells.arrows)

    positions = sorted(knight.contact().x for knight in knights)
    assert all(
        following - current >= personal_space(knights[0].follower.current_anchor().surface) - 0.01
        for current, following in zip(positions, positions[1:], strict=False)
    )
    assert all(knight.contact().x > 300.0 for knight in knights)
    assert fired
