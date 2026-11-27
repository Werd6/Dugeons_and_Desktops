"""Leap Smash must work on desktop surfaces, not just an empty floor."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.heroes.the_mighty.combat import Attack
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def wall_scene(side):
    world = SimWorld([Rect(300, 200, 400, 250)], 600, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(100, 600), "hero_barbarian")
    x, target_x = (300, 370) if side == "left" else (700, 630)
    surface = next(s for s in hero.planner.surfaces if s.wall and s.box == 0 and s.start.x == x)
    hero.follower.reset(Anchor(surface, surface.point_at(300)))
    hero.locomotion.teleport(hero.follower.command())
    target = world.add_goblin(Vec2(target_x, 200), "flag")
    target.max_hp = 1000
    return world, hero, target


def land(hero):
    for _ in range(120):
        hero.update(DT)
        if hero.leap is None:
            return
    pytest.fail("Leap never landed")


@pytest.mark.parametrize("side", ["left", "right"])
def test_launches_from_wall_clears_the_lip_and_smashes_on_top(side):
    _, hero, target = wall_scene(side)
    hero.boulder_cooldown = 6
    hero.attack()
    assert hero.weapon.action is Attack.LEAP and hero.leap is not None
    assert hero.locomotion.mode is PoseMode.CLIMB
    end = hero.leap.landing.point
    assert hero._clear_leap(hero.leap)
    for _ in range(30):
        hero.update(DT)
    assert hero.locomotion.mode is PoseMode.AIR and hero.contact().y < 200
    land(hero)
    assert hero.contact() == end and hero.contact().y == 200
    assert hero.facing == (1 if side == "left" else -1)
    assert target.damage == 8
    assert hero.boulder_cooldown > 0


def test_leaps_down_from_a_window_underside_without_hitting_the_roof():
    world = SimWorld([Rect(300, 200, 400, 250)], 600, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(100, 600), "hero_barbarian")
    surface = next(s for s in hero.planner.surfaces if s.hanging and s.box == 0)
    hero.follower.reset(Anchor(surface, surface.point_at(400)))
    hero.locomotion.teleport(hero.follower.command())
    target = world.add_goblin(Vec2(540, 600), "flag")
    hero.attack()
    assert hero.locomotion.mode is PoseMode.HANG
    assert hero.leap is not None and hero._clear_leap(hero.leap)
    assert hero.leap.height == 0
    land(hero)
    assert hero.contact() == Vec2(520, 600) and target.damage == 8


def test_uses_lower_arc_when_a_regular_leap_would_hit_a_window_bottom():
    world = SimWorld([Rect(200, 100, 400, 230)], 400, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(350, 400), "hero_barbarian")
    target = world.add_goblin(Vec2(510, 400), "flag")
    hero.attack()
    assert hero.leap is not None and 0 < hero.leap.height < 30
    assert hero._clear_leap(hero.leap)
    land(hero)
    assert target.damage == 8


def test_finds_a_solid_landing_beside_a_body_part_overhanging_a_window():
    world = SimWorld([Rect(50, 200, 200, 200), Rect(300, 200, 400, 250)], 600, 1000)
    hero = world.add_stickman(Vec2(180, 200), "hero_barbarian")
    leap = hero._plan_leap(Vec2(295, 180))
    assert leap is not None and leap.landing.surface.box == 1
    assert leap.landing.point == Vec2(307, 200)
    assert hero._clear_leap(leap)


def test_moving_departure_wall_carries_the_windup_and_landing():
    world, hero, _ = wall_scene("left")
    hero.attack()
    hero.update(0.1)
    start = hero.leap.start
    end = hero.leap.landing.point
    delta = Vec2(20, -10)
    world.apply_terrain(TerrainChange(moves={0: delta}), [world.boxes[0].moved(20, -10)])
    assert hero.leap.start == start + delta
    assert hero.leap.landing.point == end + delta
    assert hero.contact() == Vec2(320, 290)
    land(hero)
    assert hero.animated and hero.contact() == end + delta


@pytest.mark.parametrize("defender", ["minotaur", "chimera"])
def test_live_desktop_combat_uses_leap_smash_from_climbing_or_hanging(defender):
    session = DesktopSession(
        Rect(0, 0, 1200, 800),
        Rect(0, 30, 1200, 720),
        FakeWindowSource([WindowRecord(1, Rect(160, 200, 800, 500))]),
        seed=3,
        defenders=(defender,),
        max_stickmen=0,
    )
    hero = session.spawn_at_edge("left", variant="hero_barbarian")
    for _ in range(60 * 20):
        before = hero.locomotion.mode
        session.advance(DT)  # Advance the enemies, attacks, terrain navigation, and hero together.
        if hero.leap is not None:
            assert before in (PoseMode.CLIMB, PoseMode.HANG)
            assert hero.weapon.action is Attack.LEAP
            break
    else:
        pytest.fail("The live desktop fight never selected Leap Smash")
    airborne = False
    for _ in range(90):
        session.advance(DT)
        airborne |= hero.locomotion.mode is PoseMode.AIR
        if hero.leap is None:
            break
    assert airborne and hero.leap is None
    assert any(impact.ground for impact in hero.combat.impacts)
