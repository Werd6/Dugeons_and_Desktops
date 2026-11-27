"""Health escapes leave real decoys and preserve combat, terrain, and cleanup rules."""

import pytest
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.actors.hunting import Hunt
from dungeons_desktops.game.defenders.mimic.actor import Mode
from dungeons_desktops.game.heroes.the_slayer.assassinate import Phase
from dungeons_desktops.game.heroes.the_slayer.render import draw_slayer_effects
from dungeons_desktops.game.heroes.the_slayer.shadow import (
    CLONE_LIFETIME,
    ESCAPE_RECOVERY,
    ShadowClone,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.render.scene import draw_actors

DT = 1 / 60


def setup(boxes=()):
    world = SimWorld(list(boxes), 300, 1000)
    hero = world.add_stickman(Vec2(600, 300), "hero_rogue")
    return world, hero


def hit(hero, damage):
    return hero.hurt(damage, hero.center(), Vec2(0, 0), "goblin", "defeated")


def clones(world):
    return [actor for actor in world.stickmen if isinstance(actor, ShadowClone)]


def test_each_health_threshold_escapes_once_and_healing_does_not_restore_it():
    world, hero = setup()
    for index, hp in enumerate((45, 30, 15), 1):
        hero.reveal()
        hit(hero, hero.hp - hp - 1)
        assert len(clones(world)) == index - 1
        before, feet = hero.center(), hero.contact()
        assert not hit(hero, 1)
        clone = clones(world)[-1]
        assert hero.hp == hp and len(clones(world)) == index
        assert clone.center() == before and clone.contact() == feet
        assert hero.contact() == feet - Vec2(160, 0)
        assert hero.stealthed and not hero.prey and not hero.hits(hero.center())
        assert clone.prey and clone.hits(before) and clone.hp == 1
        assert clone not in world.heroes and hero in world.heroes
        # Subsequent damage is blocked until he next attacks/reveals.
        hit(hero, 1000)
        assert hero.hp == hp
    hero.heal(60)
    hero.reveal()
    hit(hero, 46)
    assert hero.hp == 14 and len(clones(world)) == 3
    assert not hero.stealthed


def test_heavy_hit_uses_crossed_thresholds_together_but_lethal_hit_still_kills():
    world, hero = setup()
    hit(hero, 48)
    assert hero.hp == 12 and len(clones(world)) == 1 and hero.stealthed
    hero.heal(60)
    hero.reveal()
    hit(hero, 48)
    assert len(clones(world)) == 1 and not hero.stealthed
    other = world.add_stickman(Vec2(800, 300), "hero_rogue")
    assert hit(other, 60)
    assert not other.animated and len(clones(world)) == 1


def test_blocked_damage_does_not_use_a_threshold_or_create_a_clone():
    world, hero = setup()
    hero._grace["goblin"] = 1
    hit(hero, 15)
    assert hero.hp == 60 and not clones(world)
    hero._grace.clear()
    hit(hero, 15)
    assert hero.hp == 45 and len(clones(world)) == 1


def test_defenders_retarget_to_clone_and_first_hit_dissolves_it_without_a_corpse():
    world, hero = setup()
    hunt = Hunt(retarget_every=60)
    assert hunt.update(DT, Vec2(620, 300), world.stickmen) is hero
    hit(hero, 15)
    clone = clones(world)[0]
    assert hunt.update(DT, Vec2(620, 300), world.stickmen) is clone
    assert world.locate_prey(clone) == clone.center()
    assert world.prey_at(clone.center()) is clone
    assert world._spear_hits(clone.center()) is clone
    before_gore = len(world.gore.drops)
    assert hit(clone, 1)
    assert clone.hp == 0 and clone.gone and not clone.prey
    assert world.locate_prey(clone) is None and world.prey_at(clone.center()) is None
    assert hunt.update(DT, Vec2(620, 300), world.stickmen) is None
    assert not hit(clone, 1) and len(world.gore.drops) == before_gore
    assert world.kills == 0 and not world.kill_marks
    world.add_lich(Vec2(800, 300))
    assert world.raise_skeleton(clone) is None
    world._despawn()
    assert clone not in world.stickmen and hero in world.heroes


def test_surviving_clone_expires_after_four_seconds_even_if_owner_dies():
    world, hero = setup()
    hit(hero, 15)
    clone = clones(world)[0]
    hero.reveal()
    hit(hero, 100)
    clone.paralyze(10)
    for _ in range(round(CLONE_LIFETIME / DT) - 1):
        world.advance(DT)
    assert clone in world.stickmen and clone.prey
    world.advance(DT)
    assert clone.gone and clone not in world.stickmen


@pytest.mark.parametrize("phase", [Phase.THROW, Phase.FLIGHT, Phase.EMBEDDED])
def test_escape_cancels_assassinate_and_preserves_stealth_before_attacking_again(phase):
    world, hero = setup()
    world.add_minotaur(Vec2(700, 300))
    hero.attack()
    for _ in range(180):
        if hero.assassinate.phase is phase:
            break
        hero.update(DT)
    assert hero.assassinate.phase is phase
    hit(hero, 15)
    assert not hero.assassinate.active and not hero.weapon.busy
    assert hero.assassinate.cooldown > 0
    # Even a ready ability cannot undo the escape on its first frame.
    hero.assassinate.cooldown = 0
    for _ in range(round(ESCAPE_RECOVERY / DT) - 1):
        hero.attack()
        hero.update(DT)
        assert hero.stealthed and not hero.weapon.busy
    for _ in range(3):
        hero.update(DT)
    assert hero.assassinate.phase is Phase.THROW and not hero.stealthed


@pytest.mark.parametrize("facing", [-1, 1])
def test_blink_goes_backward_in_both_directions(facing):
    world, hero = setup()
    hero.follower.facing = facing
    hero.locomotion.teleport(hero.follower.command())
    before = hero.contact()
    hit(hero, 15)
    assert hero.contact() == before - Vec2(160 * facing, 0)
    assert hero.facing == facing


@pytest.mark.parametrize("boxes,x", [([], 20), ([Rect(420, 200, 100, 100)], 600)])
def test_blink_chooses_valid_clear_terrain_at_edges_and_windows(boxes, x):
    world, _ = setup(boxes)
    hero = world.add_stickman(Vec2(x, 300), "hero_rogue")
    hit(hero, 15)
    anchor = hero.follower.current_anchor()
    assert hero.planner.owns(anchor.surface) and anchor.surface.walkable
    assert anchor.surface.contains(hero.contact())
    assert 0 <= hero.contact().x < x
    assert not any(box.contains(hero.center()) for box in boxes)


def test_airborne_clone_keeps_exact_departure_pose_while_hero_blinks_to_ground():
    world, hero = setup()
    hero.fall_in(Vec2(600, 100))
    before, feet = hero.center(), hero.contact()
    hit(hero, 15)
    clone = clones(world)[0]
    assert clone.center() == before and clone.contact() == feet
    clone.update(1)
    assert clone.center() == before
    assert hero.contact() == Vec2(440, 300) and hero.stealthed


def test_shadow_does_not_attack_or_inherit_hero_abilities():
    world, hero = setup()
    hit(hero, 15)
    clone = clones(world)[0]
    enemy = world.add_goblin(Vec2(610, 300), "flag")
    hp, origin = enemy.hp, clone.center()
    for _ in range(60):
        clone.attack()
        clone.update(DT)
    assert enemy.hp == hp and clone.center() == origin and clone.prey
    assert not hasattr(clone, "assassinate") and not hasattr(clone, "escape_thresholds")


def test_escape_clears_engulf_state_without_defender_ooze():
    world = SimWorld([], 400, 800)
    hero = world.add_stickman(Vec2(500, 300), "hero_rogue")
    hero.engulfed_by = object()

    hero._shadow_escape()
    assert hero.engulfed_by is None



def test_mimic_can_attack_the_decoy_but_it_cannot_throw_a_rogue_dagger():
    world, hero = setup()
    hit(hero, 15)
    clone = clones(world)[0]
    mimic = world.add_mimic(Vec2(620, 300))
    mimic._mark(clone)
    assert mimic._arrived(clone)
    mimic._lure(DT)
    assert mimic.mode is Mode.OPEN and mimic.victim is clone
    assert mimic.spotter is None and mimic.knife is None


def test_shadow_render_is_translucent_and_safe_before_and_after_expiry():
    world, hero = setup()
    hit(hero, 15)
    clone = clones(world)[0]
    image = QImage(1000, 320, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    draw_actors(painter, (), world.stickmen)
    draw_slayer_effects(painter, world.stickmen)
    assert painter.opacity() == 1
    painter.end()
    assert 0 < clone.visibility < 1 and clone.prey
    assert any(image.pixelColor(x, y).alpha() > 0 for x in range(580, 620) for y in range(260, 305))
    clone.update(CLONE_LIFETIME)
    painter = QPainter(image)
    draw_actors(painter, (), [clone])
    draw_slayer_effects(painter, [clone])
    painter.end()
