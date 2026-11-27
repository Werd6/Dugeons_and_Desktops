"""Independent spell clocks, bounded copies, safe doors, and five separate impacts."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.effects.chromatic import RayEffect
from dungeons_desktops.game.heroes.the_inquisitive.actor import Simulacrum
from dungeons_desktops.game.heroes.the_inquisitive.spell_render import draw_iggy_spells
from dungeons_desktops.game.heroes.the_inquisitive.spells import (
    CAST_RELEASE,
    COOLDOWNS,
    MISSILE_INTERVAL,
    Ability,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.render.scene import draw_actors

DT = 1 / 60


def advance(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def scene(ability, *, far=False, boxes=()):
    world = SimWorld(boxes, 400, 1200, ceiling=0)
    hero = world.add_stickman(Vec2(100, 400), "hero_wizard")
    target = world.add_minotaur(Vec2(800 if far else 350, 400))
    hero.cooldowns = {key: 0 if key is ability else 999 for key in Ability}
    return world, hero, target


def test_five_missiles_launch_sequentially_take_different_paths_and_hit_once_each():
    world, hero, target = scene(Ability.MAGIC_MISSILE)
    assert hero.cast_spell(Ability.MAGIC_MISSILE)
    missiles, launched = [], []
    for frame in range(180):
        hero.update(DT)
        for missile in hero.spells.missiles:
            if not any(missile is previous for previous in missiles):
                missiles.append(missile)
                launched.append((frame + 1) * DT)
    assert len(missiles) == 5
    assert launched[0] == pytest.approx(CAST_RELEASE, abs=DT)
    for before, after in zip(launched, launched[1:], strict=False):
        assert after - before == pytest.approx(MISSILE_INTERVAL, abs=DT)
    assert len({missile.point(0.4) for missile in missiles}) == 5
    assert all(missile.point(0) == missile.origin for missile in missiles)
    assert all(missile.point(1).distance_to(missile.target) < 1e-6 for missile in missiles)
    assert all(
        missile.point(i / 30).y < world.floor_y
        for missile in missiles for i in range(1, 30)
    )
    assert target.damage == 5 and not world.spells.missiles
    assert not hero.spells.missiles


def test_ready_ray_can_cast_while_missile_has_its_own_cooldown():
    _, hero, target = scene(Ability.MAGIC_MISSILE)
    assert hero.cast_spell(Ability.MAGIC_MISSILE)
    advance(hero, 1.5)
    remaining = hero.cooldowns[Ability.MAGIC_MISSILE]
    assert remaining > 2
    hero.cooldowns[Ability.CHROMATIC_RAY] = 0
    assert hero.cast_spell(Ability.CHROMATIC_RAY)
    advance(hero, 0.4)
    assert hero.cooldowns[Ability.MAGIC_MISSILE] == pytest.approx(remaining - 0.4)
    assert hero.cooldowns[Ability.CHROMATIC_RAY] > 5
    assert hero.spells.rays and hero.casting is Ability.CHROMATIC_RAY
    hero.spells.rays[-1].effect = RayEffect.ACID
    advance(hero, 1.7)
    assert target.damage == 9  # Five missiles plus one swept ray hit.


def test_autonomous_spell_choice_is_not_a_fixed_rotation():
    choices = set()
    for seed in range(8):
        world = SimWorld([], 400, 1200, seed=seed)
        hero = world.add_stickman(Vec2(100, 400), "hero_wizard")
        hero.cooldowns[Ability.SIMULACRUM] = 10
        world.add_minotaur(Vec2(350, 400))
        hero.update(DT)
        choices.add(hero.casting)
    assert choices == {Ability.CHROMATIC_RAY, Ability.MAGIC_MISSILE}


def test_simulacra_have_three_hp_four_live_slots_and_cannot_duplicate():
    world = SimWorld([], 400, 1200)
    hero = world.add_stickman(Vec2(300, 400), "hero_wizard")
    summoned = []
    elapsed = 0
    for count in range(4):
        for _ in range(650):
            hero.update(DT)
            elapsed += DT
            if len(hero.copies) == count + 1:
                summoned.append(elapsed)
                break
        assert len(hero.copies) == count + 1
        assert hero.cooldowns[Ability.SIMULACRUM] == pytest.approx(10)
        assert not hero.cast_spell(Ability.SIMULACRUM)
    assert all(10 <= b - a < 10.4 for a, b in zip(summoned, summoned[1:], strict=False))
    advance(hero, 11)
    assert not hero.cast_spell(Ability.SIMULACRUM)
    for copy in hero.copies:
        assert isinstance(copy, Simulacrum) and copy.hp == 3
        assert copy in world.stickmen and copy not in world.heroes and copy.prey
        assert Ability.SIMULACRUM not in copy.cooldowns
        assert not copy.cast_spell(Ability.SIMULACRUM)
        assert copy.cooldowns is not hero.cooldowns
    victim = hero.copies[0]
    victim.knock_down(victim.center(), 0, 2, 1)
    assert not victim.animated and len(hero.copies) == 4
    assert not hero.cast_spell(Ability.SIMULACRUM)
    victim.get_up()
    victim.hurt(3, victim.center(), Vec2(0, 0), "test", "defeated")
    assert len(hero.copies) == 3
    assert hero.cast_spell(Ability.SIMULACRUM)
    advance(hero, 0.4)
    assert len(hero.copies) == 4 and victim not in hero.copies


@pytest.mark.parametrize("distance", [None, 750, 250])
def test_simulacrum_has_priority_without_needing_an_enemy_in_range(distance):
    world = SimWorld([], 400, 1200)
    hero = world.add_stickman(Vec2(100, 400), "hero_wizard")
    if distance is not None:
        world.add_minotaur(Vec2(100 + distance, 400))
    hero.cooldowns = dict.fromkeys(Ability, 0)
    hero.update(DT)
    assert hero.casting is Ability.SIMULACRUM
    advance(hero, 0.4)
    assert len(hero.copies) == 1 and hero.cooldowns[Ability.SIMULACRUM] > 9


@pytest.mark.parametrize("ability", [
    Ability.CHROMATIC_RAY, Ability.MAGIC_MISSILE, Ability.DIMENSION_DOOR,
])
def test_copy_can_cast_other_spells(ability):
    world, hero, target = scene(Ability.SIMULACRUM, far=ability is Ability.DIMENSION_DOOR)
    copy = hero._summon()
    copy.wander = False
    copy.recovery = 0
    copy.cooldowns = {key: 0 if key is ability else 999 for key in copy.cooldowns}
    assert copy.cast_spell(ability)
    advance(copy, 3)
    if ability is Ability.DIMENSION_DOOR:
        assert copy.contact().distance_to(hero.contact()) > 60
    else:
        assert target.damage == (4 if ability is Ability.CHROMATIC_RAY else 5)
    assert not hero.spells.rays and not hero.spells.missiles
    assert len(world.heroes) == 1


@pytest.mark.parametrize("interrupt", ["stun", "death", "blind", "thrall"])
def test_interrupted_windup_cannot_release_or_spend_cooldown(interrupt):
    _, hero, target = scene(Ability.MAGIC_MISSILE)
    assert hero.cast_spell(Ability.MAGIC_MISSILE)
    advance(hero, 0.1)
    if interrupt == "stun":
        hero.paralyze(2)
    elif interrupt == "death":
        hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    elif interrupt == "blind":
        hero.blind = 2
    else:
        hero.enthrall()
    advance(hero, 1)
    assert not hero.spells.missiles and target.damage == 0
    assert hero.cooldowns[Ability.MAGIC_MISSILE] == 0


def test_released_missiles_finish_but_death_cancels_rest_of_volley():
    _, hero, target = scene(Ability.MAGIC_MISSILE)
    assert hero.cast_spell(Ability.MAGIC_MISSILE)
    advance(hero, 0.6)
    assert hero.missiles_fired == 2
    hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    advance(hero, 1.6)
    assert target.damage == 2 and hero.cooldowns[Ability.MAGIC_MISSILE] > 0


def test_dimension_door_fades_phases_teleports_cat_and_uses_lich_cooldown():
    _, hero, target = scene(Ability.DIMENSION_DOOR, far=True)
    start = hero.contact()
    assert hero.cast_spell(Ability.DIMENSION_DOOR)
    assert hero.cooldowns[Ability.DIMENSION_DOOR] == COOLDOWNS[Ability.DIMENSION_DOOR] == 20
    advance(hero, 0.7)
    assert hero.contact() == start and hero.phased and not hero.prey
    hp = hero.hp
    hero.hurt(10, hero.center(), Vec2(0, 0), "test", "defeated")
    assert hero.hp == hp and not hero.hits(hero.center())
    advance(hero, 0.15)
    assert hero.contact().distance_to(start) > 60
    assert hero.cat.feet.distance_to(hero.contact()) < 20
    advance(hero, 0.6)
    assert hero.door is None and hero.visibility == 1 and hero.prey
    assert 160 < hero.center().distance_to(target.center()) < 280


@pytest.mark.parametrize("remove", [False, True])
def test_window_changes_during_door_keep_a_valid_exit(remove):
    world, hero, _ = scene(
        Ability.DIMENSION_DOOR, far=True, boxes=[Rect(500, 200, 500, 200)]
    )
    world.minotaurs.clear()
    world.add_minotaur(Vec2(800, 200))
    assert hero.cast_spell(Ability.DIMENSION_DOOR)
    assert hero.door.surface.box == 0
    destination = hero.door.target
    advance(hero, 0.4)
    change = TerrainChange(remap={0: None}) if remove else TerrainChange(moves={0: Vec2(20, -30)})
    world.apply_terrain(change, [] if remove else [Rect(520, 170, 500, 200)])
    if not remove:
        assert hero.door.target == destination + Vec2(20, -30)
    advance(hero, 1)
    assert hero.animated and hero.planner.owns(hero.follower.current_anchor().surface)
    assert not any(box.contains(hero.center()) for box in world.boxes)


def test_no_dimension_door_when_already_at_casting_range():
    _, hero, _ = scene(Ability.DIMENSION_DOOR)
    assert not hero.cast_spell(Ability.DIMENSION_DOOR)
    assert hero.cooldowns[Ability.DIMENSION_DOOR] == 0


def test_chromatic_ray_colors_vary_and_rendering_does_not_advance_spells():
    world, hero, target = scene(Ability.CHROMATIC_RAY)
    colors = set()
    for _ in range(10):
        target.damage = 0
        hero.spells.ray(hero.wand_tip(), target)
        colors.add(hero.spells.rays[-1].color)
    assert len(colors) >= 3
    hero.spells.advance_ray(0.8)
    hero.spells.resolve_ray(hero.wand_tip())
    hero.spells.missile(hero.wand_tip(), target, target.center())
    hero.spells.update(0.1)
    copy = hero._summon()
    copy.wander = False

    def render():
        image = QImage(1000, 450, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(2, 2)
        painter.translate(0, -200)
        draw_actors(painter, (), world.stickmen)
        draw_iggy_spells(painter, world.stickmen)
        painter.end()
        return image

    rng = world.random.getstate()
    age = hero.spells.missiles[0].age
    first = render()
    assert first == render() and first.pixelColor(200, 390).alpha() > 0
    middle = hero.spells.rays[-1].start.lerp(hero.spells.rays[-1].end, 0.5)
    assert first.pixelColor(round(middle.x * 2), round((middle.y - 200) * 2)).alpha() > 180
    assert world.random.getstate() == rng and hero.spells.missiles[0].age == age
