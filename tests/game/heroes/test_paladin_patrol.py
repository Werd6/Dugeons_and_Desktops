"""Broad screen patrols, longer pursuit range, and a pace the squad can follow."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.heroes.hero_paladin.aura import AURA_RADIUS, keep_with_squad
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange

DT = 1 / 60


def finish_route(actor):
    route = actor.follower.route
    assert route is not None
    actor.follower.update(route.duration + 1)
    actor.locomotion.teleport(actor.follower.command())


@pytest.mark.parametrize("left,top", [(0, 0), (-1200, -300)])
def test_patrol_circles_the_screen_on_real_surfaces(left, top):
    world = SimWorld([], top + 700, left + 1200, left=left, ceiling=top)
    hero = world.add_stickman(Vec2(left + 600, world.floor_y), "hero_paladin", wander=True)
    goals = []
    for _ in range(8):
        hero.update(1)
        assert hero.goal_reachable and hero.goal == hero._wander_destination
        route = hero.follower.route
        assert route and all(hero.planner.owns(step.surface) for step in route.steps)
        goals.append(hero.goal - Vec2(left, top))
        finish_route(hero)
    assert any(p.x < 100 for p in goals) and any(p.x > 1100 for p in goals)
    assert any(p.y < 100 for p in goals) and any(p.y > 600 for p in goals)
    # From the bottom, the clockwise circuit proceeds left, top, right, bottom.
    assert goals[0].x < 600
    assert goals[2].y < 350
    assert goals[4].x > 600
    assert goals[6].y > 350


def test_patrol_uses_window_tops_and_replans_when_terrain_changes():
    window = Rect(300, 250, 600, 450)
    world = SimWorld([window], 700, 1200, ceiling=0)
    hero = world.add_stickman(Vec2(600, 250), "hero_paladin", wander=True)
    used_window = False
    for _ in range(8):
        hero._pick_wander_goal()
        used_window |= hero.follower.route.steps[-1].surface.box == 0
        finish_route(hero)
    assert used_window
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    for _ in range(120):
        hero.update(DT)
    hero.halt()
    hero._pick_wander_goal()
    assert hero.follower.moving and hero.hp == hero.max_hp
    assert all(hero.planner.owns(step.surface) for step in hero.follower.route.steps)


def test_floor_only_preview_still_patrols_both_sides():
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(500, 300), "hero_paladin", wander=True)
    goals = []
    for _ in range(8):
        hero._pick_wander_goal()
        goals.append(hero.goal)
        finish_route(hero)
    assert all(p.y == 300 for p in goals)
    assert min(p.x for p in goals) < 100 and max(p.x for p in goals) > 900


def test_patrol_yields_to_a_distant_enemy_then_resumes():
    world = SimWorld([], 300, 1400)
    hero = world.add_stickman(Vec2(100, 300), "hero_paladin", wander=True)
    regular = world.add_stickman(Vec2(100, 300), "paladin")
    hero.update(DT)
    target = world.add_goblin(Vec2(650, 300), "flag")
    assert not regular._seek(1)
    hero.update(0.6)
    assert hero.quarry is target and hero.goal != hero._wander_destination
    assert hero.follower.moving and not hero.weapon.busy and target.damage == 0
    assert hero.calling.reach == regular.calling.reach == 30
    world.goblins.remove(target)
    finish_route(hero)
    hero.update(1)
    assert hero.quarry is None and hero.follower.moving
    assert hero.goal == hero._wander_destination


def test_enemies_beyond_extended_range_do_not_interrupt_patrol():
    world = SimWorld([], 300, 1400)
    hero = world.add_stickman(Vec2(100, 300), "hero_paladin", wander=True)
    world.add_goblin(Vec2(1050, 300), "flag")
    hero.update(DT)
    assert hero.quarry is None and hero.follower.moving
    assert hero.goal == hero._wander_destination


def test_manual_control_does_not_start_an_automatic_patrol():
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(500, 300), "hero_paladin")
    hero.update(DT)
    assert not hero.follower.moving and hero.goal is None
    destination = Vec2(700, 300)
    hero.set_goal(destination)
    hero.update(DT)
    assert hero.goal == destination and hero.patrol.sector is None


def test_walks_at_ninety_percent_of_normal_adventurer_speed():
    world = SimWorld([], 300, 1400)
    hero = world.add_stickman(Vec2(100, 300), "hero_paladin")
    regular = world.add_stickman(Vec2(100, 300), "paladin")
    for actor in (hero, regular):
        actor.set_goal(Vec2(1200, 300))
    for _ in range(60):
        world.advance(DT)
    assert hero.contact().x - 100 == pytest.approx((regular.contact().x - 100) * 0.9)


def test_squad_can_follow_the_patrol_across_the_screen_ceiling():
    world = SimWorld([], 600, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(500, 600), "hero_paladin")
    ally = world.add_stickman(Vec2(550, 600), "fighter", wander=True)
    ally._pick_wander_goal()
    assert ally._aura_leader is hero
    ceiling = next(s for s in hero.planner.surfaces if s.hanging and s.box is None)
    anchor = hero.planner.anchor_near(ceiling.point_at(500))
    hero.follower.reset(anchor)
    hero.locomotion.teleport(hero.follower.command())
    keep_with_squad(ally, 1)
    assert ally.goal.distance_to(hero.center()) < AURA_RADIUS
    assert ally.follower.route.steps[-1].surface.hanging
    assert ally.follower.route.steps[-1].surface.id == ceiling.id
    finish_route(ally)
    assert ally.protector is hero
