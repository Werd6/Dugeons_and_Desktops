"""Distance selection, attack timing, allegiance, rage, and interrupted leaps."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.heroes.the_mighty.combat import Attack
from dungeons_desktops.game.heroes.the_mighty.render import draw_mighty_effects
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange

DT = 1 / 60


def scene(distance=30, boxes=()):
    world = SimWorld(list(boxes), 300, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_barbarian")
    target = world.add_goblin(Vec2(100 + distance, 300), "flag")
    target.max_hp = 1000
    return world, hero, target


def advance(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


@pytest.mark.parametrize(
    "distance,attack",
    [
        (30, Attack.MELEE),
        (150, Attack.LEAP),
        (330, Attack.BOULDER),
    ],
)
def test_selects_attack_by_distance(distance, attack):
    _, hero, _ = scene(distance)
    hero.attack()
    assert hero.weapon.action is attack and hero.weapon.busy


def test_no_attack_when_target_is_out_of_range():
    _, hero, _ = scene(650)
    advance(hero, 0.5)
    assert not hero.weapon.busy and hero.leap is None and not hero.combat.boulders


def test_every_third_melee_is_a_single_massive_area_hit_that_spares_allies():
    world, hero, target = scene()
    extra = world.add_goblin(Vec2(155, 300), "flag")
    extra.max_hp = 1000
    ally = world.add_stickman(Vec2(130, 300), "barbarian")
    hero.attack()
    advance(hero, 2.2)
    assert hero.weapon.action is Attack.SWING
    assert hero.melee_count == 2 and target.damage == 4 and extra.damage == 0
    advance(hero, 0.15)
    assert hero.melee_count == 3 and target.damage == 16 and extra.damage == 12
    assert ally.damage == hero.damage == 0
    advance(hero, 0.3)
    assert target.damage == 16 and extra.damage == 12


def test_boulder_releases_from_hand_arcs_and_survives_caster_death():
    world, hero, target = scene(330)
    ally = world.add_stickman(Vec2(430, 300), "barbarian")
    hero.attack()
    advance(hero, 0.5)
    assert not hero.combat.boulders
    advance(hero, 0.1)
    assert len(hero.combat.boulders) == 1
    rock = hero.combat.boulders[0]
    assert rock.velocity.y < 0
    start = rock.position
    hero.hurt(100, hero.center(), Vec2(0, 0), "test", "defeated")
    advance(hero, 0.1)
    assert rock.position.x > start.x and rock.position.y < start.y
    advance(hero, 1.4)
    assert target.damage == 6 and ally.damage == 0
    assert not hero.combat.boulders


def test_leap_has_airborne_arc_and_only_deals_damage_on_landing():
    _, hero, target = scene(150)
    hero.attack()
    advance(hero, 0.5)
    assert hero.contact().y < 275 and 100 < hero.contact().x < 230
    assert target.damage == 0
    advance(hero, 0.3)
    assert hero.leap is None and hero.contact() == Vec2(230, 300)
    assert target.damage == 8 and len(hero.combat.impacts) == 1
    advance(hero, 0.2)
    assert target.damage == 8


def test_obstructed_leap_uses_boulder_instead():
    _, hero, _ = scene(150, [Rect(160, 100, 30, 200)])
    hero.attack()
    assert hero.leap is None and hero.weapon.action is Attack.BOULDER


@pytest.mark.parametrize("facing", [-1, 1])
@pytest.mark.parametrize("rage", [False, True])
def test_mighty_swing_blade_meets_ground_at_the_damage_frame(facing, rage):
    _, hero, _ = scene(facing * 30)
    if rage:
        hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
    hero.melee_count = 2
    hero.attack()
    advance(hero, 0.55)
    blade = hero.weapon_strokes()[1].shape
    assert abs(max(point.y for point in blade) - hero.contact().y) < 3 * hero.size_multiplier


def test_distance_is_reconsidered_after_a_throw():
    _, hero, target = scene(330)
    hero.attack()
    advance(hero, 1.3)
    assert not hero.weapon.busy
    assert hero.boulder_cooldown > 0
    anchor = target.planner.anchor_near(Vec2(130, 300), walk_only=True)
    target.follower.reset(anchor)
    target.locomotion.teleport(target.follower.command())
    hero.attack()
    assert hero.weapon.action is Attack.MELEE


def test_stunned_leap_lands_without_an_attack():
    _, hero, target = scene(150)
    hero.attack()
    advance(hero, 0.4)
    hero.paralyze(2)
    advance(hero, 0.7)
    assert hero.leap is None and hero.contact().y == 300
    assert target.damage == 0 and not hero.combat.impacts


@pytest.mark.parametrize("condition", ["stun", "blind", "thrall", "death"])
def test_interrupted_throw_does_not_release(condition):
    _, hero, target = scene(330)
    hero.attack()
    advance(hero, 0.2)
    if condition == "stun":
        hero.paralyze(2)
    elif condition == "blind":
        hero.blind_for(2)
    elif condition == "thrall":
        hero.enthrall()
    else:
        hero.hurt(100, hero.center(), Vec2(0, 0), "test", "defeated")
    advance(hero, 1)
    assert not hero.combat.boulders and target.damage == 0
    assert hero.boulder_cooldown == 0


def test_rage_doubles_rig_weapon_and_hit_area_without_healing_and_refreshes():
    world, hero, _ = scene(650)
    original = hero.layout
    haft = hero.weapon.haft
    feet = hero.contact()
    hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
    assert hero.enraged and hero.hp == 59 and hero.size_multiplier == 2
    assert hero.contact() == feet and hero.planner is world.mighty_rage_planner
    for bone in original.skeleton.bones:
        assert hero.layout.skeleton.bone(bone.name).length == pytest.approx(bone.length * 2)
    assert hero.weapon.haft == pytest.approx(haft * 2)
    assert hero.hits(hero.transforms()[hero.layout.head].end)
    advance(hero, 9)
    hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
    advance(hero, 9)
    assert hero.enraged and hero.hp == 58
    advance(hero, 1.1)
    assert not hero.enraged and hero.size_multiplier == 1 and hero.hp == 58
    assert hero.layout.head_radius == original.head_radius and hero.contact() == feet


@pytest.mark.parametrize("distance,expected", [(30, 4), (150, 10), (330, 8)])
def test_rage_adds_two_damage_to_each_attack_type(distance, expected):
    _, hero, target = scene(distance)
    hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
    hero.attack()
    for _ in range(120):
        hero.update(DT)
        if target.damage:
            break
    assert target.damage == expected


def test_raging_mighty_swing_deals_fourteen():
    _, hero, target = scene()
    hero.melee_count = 2
    hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
    hero.attack()
    advance(hero, 0.6)
    assert target.damage == 14


def test_ignored_damage_does_not_refresh_rage_and_lethal_damage_does_not_grow():
    _, hero, _ = scene(650)
    hero.hurt(1, hero.center(), Vec2(0, 0), "dragon", "defeated")
    advance(hero, 0.1)
    left = hero.rage_left
    hero.hurt(1, hero.center(), Vec2(0, 0), "dragon", "defeated")
    assert hero.rage_left == left and hero.hp == 59
    _, other, _ = scene()
    other.hurt(100, other.center(), Vec2(0, 0), "test", "defeated")
    assert not other.enraged and other.size_multiplier == 1


def test_growth_during_leap_preserves_landing_and_attack():
    _, hero, target = scene(150)
    hero.attack()
    advance(hero, 0.4)
    position = hero.contact()
    hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
    assert hero.contact() == position and hero.leap is not None
    advance(hero, 0.5)
    assert hero.contact() == Vec2(230, 300) and target.damage == 10
    assert hero.planner.owns(hero.follower.current_anchor().surface)


def test_removed_landing_interrupts_leap_without_a_ghost_impact():
    world = SimWorld([Rect(180, 220, 160, 80)], 300, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_barbarian")
    target = world.add_goblin(Vec2(250, 220), "flag")
    hero.attack()
    assert hero.leap is not None
    advance(hero, 0.4)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert hero.leap is None and not hero.animated
    advance(hero, 1)
    assert not hero.combat.impacts and target.damage == 0
    world.goblins.clear()
    for _ in range(240):
        world.advance(DT)
    assert hero in world.stickmen and hero.animated and hero.hp == hero.max_hp


def test_render_all_attacks_and_rage_without_changing_simulation():
    for distance in (30, 150, 330):
        for rage in (False, True):
            _, hero, _ = scene(distance)
            if rage:
                hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
            hero.attack()
            for frame in range(90):
                hero.update(DT)
                if frame % 10:
                    continue
                image = QImage(700, 400, QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                before = (hero.contact(), hero.melee_count, hero.rage_left)
                draw_stickman(painter, hero)
                draw_mighty_effects(painter, [hero])
                painter.end()
                assert before == (hero.contact(), hero.melee_count, hero.rage_left)
                assert not image.isNull()
