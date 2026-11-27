"""Timed transformations preserve the hero, combat allegiance and terrain behavior."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.defenders.dragon.actor import BODY_LENGTH, DragonMode
from dungeons_desktops.game.heroes.natures_wrath.bear import BEAR_SECONDS, CHARGE_SPEED, WALK_SPEED
from dungeons_desktops.game.heroes.natures_wrath.dragon import MAGMA_SIZE, DragonPhase
from dungeons_desktops.game.heroes.natures_wrath.spells import Ability
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def scene(ability=Ability.MAGMA_DRAGON, boxes=(), point=None):
    world = SimWorld(list(boxes), 400, 1200, ceiling=0)
    hero = world.add_stickman(point or Vec2(200, 400), "hero_druid")
    hero.queue_index = hero.rotation.index(ability)
    return world, hero


def advance(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def start(hero, ability):
    if ability is Ability.MAGMA_DRAGON:
        hero._start_dragon()
    else:
        hero._start_bear()


def test_dragon_strafes_immediately_and_obeys_exact_6_10_6_phases():
    world, hero = scene()
    target = world.add_minotaur(Vec2(400, 400))
    hero._start_dragon()
    dragon = hero.dragon
    assert dragon.mode is DragonMode.FLY
    assert dragon.shoulder.distance_to(dragon.hip) == pytest.approx(BODY_LENGTH * MAGMA_SIZE)
    advance(hero, 1)
    assert dragon.flames and hero.center().x != 200
    advance(hero, 5)
    assert dragon.elapsed == pytest.approx(6)
    assert dragon.form_phase is DragonPhase.NORMAL and dragon.mode is DragonMode.LAND
    advance(hero, 9.9)
    assert dragon.mode in (DragonMode.WALK, DragonMode.SWIPE)
    advance(hero, 0.1)
    assert dragon.form_phase is DragonPhase.LAST_STRAFE and dragon.mode is DragonMode.FLY
    advance(hero, 5.9)
    assert hero.dragon is dragon and hero.current_ability is Ability.MAGMA_DRAGON
    position = hero.contact()
    advance(hero, 0.1)
    assert hero.dragon is None and hero.current_ability is Ability.FIREBALL
    assert hero.contact().distance_to(position) < 25
    assert hero.locomotion.mode is PoseMode.AIR
    assert target.damage > 0
    assert not world.dragons


@pytest.mark.parametrize("ability", [Ability.MAGMA_DRAGON, Ability.BEAR])
def test_form_release_uses_rotation_and_preserves_health_and_rosters(ability):
    world, hero = scene(ability)
    world.add_goblin(Vec2(350, 400), "flag")
    hero.damage = 17
    advance(hero, 0.5)
    form = hero.form
    assert form is not None and hero.casting is None
    assert hero.hp == 43 and hero.max_hp == 60
    assert hero in world.heroes and hero in world.stickmen and hero.prey
    assert form not in world.monsters() and hero not in world.monsters()
    assert hero.hits(form.head) and hero.hits(form.body)
    assert not hero.hits(form.body + Vec2(0, -150))
    assert not hero.limbs_draggable
    hero._end_form()
    assert hero.hp == 43 and hero.form is None
    assert hero.current_ability is (
        Ability.FIREBALL if ability is Ability.MAGMA_DRAGON else Ability.CHAIN_LIGHTNING
    )


@pytest.mark.parametrize("ability", [Ability.MAGMA_DRAGON, Ability.BEAR])
def test_forms_hurt_defenders_without_friendly_fire(ability):
    world, hero = scene(ability)
    target = world.add_minotaur(Vec2(430, 400))
    ally = world.add_stickman(Vec2(350, 400), "druid")
    start(hero, ability)
    advance(hero, 5)
    assert target.damage > 0
    assert hero.damage == ally.damage == 0


@pytest.mark.parametrize("ability", [Ability.MAGMA_DRAGON, Ability.BEAR])
def test_stun_pauses_form_motion_but_not_expiry_and_death_reverts_in_place(ability):
    _, hero = scene(ability)
    start(hero, ability)
    hero.paralyze(1)
    before = hero.contact()
    advance(hero, 0.5)
    assert hero.contact() == before and hero.form.elapsed == pytest.approx(0.5)
    assert hero.stun == pytest.approx(0.5)
    hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    assert hero.form is None and not hero.animated and not hero.prey
    assert hero.center().distance_to(before) < 60
    advance(hero, 1)
    assert hero.form is None


def test_bear_lasts_30_seconds_then_rotation_continues_to_lightning():
    _, hero = scene(Ability.BEAR)
    hero._start_bear()
    advance(hero, BEAR_SECONDS - DT)
    assert hero.bear is not None and hero.current_ability is Ability.BEAR
    advance(hero, DT)
    assert hero.form is None and hero.current_ability is Ability.CHAIN_LIGHTNING
    assert hero.cast_wait > 0 and hero.locomotion.mode is PoseMode.WALK


def test_bear_wanders_and_switches_to_a_faster_charging_gait():
    world, hero = scene(Ability.BEAR)
    hero._start_bear()
    bear = hero.bear
    bear.wander_x = 600
    advance(hero, 0.7)
    assert not bear.charging and 20 < abs(bear.velocity.x) <= WALK_SPEED
    target = world.add_minotaur(Vec2(600, 400))
    advance(hero, 0.6)
    assert bear.charging and bear.charge > 0.9
    assert WALK_SPEED * 3 < abs(bear.velocity.x) <= CHARGE_SPEED
    assert any(leg.foot.y < bear.feet.y - 2 for leg in bear.legs)
    advance(hero, 3)
    assert target.damage > 0


@pytest.mark.parametrize("facing", [-1, 1])
def test_taller_bear_can_reach_small_enemies_with_its_front_paws(facing):
    world, hero = scene(Ability.BEAR, point=Vec2(500, 400))
    target = world.add_goblin(Vec2(500 + facing * 240, 400), "flag")
    hero._start_bear()
    for _ in range(60 * 5):
        world.advance(DT)
    assert target.damage > 0


def test_bear_wont_climb_to_an_enemy_on_another_surface():
    world, hero = scene(Ability.BEAR, [Rect(500, 180, 250, 100)])
    target = world.add_goblin(Vec2(600, 180), "flag")
    hero._start_bear()
    advance(hero, 10)
    assert hero.bear.support.walkable and hero.contact().y == 400
    assert not hero.bear.charging and target.damage == 0
    assert hero.locomotion.mode is PoseMode.WALK


def test_bear_stops_at_window_edges_and_falls_when_window_is_removed():
    world, hero = scene(Ability.BEAR, [Rect(100, 200, 300, 100)], Vec2(200, 200))
    hero._start_bear()
    bear = hero.bear
    bear.wander_x = 1000
    advance(hero, 5)
    assert 145 <= bear.feet.x <= 355 and bear.feet.y == 200
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(130, 180, 300, 100)])
    assert bear.feet.y == 180 and bear.support.walkable
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert bear.flying
    advance(hero, 1)
    assert bear.feet.y == 400 and not bear.flying
    assert hero.form is bear


def test_bear_cast_in_air_falls_instead_of_climbing_or_hovering():
    _, hero = scene(Ability.BEAR)
    hero.fall_in(Vec2(200, 100))
    hero._start_bear()
    assert hero.bear.flying
    advance(hero, 1.2)
    assert hero.contact().y == 400 and not hero.bear.flying


@pytest.mark.parametrize("ability", [Ability.MAGMA_DRAGON, Ability.BEAR])
def test_forms_render_deterministically_with_their_signature_colors(ability):
    world, hero = scene(ability)
    start(hero, ability)
    rng = world.random.getstate()

    def render():
        image = QImage(800, 500, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(3, 3)
        painter.translate(-100, -250)
        draw_stickman(painter, hero)
        painter.end()
        return image

    image = render()
    assert image == render() and rng == world.random.getstate()
    colors = [image.pixelColor(x, y) for x in range(80, 600) for y in range(100, 450)]
    if ability is Ability.BEAR:
        assert any(c.red() > 180 and c.green() < 90 and c.blue() < 100 for c in colors)
    else:
        assert any(c.red() > 220 and 80 < c.green() < 230 and c.blue() < 100 for c in colors)
