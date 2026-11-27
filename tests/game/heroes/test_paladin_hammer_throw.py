"""Retaliation throws one real hammer without consuming melee hits or Smite."""

import pytest
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.hero_paladin.hammer_throw import THROW_DAMAGE, Phase
from dungeons_desktops.game.heroes.hero_paladin.render import draw_paladin_effects
from dungeons_desktops.game.heroes.hero_paladin.smite import HAMMER_DAMAGE
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.render.scene import draw_actors

DT = 1 / 60


def scene(distance=180):
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(400, 300), "hero_paladin")
    target = world.add_goblin(Vec2(400 + distance, 300), "flag")
    target.max_hp = 100
    return world, hero, target


def advance(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def hit(hero, amount=1, source="test"):
    return hero.hurt(amount, hero.center(), Vec2(0, 0), source, "defeated")


def until(hero, condition):
    for _ in range(240):
        if condition():
            return
        hero.update(DT)
    pytest.fail("Hammer did not reach the expected phase")


def place(actor, x):
    anchor = actor.planner.anchor_near(Vec2(x, 300), walk_only=True)
    actor.follower.reset(anchor)
    actor.locomotion.teleport(actor.follower.command())


@pytest.mark.parametrize("side", [-1, 1])
def test_damage_throws_at_nearest_non_melee_enemy_in_either_direction(side):
    world, hero, target = scene(side * 180)
    near = world.add_goblin(Vec2(400 + side * 15, 300), "flag")
    farther = world.add_goblin(Vec2(400 + side * 240, 300), "flag")
    hit(hero)
    assert hero.hammer_throw.phase is Phase.WINDUP
    assert hero.hammer_throw.target is target
    assert not hero.weapon.hammer_away and target.damage == 0
    advance(hero, 0.3)
    assert hero.hammer_throw.phase is Phase.OUTWARD and hero.weapon.hammer_away
    assert hero.facing == side and target.damage == 0
    until(hero, lambda: hero.hammer_throw.phase is Phase.RETURN)
    assert target.damage == THROW_DAMAGE and near.damage == farther.damage == 0
    until(hero, lambda: not hero.hammer_throw.active)
    assert not hero.weapon.hammer_away and not hero.weapon.busy
    assert hero.melee_hits == 0 and hero.smite is None


def test_no_throw_without_damage_or_when_only_melee_enemies_exist():
    _, hero, target = scene(15)
    hit(hero)
    assert not hero.hammer_throw.active and not hero.hammer_throw.pending
    place(target, 600)
    advance(hero, 0.2)
    assert not hero.hammer_throw.active
    hit(hero)
    assert hero.hammer_throw.active


def test_enemy_just_outside_normal_melee_reach_is_eligible():
    _, hero, target = scene(35)
    distance = target.center().distance_to(hero.center())
    assert hero.calling.reach < distance < hero.calling.reach + 12
    hit(hero)
    assert hero.hammer_throw.target is target


@pytest.mark.parametrize("blocked", ["grace", "aura", "zero", "lethal", "thrall", "stun"])
def test_blocked_lethal_or_incapacitated_hits_do_not_trigger_throw(blocked):
    world, hero, target = scene()
    source, amount = "test", 1
    if blocked == "grace":
        source = "dragon"
        hero._grace[source] = 1
    elif blocked == "aura":
        world.add_stickman(Vec2(350, 300), "hero_paladin")
    elif blocked == "zero":
        amount = 0
    elif blocked == "lethal":
        amount = hero.max_hp
    elif blocked == "thrall":
        hero.enthrall()
    else:
        hero.paralyze(2)
    hit(hero, amount, source)
    advance(hero, 0.5)
    assert not hero.hammer_throw.active and not hero.hammer_throw.pending
    assert target.damage == 0


def test_repeated_hits_cannot_duplicate_hammer_and_new_hit_can_trigger_after_return():
    _, hero, target = scene()
    hit(hero)
    advance(hero, 0.3)
    flight = hero.hammer_throw
    for _ in range(5):
        hit(hero)
        hero.update(DT)
        assert hero.hammer_throw is flight
    until(hero, lambda: not flight.active)
    advance(hero, 0.4)
    assert target.damage == THROW_DAMAGE and not flight.pending
    hit(hero)
    until(hero, lambda: not flight.active)
    assert target.damage == 2 * THROW_DAMAGE


def test_damage_during_smite_waits_for_swing_and_does_not_change_hit_counter():
    world, hero, target = scene()
    melee = world.add_minotaur(Vec2(425, 300))
    ally = world.add_stickman(Vec2(350, 300), "fighter")
    ally.damage = 4
    hero.melee_hits = 2
    hero.attack()
    advance(hero, 0.1)
    hit(hero)
    assert hero.hammer_throw.pending and not hero.hammer_throw.active
    advance(hero, 0.5)
    assert hero.melee_hits == 3 and melee.damage == 1 + 3 * HAMMER_DAMAGE and ally.damage == 2
    until(hero, lambda: hero.hammer_throw.phase is Phase.OUTWARD)
    assert hero.hammer_throw.target is target and melee.damage == 1 + 3 * HAMMER_DAMAGE
    until(hero, lambda: not hero.hammer_throw.active)
    assert target.damage == THROW_DAMAGE and hero.melee_hits == 3 and ally.damage == 2
    hero.attack()
    advance(hero, 0.4)
    assert hero.melee_hits == 4 and melee.damage == 2 + 3 * HAMMER_DAMAGE


def test_queued_throw_preserves_manual_route_paused_by_the_previous_swing():
    world, hero, _ = scene()
    melee = world.add_goblin(Vec2(415, 300), "flag")
    melee.max_hp = 1
    destination = Vec2(800, 300)
    hero.set_goal(destination)
    hero.attack()
    assert hero._resume_route
    hit(hero)
    until(hero, lambda: hero.hammer_throw.phase is Phase.OUTWARD)
    until(hero, lambda: not hero.hammer_throw.active)
    advance(hero, 0.2)
    assert hero.goal == destination and hero.follower.moving
    assert hero.contact().x > 400


def test_airborne_target_is_tracked_and_moving_target_is_hit_once():
    world, hero, grounded = scene()
    world.goblins.remove(grounded)
    target = world.add_dragon(Vec2(510, 180), facing=1)
    hit(hero)
    assert hero.hammer_throw.target is target
    advance(hero, 0.3)
    target._shift(Vec2(140, 30))
    until(hero, lambda: hero.hammer_throw.phase is Phase.RETURN)
    assert target.damage == THROW_DAMAGE
    place(hero, 350)
    until(hero, lambda: not hero.hammer_throw.active)
    assert target.damage == THROW_DAMAGE
    hand = hero.transforms()[hero.weapon.hand_chain.bones[-1]].end
    assert hero.hammer_throw.point.distance_to(hand) < 1e-6


def test_target_entering_melee_before_release_cancels_throw():
    _, hero, target = scene()
    hit(hero)
    advance(hero, 0.1)
    place(target, 415)
    advance(hero, 0.2)
    assert not hero.hammer_throw.active and not hero.weapon.hammer_away
    assert target.damage == 0 and hero.melee_hits == 0


def test_vanished_target_makes_hammer_return_without_hitting_another_enemy():
    world, hero, target = scene()
    extra = world.add_goblin(Vec2(650, 300), "flag")
    hit(hero)
    advance(hero, 0.3)
    world.goblins.remove(target)
    until(hero, lambda: not hero.hammer_throw.active)
    assert extra.damage == target.damage == 0 and not hero.weapon.hammer_away


@pytest.mark.parametrize("timing", [0.1, 0.35])
def test_death_or_stun_cleans_up_weapon_and_prevents_ghost_hits(timing):
    _, hero, target = scene()
    hit(hero)
    advance(hero, timing)
    if timing < 0.3:
        hero.paralyze(2)
    else:
        hit(hero, hero.max_hp)
    advance(hero, 1)
    assert target.damage == 0 and not hero.hammer_throw.active
    assert not hero.weapon.hammer_away and not hero.weapon.throwing


def test_kill_credits_hero_and_hammer_never_hits_on_return():
    world, hero, target = scene()
    target.max_hp = THROW_DAMAGE
    hit(hero)
    until(hero, lambda: hero.hammer_throw.phase is Phase.RETURN)
    assert target not in world.goblins and target in world.fallen
    assert world.monster_kills == 1
    extra = world.add_goblin(Vec2(500, 300), "flag")
    until(hero, lambda: not hero.hammer_throw.active)
    assert extra.damage == 0 and hero.melee_hits == 0


def test_render_throw_with_shield_without_mutating_projectile():
    world, hero, target = scene()
    hit(hero)
    advance(hero, 0.4)
    image = QImage(1000, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    before = (hero.hammer_throw.point, hero.hammer_throw.angle, target.damage)
    painter = QPainter(image)
    draw_actors(painter, (), world.stickmen)
    draw_paladin_effects(painter, world.heroes)
    assert painter.opacity() == 1
    painter.end()
    assert before == (hero.hammer_throw.point, hero.hammer_throw.angle, target.damage)
    point = hero.hammer_throw.point
    assert any(
        image.pixelColor(x, y).alpha()
        for x in range(int(point.x) - 10, int(point.x) + 11)
        for y in range(int(point.y) - 10, int(point.y) + 11)
    )
