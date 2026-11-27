import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.defenders.graveknights.actor import (
    GRAVEKNIGHT_PACK,
    GRAVEKNIGHT_ROSTER,
    GRAVEKNIGHT_STATS,
    GraveknightRole,
)
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1 / 60
FLOOR = 600.0


def advance_until(world, condition, seconds=10.0):
    for _ in range(round(seconds / DT)):
        world.advance(DT)
        if condition():
            return True
    return False


def test_desktop_defender_arrives_as_a_squad_of_four():
    session = DesktopSession(
        Rect(0, 0, 1400, 900),
        Rect(0, 30, 1400, 800),
        FakeWindowSource(),
        defenders=("graveknights",),
        max_stickmen=0,
        seed=4,
    )

    assert GRAVEKNIGHT_PACK == 4
    assert len(session.graveknights) == GRAVEKNIGHT_PACK
    assert tuple(knight.role for knight in session.graveknights) == GRAVEKNIGHT_ROSTER
    assert all(
        knight.hp == GRAVEKNIGHT_STATS[knight.role].hp
        for knight in session.graveknights
    )
    assert session.defender_health == 1.0


def test_graveknight_fires_while_advancing():
    world = SimWorld([], FLOOR, 1400, seed=3)
    knight = world.add_graveknight(Vec2(100, FLOOR), GraveknightRole.ARCHER)
    prey = world.add_stickman(Vec2(400, FLOOR))
    prey.paralyze(30)
    knight.cooldown = 0.0
    start = knight.contact()
    movement_while_drawing = []
    previous = start
    saw_arrow = False

    for _ in range(round(6 / DT)):
        world.advance(DT)
        if knight.weapon.busy:
            movement_while_drawing.append(knight.contact().distance_to(previous))
        previous = knight.contact()
        saw_arrow |= any(arrow.owner is knight for arrow in world.spells.arrows)
        if saw_arrow and knight.contact().x > start.x + 15:
            break

    assert saw_arrow
    assert knight.contact().x > start.x + 15
    assert sum(movement_while_drawing) > 5


def test_graveknights_share_a_quarry_and_advance_as_a_squad():
    world = SimWorld([], FLOOR, 1400, seed=7)
    knights = [world.add_graveknight(Vec2(100 + 18 * i, FLOOR)) for i in range(4)]
    farther = world.add_stickman(Vec2(1100, FLOOR))
    quarry = world.add_stickman(Vec2(700, FLOOR))
    farther.paralyze(30)
    quarry.paralyze(30)
    starts = [knight.contact().distance_to(quarry.contact()) for knight in knights]

    assert advance_until(world, lambda: all(knight.target is not None for knight in knights))
    assert {knight.target for knight in knights} == {quarry}
    for _ in range(round(2 / DT)):
        world.advance(DT)
    distances = [knight.contact().distance_to(quarry.contact()) for knight in knights]
    assert all(after < before for before, after in zip(starts, distances, strict=True))


def test_graveknight_can_be_targeted_killed_and_despawned():
    world = SimWorld([], FLOOR, 900, seed=8)
    knight = world.add_graveknight(Vec2(400, FLOOR))

    assert knight in world.monsters() and knight in world.actors
    assert world.monster_at(knight.center()) is knight
    assert world.hurt_monster(knight, knight.hp, knight.center(), Vec2(40, -20))
    assert knight.dead and knight.ragdoll is not None
    assert knight not in world.graveknights and knight in world.fallen
    assert advance_until(world, lambda: knight not in world.fallen, seconds=4.0)


def test_squad_health_bar_counts_all_four_graveknights():
    session = DesktopSession(
        Rect(0, 0, 1400, 900),
        Rect(0, 30, 1400, 800),
        FakeWindowSource(),
        defenders=("graveknights",),
        max_stickmen=0,
        seed=9,
    )
    first = session.graveknights[0]
    maximum = sum(knight.max_hp for knight in session.graveknights)

    session.hurt_monster(first, first.hp, first.center(), Vec2(0, 0))

    assert session.defender_health == pytest.approx((maximum - first.max_hp) / maximum)
