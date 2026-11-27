import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.graveknights.actor import (
    GRAVEKNIGHT_STATS,
    GraveknightRole,
)
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1 / 60
FLOOR = 600.0


@pytest.mark.parametrize("role", (GraveknightRole.ARCHER, GraveknightRole.MAGE))
def test_ranged_graveknights_fire_from_their_standoff_instead_of_charging(role):
    world = SimWorld([], FLOOR, 1400, seed=41)
    knight = world.add_graveknight(Vec2(100.0, FLOOR), role)
    prey = world.add_stickman(Vec2(700.0, FLOOR), "hero_fighter")
    prey.paralyze(30.0)
    knight.cooldown = 0.0
    start = knight.contact()

    for _ in range(12 * 60):
        world.advance(DT)

    distance = knight.contact().distance_to(prey.contact())
    assert knight.contact().x > start.x + 300.0
    assert distance == pytest.approx(GRAVEKNIGHT_STATS[role].standoff, abs=18.0)
    assert prey.damage > 0


@pytest.mark.parametrize("role", (GraveknightRole.ARCHER, GraveknightRole.MAGE))
def test_ranged_graveknights_make_space_when_their_target_gets_too_close(role):
    world = SimWorld([], FLOOR, 900, seed=42)
    knight = world.add_graveknight(Vec2(500.0, FLOOR), role)
    prey = world.add_stickman(Vec2(520.0, FLOOR), "hero_fighter")
    prey.paralyze(30.0)
    start = knight.contact()

    for _ in range(4 * 60):
        world.advance(DT)

    assert knight.contact().x < start.x - 40.0
    assert knight.contact().distance_to(prey.contact()) == pytest.approx(
        GRAVEKNIGHT_STATS[role].standoff,
        abs=18.0,
    )
