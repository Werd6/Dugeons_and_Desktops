"""Gun selection, damage, recoil timing, retreat, and interrupted combat."""

import math

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.heroes.the_hunter.combat import Gun
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange

DT = 1 / 60


def advance(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def scene(facing=1, distance=240):
    world = SimWorld([], 300, 4000)
    hero = world.add_stickman(Vec2(2000, 300), "hero_ranger")
    target = enemy(world, 2000 + facing * distance)
    return world, hero, target


def enemy(world, x, height=0):
    target = world.add_goblin(Vec2(x, 300), "flag")
    target.max_hp = 1000
    target.locomotion.pose.root -= Vec2(0, height)
    return target


@pytest.mark.parametrize("facing", [-1, 1])
def test_sniper_has_global_range_and_cannot_bypass_30_second_cooldown(facing, monkeypatch):
    _, hero, target = scene(facing, 1400)
    hits = []
    damage = hero._damage
    time = 0.0

    def record(*args):
        hits.append((time, hero.weapon.gun, args[2]))
        damage(*args)

    monkeypatch.setattr(hero, "_damage", record)
    for frame in range(60 * 32):
        time = frame * DT
        hero.attack()  # Preview attack hotkey must still respect each cooldown.
        hero.update(DT)
        if frame == 30:
            assert target.damage == 10 and hero.sniper_cooldown > 29
        if frame == 120:
            assert (hero.contact().x - 2000) * facing > 0  # Closes for pistols.
    sniper = [(time, damage) for time, gun, damage in hits if gun is Gun.SNIPER]
    assert len(sniper) == 2
    assert sniper[1][0] - sniper[0][0] >= 30
    assert all(damage == 10 for _, damage in sniper)


@pytest.mark.parametrize("facing", [-1, 1])
def test_shotgun_hits_cone_once_then_recoils_before_rolling(facing):
    world, hero, target = scene(facing, 60)
    second = enemy(world, 2000 + facing * 95, height=15)
    outside_angle = enemy(world, 2000 + facing * 60, height=70)
    behind = enemy(world, 2000 - facing * 80)
    distant = enemy(world, 2000 + facing * 170)
    ally = world.add_stickman(Vec2(2000 + facing * 80, 300), "fighter")
    hero.attack()
    advance(hero, 0.15)
    assert target.damage == 0 and hero.roll is None
    assert hero.contact().x == 2000
    advance(hero, 0.1)
    assert target.damage == second.damage == 4
    assert outside_angle.damage == behind.damage == distant.damage == ally.damage == 0
    assert hero.shotgun_blast is not None
    assert hero.shotgun_cooldown > 5.9 and hero.sniper_cooldown == 0
    assert hero.roll is None and hero.weapon_held and hero.contact().x == 2000
    advance(hero, 0.15)
    assert hero.roll is not None and (hero.contact().x - 2000) * facing < 0
    advance(hero, 0.6)
    assert hero.roll is None
    assert hero.contact().x == pytest.approx(2000 - facing * 95)
    assert target.damage == second.damage == 4
    assert hero.shotgun_blast is None


@pytest.mark.parametrize("facing", [-1, 1])
def test_pistols_fire_half_damage_from_both_hands_while_retreating_then_hold(facing):
    world, hero, target = scene(facing, 120)
    hero.sniper_cooldown = hero.shotgun_cooldown = 100
    advance(hero, 0.15)
    assert target.damage == 0.5 and hero.weapon.gun is Gun.PISTOLS
    first = hero.shot[0]
    advance(hero, 0.15)
    assert target.damage == 1
    assert hero.shot[0].distance_to(first) > 1
    assert (hero.contact().x - 2000) * facing < 0 and hero.facing == facing
    assert hero.weapon.backpedalling
    advance(hero, 3)
    held_at = hero.contact()
    damage = target.damage
    assert world.closest_part(target, hero.center()).distance_to(hero.center()) >= 215
    advance(hero, 1)
    assert hero.contact().distance_to(held_at) < 1
    assert target.damage > damage and hero.facing == facing
    target.locomotion.pose.root -= Vec2(facing * 90, 0)
    advance(hero, 0.3)
    assert (hero.contact().x - held_at.x) * facing < 0


def test_pistols_do_not_fire_outside_range_but_walk_toward_target():
    _, hero, target = scene(distance=900)
    hero.sniper_cooldown = hero.shotgun_cooldown = 100
    advance(hero, 4)
    assert target.damage == 0 and hero.contact().x > 2100


def test_shotgun_becomes_available_after_six_seconds_independently(monkeypatch):
    world, hero, target = scene(distance=65)
    hero.sniper_cooldown = 100
    hits = []
    damage = hero._damage
    time = 0.0

    def record(*args):
        if hero.weapon.gun is Gun.SHOTGUN:
            hits.append(time)
        damage(*args)

    monkeypatch.setattr(hero, "_damage", record)
    for frame in range(60 * 8):
        time = frame * DT
        # Keep the enemy close as the Hunter retreats, without attacking him.
        anchor = target.planner.anchor_near(hero.contact() + Vec2(65, 0), walk_only=True)
        target.follower.reset(anchor)
        target.locomotion.teleport(target.follower.command())
        hero.update(DT)
    assert len(hits) == 2 and 6 <= hits[1] - hits[0] < 6.7
    assert hero.sniper_cooldown == pytest.approx(92)
    assert world.monster_kills == 0


@pytest.mark.parametrize("interruption", ["stun", "death"])
@pytest.mark.parametrize("time", [0.1, 0.25, 0.5])
def test_interrupting_windup_recoil_or_roll_stops_attack_and_movement(interruption, time):
    _, hero, target = scene(distance=65)
    advance(hero, time)
    damage = target.damage
    if interruption == "stun":
        hero.paralyze(2)
    else:
        hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "test", "defeated")
    advance(hero, 1)
    assert hero.roll is None and hero._roll_after is None
    assert target.damage == damage


def test_pistols_kill_on_fractional_health_without_a_second_ghost_hit():
    world, hero, target = scene()
    hero.sniper_cooldown = hero.shotgun_cooldown = 100
    target.damage = target.max_hp - 0.5
    advance(hero, 0.4)
    assert target.hp == 0 and target in world.fallen and world.monster_kills == 1
    assert target.damage == target.max_hp


@pytest.mark.parametrize("change", ["move", "remove"])
def test_rolling_on_a_narrow_window_respects_edges_and_survives_terrain_change(change):
    world = SimWorld([Rect(180, 100, 80, 200)], 300, 600, ceiling=0)
    hero = world.add_stickman(Vec2(195, 100), "hero_ranger")
    target = world.add_goblin(Vec2(245, 100), "flag")
    target.max_hp = 1000
    advance(hero, 0.4)
    assert hero.roll is not None and 180 < hero.contact().x < 195
    if change == "move":
        world.apply_terrain(TerrainChange(moves={0: Vec2(20, -10)}),
                            [Rect(200, 90, 80, 200)])
        advance(hero, 0.6)
        assert 200 < hero.contact().x < 215 and hero.contact().y == 90
    else:
        world.goblins.remove(target)
        world.apply_terrain(TerrainChange(remap={0: None}), [])
        advance(hero, 4)
    assert hero.animated and hero.hp == hero.max_hp and hero.fade == 0
    assert hero.roll is None and world.planner.owns(hero.follower.current_anchor().surface)


@pytest.mark.parametrize("facing", [-1, 1])
def test_backpedal_feet_stay_reachable_and_knees_keep_their_normal_bend(facing):
    _, hero, _ = scene(facing, 65)
    hero.sniper_cooldown = hero.shotgun_cooldown = 100
    for frame in range(90):
        hero.update(DT)
        if frame < 15:  # Let the idle-to-retreat blend finish.
            continue
        transforms = hero.transforms()
        for leg in hero.layout.legs:
            hip = transforms[leg.bones[0]].start
            knee = transforms[leg.bones[0]].end
            foot = transforms[leg.bones[-1]].end
            assert foot.y <= 300.01
            assert abs(foot.x - hip.x) < hero.layout.leg_length * 0.8
            assert (knee - hip).cross(foot - knee) * facing >= -1e-5
            assert all(math.isfinite(v) for v in (foot.x, foot.y))
