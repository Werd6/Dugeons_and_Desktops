import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.defenders.zombies.spacing import personal_space, spread_positions
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind


def crowd(kind, count=6):
    world = SimWorld([Rect(300, 150, 300, 250)], 700, 1400)
    surface = next(s for s in world.zombie_planner.surfaces if s.kind is kind)
    point = surface.point_at((surface.low + surface.high) / 2)
    zombies = [world.add_zombie(point) for _ in range(count)]
    for zombie in zombies:
        zombie.follower.reset(Anchor(surface, point))
        zombie.locomotion.teleport(zombie.follower.command())
        zombie._last_contact = point
    return world, surface, zombies


@pytest.mark.parametrize(
    "kind", [SurfaceKind.FLOOR, SurfaceKind.LEFT, SurfaceKind.RIGHT, SurfaceKind.CEILING]
)
def test_overlapping_zombies_separate_on_their_own_surface(kind):
    world, surface, zombies = crowd(kind)
    for _ in range(480):
        world.zombie_pack.separate(1 / 60, set(zombies))
    positions = sorted(surface.coord(z.contact()) for z in zombies)
    assert all(
        b - a >= personal_space(surface) - 0.01
        for a, b in zip(positions, positions[1:], strict=False)
    )
    for zombie in zombies:
        assert zombie.follower.current_anchor().surface is surface
        assert surface.contains(zombie.contact())
        assert zombie.pose().root.distance_to(zombie.contact()) < 40


@pytest.mark.parametrize("start", [0, 25, 50])
def test_overcrowded_ledge_uses_available_space_without_pushing_anyone_off(start):
    result = spread_positions([start] * 20, 0, 50, 14)
    assert result[0] >= 0 and result[-1] <= 50
    assert all(b > a for a, b in zip(result, result[1:], strict=False))
    assert result[-1] - result[0] == pytest.approx(50)


def test_spacing_does_not_move_isolated_zombies():
    assert spread_positions([20, 100, 100, 200], 0, 300, 14) == [20, 93, 107, 200]


def test_immobilized_zombie_stays_put_while_others_make_room():
    world, _, zombies = crowd(SurfaceKind.FLOOR, 2)
    pinned = zombies[0]
    original = pinned.contact()
    for _ in range(180):
        world.zombie_pack.separate(1 / 60, {zombies[1]})
    assert pinned.contact() == original
    assert zombies[1].contact().distance_to(original) > 13.9


def test_spacing_keeps_routes_that_already_lead_away_from_the_crowd():
    world, surface, zombies = crowd(SurfaceKind.FLOOR, 2)
    for zombie, offset in zip(zombies, (-100, 100), strict=True):
        assert zombie._go(zombie.contact() + Vec2(offset, 0))
    destinations = [z.follower.remaining_steps()[-1].end for z in zombies]
    world.zombie_pack.separate(1 / 60, set(zombies))
    for zombie, destination in zip(zombies, destinations, strict=True):
        assert zombie.follower.moving
        assert zombie.follower.remaining_steps()[-1].end == destination
        assert zombie.follower.current_anchor().surface is surface


def test_held_zombies_do_not_displace_the_pack():
    world, _, zombies = crowd(SurfaceKind.FLOOR, 2)
    zombies[0].pick_up(zombies[0].center())
    positions = [z.contact() for z in zombies]
    world.zombie_pack.separate(0.5, set(zombies))
    assert [z.contact() for z in zombies] == positions


def test_large_horde_can_reserve_more_than_the_old_fixed_number_of_slots():
    world = SimWorld([], 700, 1400)
    zombies = [world.add_zombie(Vec2(100 + index * 16, 700)) for index in range(24)]
    for zombie in zombies:
        assert zombie._go(Vec2(900, 700))
    goals = sorted(z.goal.x for z in zombies)
    assert all(b - a >= 13.99 for a, b in zip(goals, goals[1:], strict=False))


def test_horde_spreads_out_and_still_attacks_during_a_chase():
    world = SimWorld([], 600, 1400)
    zombies = [world.add_zombie(Vec2(400, 600)) for _ in range(8)]
    prey = world.add_stickman(Vec2(520, 600))
    prey.paralyze(30)
    hits = 0
    for _ in range(12 * 60):
        world.advance(1 / 60)
        hits += prey.damage
        prey.heal(100)
    positions = sorted(z.contact().x for z in zombies)
    assert all(b - a >= 13 for a, b in zip(positions, positions[1:], strict=False))
    assert hits > 0
