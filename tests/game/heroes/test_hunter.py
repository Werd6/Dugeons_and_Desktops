"""The ranger hero's loadout, navigation, rifle attack, and spawn entrypoints."""

import pytest
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.heroes.the_hunter import TheHunter
from dungeons_desktops.game.heroes.the_hunter.combat import Gun
from dungeons_desktops.game.heroes.the_hunter.weapon import SniperRifle
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind, TerrainChange
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.equipment import Bow
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def advance(actor, seconds):
    for _ in range(round(seconds / DT)):
        actor.update(DT)


def scene(facing=1):
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(500, 300), "hero_ranger")
    hero.follower.facing = facing
    hero.locomotion.teleport(hero.follower.command())
    return world, hero


def test_hunter_keeps_ranger_proportions_and_speed_with_named_hero_health():
    world, hero = scene()
    ranger = world.add_stickman(Vec2(600, 300), "ranger")
    assert isinstance(hero, TheHunter) and isinstance(hero.weapon, SniperRifle)
    assert not isinstance(hero.weapon, Bow)
    assert hero in world.heroes and hero in world.stickmen
    assert "hero_ranger" in HEROES and "hero_ranger" not in CLASSES
    assert hero.display_name == "The Outlaw" and hero.hp == hero.max_hp == 60
    assert hero.layout.skeleton.bones == ranger.layout.skeleton.bones
    assert hero.layout.head_radius == ranger.layout.head_radius
    assert hero.calling.speed == ranger.calling.speed
    assert hero.calling.reach == ranger.calling.reach
    hero.set_goal(Vec2(800, 300))
    ranger.set_goal(Vec2(900, 300))
    advance(hero, 0.5)
    advance(ranger, 0.5)
    assert hero.contact().x - 500 == pytest.approx(ranger.contact().x - 600)


@pytest.mark.parametrize("facing", [-1, 1])
def test_scoped_rifle_tracks_both_hands_during_carry_and_shot(facing):
    _, hero = scene(facing)
    for shooting in (False, True):
        if shooting:
            hero.weapon.start_action(Gun.SNIPER)
        for _ in range(70):
            hero.update(DT)
            transforms = hero.transforms()
            grip = transforms[hero.weapon.hand_chain.bones[-1]].end
            other = transforms[hero.weapon.support_chain.bones[-1]].end
            muzzle, _ = hero.weapon.muzzle(transforms, hero.facing)
            direction = (muzzle - grip).normalized()
            assert other.distance_to(grip + direction * hero.weapon.support) < 0.8
            assert (muzzle.x - grip.x) * facing > 0
            assert any(s.kind == "scope_glass" for s in hero.weapon_strokes())
            assert all(s.kind != "string" for s in hero.weapon_strokes())


@pytest.mark.parametrize("facing", [-1, 1])
def test_sniper_hits_once_at_range_without_arrows_or_friendly_fire(facing):
    world, hero = scene(facing)
    enemy = world.add_goblin(Vec2(500 + facing * 240, 300), "flag")
    ally = world.add_stickman(Vec2(500 + facing * 100, 300), "fighter")
    hero.attack()
    advance(hero, 0.4)
    assert enemy.damage == 0
    advance(hero, 0.1)
    assert enemy.damage == 10 and ally.damage == 0 and hero.shot is not None
    advance(hero, 0.6)
    assert enemy.damage == 10 and hero.shot is None and not world.spells.arrows


@pytest.mark.parametrize("interruption", ["death", "stun", "removed_target"])
def test_interrupted_rifle_does_not_leave_a_delayed_hit(interruption):
    world, hero = scene()
    enemy = world.add_goblin(Vec2(740, 300), "flag")
    hero.attack()
    advance(hero, 0.2)
    if interruption == "death":
        hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "test", "defeated")
    elif interruption == "stun":
        hero.paralyze(2)
    else:
        world.goblins.remove(enemy)
    advance(hero, 1.1)
    assert enemy.damage == 0


def test_rifle_can_aim_up_at_a_flying_enemy_and_credit_a_kill():
    world, hero = scene()
    enemy = world.add_dragon(Vec2(680, 200), facing=-1)
    enemy.damage = enemy.max_hp - 1
    assert hero._engage()
    advance(hero, 0.5)
    assert enemy.hp == 0 and world.monster_kills == 1
    assert enemy in world.fallen and hero.shot[1].y < hero.shot[0].y


def test_thrall_uses_pistols_against_adventurers_with_fractional_damage():
    world, hero = scene()
    ally = world.add_stickman(Vec2(700, 300), "fighter")
    hero.enthrall()
    hero.cooldown = 0
    advance(hero, 0.4)
    assert ally.damage == 1
    assert hero.weapon.gun is Gun.PISTOLS
    assert hero.sniper_cooldown == hero.shotgun_cooldown == 0


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_and_cleanup(edge):
    world = DesktopSession(
        Rect(0, 0, 700, 500), Rect(0, 0, 700, 450), FakeWindowSource(),
        max_stickmen=0, defenders=(), seed=3,
    )
    hero = world.spawn_at_edge(edge, variant="hero_ranger")
    assert isinstance(hero, TheHunter) and hero.wander
    assert world.hero_health_bars == [("The Outlaw", 1)]
    hero.hurt(15, hero.center(), Vec2(0, 0), "test", "defeated")
    assert world.hero_health_bars == [("The Outlaw", 0.75)]
    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "test", "defeated")
    for _ in range(240):
        world.advance(DT)
    assert hero not in world.heroes and hero not in world.stickmen


def test_climbs_rides_windows_and_recovers_when_the_window_disappears():
    world = SimWorld([Rect(180, 100, 200, 200)], 300, 600, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_ranger")
    hero.set_goal(Vec2(250, 100))
    modes = set()
    for _ in range(60 * 22):
        hero.update(DT)
        modes.add(hero.locomotion.mode)
    assert PoseMode.CLIMB in modes and hero.contact().distance_to(Vec2(250, 100)) < 1
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(210, 80, 200, 200)])
    assert hero.contact().distance_to(Vec2(280, 80)) < 1
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    advance(hero, 4)
    assert hero.animated and hero.hp == hero.max_hp
    assert hero.planner.owns(hero.follower.current_anchor().surface)


def test_preview_selects_hunter_and_preserves_his_class():
    preview = RigPreviewController(700, 400)
    preview.spawn_hunter()
    hero = preview.selected
    assert isinstance(hero, TheHunter) and hero in preview.heroes
    preview.set_variant("ranger")
    assert hero.variant == "hero_ranger" and isinstance(hero.weapon, SniperRifle)


@pytest.mark.parametrize("kind", [SurfaceKind.FLOOR, SurfaceKind.LEFT, SurfaceKind.CEILING])
def test_equipment_renders_on_floor_wall_and_ceiling_without_changing_state(kind):
    world = SimWorld([], 500, 800, ceiling=0)
    surface = next(s for s in world.planner.surfaces if s.kind is kind)
    anchor = Anchor(surface, surface.point_at((surface.low + surface.high) / 2))
    hero = world._add_stickman(anchor, "hero_ranger", False)
    advance(hero, 0.2)
    image = QImage(800, 550, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    before = (hero.contact(), hero.hp, hero.weapon.time)
    draw_stickman(painter, hero)
    painter.end()
    assert before == (hero.contact(), hero.hp, hero.weapon.time)
    assert not image.isNull()
