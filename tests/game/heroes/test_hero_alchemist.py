"""Hero Alchemist model, equipment, sticky vials, and spawn wiring."""

import pytest
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.actors.hunting import Hunt
from dungeons_desktops.game.adventurers.alchemy import CLING_DURATION
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.heroes.hero_alchemist import HeroAlchemist
from dungeons_desktops.game.heroes.hero_alchemist.beast import (
    BEAST_SCALE,
    CLAW_DAMAGE,
    MUTAGEN_COOLDOWN,
    MUTAGEN_SECONDS,
    TRANSFORM_IN,
)
from dungeons_desktops.game.heroes.hero_alchemist.poison import (
    POISON_COOLDOWN,
    POISON_DAMAGE,
    POISON_DURATION,
    VENT_RELEASE,
)
from dungeons_desktops.game.heroes.hero_alchemist.servant import (
    CAST_RELEASE,
    MOVE_SPEED,
    OOZE_LIFETIME,
    TENDRIL_DAMAGE,
    TOSS_TIME,
    AlchemicalOoze,
)
from dungeons_desktops.game.heroes.hero_alchemist.weapon import GreenVials
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.preview.controller import RigPreviewController

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def test_hero_uses_base_alchemist_proportions_movement_and_green_vials():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_alchemist")
    ordinary = world.add_stickman(Vec2(500, 300), "alchemist")
    assert isinstance(hero, HeroAlchemist)
    assert isinstance(hero.weapon, GreenVials)
    assert hero.display_name == "The Biologist" and hero.hp == hero.max_hp == 60
    assert "hero_alchemist" in HEROES and "hero_alchemist" not in CLASSES
    assert hero.layout.skeleton.bones == ordinary.layout.skeleton.bones
    assert hero.calling.speed == ordinary.calling.speed
    assert hero.calling.reach == ordinary.calling.reach
    assert hero.calling.cooldown == ordinary.calling.cooldown
    assert sum(stroke.kind == "hero_vial" for stroke in hero.weapon_strokes()) == 3


def test_green_vials_use_the_base_alchemists_throw():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    hero.ooze_cooldown = 999
    target = world.add_goblin(Vec2(350, 300), "flag")
    target.update = lambda dt: None
    hero.attack()
    advance(world, 0.45)
    assert world.vials.flying
    assert world.vials.flying[0].owner is hero
    assert sum(stroke.kind == "hero_vial" for stroke in hero.weapon_strokes()) == 2


def test_green_vial_sticks_to_its_target_and_deals_damage_over_time():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    hero.ooze_cooldown = 999
    target = world.add_goblin(Vec2(350, 300), "flag")
    target.update = lambda dt: None
    hero.attack()
    for _ in range(round(3 / DT)):
        world.advance(DT)
        if world.vials.clinging:
            break

    assert len(world.vials.clinging) == 1
    ooze = world.vials.clinging[0]
    assert ooze.target is target and ooze.owner is hero
    assert not world.vials.explosions

    hero.update = lambda dt: None
    advance(world, 1.05)
    assert target.damage == 1
    advance(world, CLING_DURATION - 1.0)
    assert not world.vials.clinging


def test_repeated_oozes_spread_across_different_target_points():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    target = world.add_goblin(Vec2(350, 300), "flag")
    anchor = target.center()
    impact = anchor + Vec2(-2, 1)
    for _ in range(3):
        world.vials.cling(target, impact, anchor, hero)

    offsets = [ooze.offset for ooze in world.vials.clinging]
    assert len(set(offsets)) == 3
    assert all(
        first.distance_to(second) >= 14
        for index, first in enumerate(offsets)
        for second in offsets[index + 1 :]
    )


def test_beastform_mutagen_grows_then_claws_nearby_targets():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    target = world.add_goblin(Vec2(255, 300), "flag")
    target.update = lambda dt: None
    hero.ooze_cooldown = 999
    hero.poison_cooldown = 999

    world.advance(DT)
    assert hero.beast is not None and hero.beast.transforming
    start_scale = hero.beast.visual_scale
    advance(world, TRANSFORM_IN)
    assert hero.beast is not None
    assert hero.beast.visual_scale == pytest.approx(BEAST_SCALE)
    assert hero.beast.visual_scale > start_scale

    for _ in range(round(2 / DT)):
        world.advance(DT)
        if target.damage:
            break
    assert target.damage == CLAW_DAMAGE
    assert not world.vials.flying and not world.vials.explosions


def test_poison_vent_damages_every_enemy_inside_the_lingering_cloud_each_second():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    hero.mutagen_cooldown = 999
    hero.ooze_cooldown = 999
    hero.cooldown = 999
    near = world.add_goblin(Vec2(245, 300), "flag")
    second = world.add_goblin(Vec2(270, 300), "flag")
    far = world.add_goblin(Vec2(350, 300), "flag")
    for target in (near, second, far):
        target.update = lambda dt: None

    world.advance(DT)
    assert hero.vent_time is not None
    assert hero.poison_cooldown == pytest.approx(POISON_COOLDOWN)
    advance(world, VENT_RELEASE + 0.05)
    assert len(hero.poison_clouds) == 1
    assert near.damage == second.damage == far.damage == 0

    advance(world, 1.0)
    assert near.damage == second.damage == POISON_DAMAGE
    assert far.damage == 0
    world.goblins.remove(near)
    advance(world, 1.0)
    assert near.damage == POISON_DAMAGE
    assert second.damage == 2 * POISON_DAMAGE

    advance(world, POISON_DURATION)
    assert not hero.poison_clouds


def test_thrown_ooze_is_priority_prey_and_grows_instead_of_taking_damage():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    target = world.add_goblin(Vec2(350, 300), "flag")
    target.update = lambda dt: None

    world.advance(DT)
    assert hero.ooze_cast_time is not None
    advance(world, CAST_RELEASE + 0.05)
    assert hero.ooze_toss is not None
    advance(world, TOSS_TIME + 0.05)
    servant = hero.ooze_servant
    assert isinstance(servant, AlchemicalOoze) and servant in world.stickmen
    paladin = world.add_stickman(Vec2(325, 300), "hero_paladin")
    assert paladin.target_priority < servant.target_priority
    assert Hunt().update(DT, target.center(), world.stickmen) is servant

    hp = servant.hp
    servant.hurt(5, servant.center(), Vec2(50, -20), "goblin", "ignored")
    assert servant.hp == hp and servant.damage == 0
    assert servant.target_scale > 1.0
    before = servant.ooze_scale
    advance(world, 0.25)
    assert servant.ooze_scale > before


def test_ooze_creeps_toward_monsters_then_hits_with_a_tendril():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    hero.update = lambda dt: None
    target = world.add_goblin(Vec2(340, 300), "flag")
    target.update = lambda dt: None
    servant = AlchemicalOoze(hero, hero.follower.current_anchor())
    world.stickmen.append(servant)
    start = servant.contact()

    advance(world, 1.0)
    assert 0.0 < servant.contact().x - start.x <= MOVE_SPEED * 1.05
    for _ in range(round(3 / DT)):
        world.advance(DT)
        if target.damage:
            break
    assert target.damage == TENDRIL_DAMAGE


def test_ooze_lashes_up_to_three_enemies_with_separate_tendrils():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    hero.update = lambda dt: None
    targets = [world.add_goblin(Vec2(x, 300), "flag") for x in (275, 295, 315)]
    for target in targets:
        target.update = lambda dt: None
    servant = AlchemicalOoze(hero, hero.follower.current_anchor())
    world.stickmen.append(servant)

    advance(world, 1.0)

    assert [target.damage for target in targets] == [TENDRIL_DAMAGE] * 3


def test_ooze_expires_after_twelve_seconds_without_leaving_a_body():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    hero.update = lambda dt: None
    servant = AlchemicalOoze(hero, hero.follower.current_anchor())
    hero.ooze_servant = servant
    world.stickmen.append(servant)

    advance(world, OOZE_LIFETIME - DT)
    assert servant in world.stickmen and servant.prey
    world.advance(DT)

    assert servant not in world.stickmen
    assert hero.ooze_servant is None


def test_beastform_reverts_after_ten_seconds_and_starts_its_cooldown():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_alchemist")
    target = world.add_goblin(Vec2(500, 300), "flag")
    target.update = lambda dt: None
    hero.ooze_cooldown = 999

    world.advance(DT)
    assert hero.beast is not None
    advance(world, MUTAGEN_SECONDS)
    assert hero.beast is None
    assert hero.mutagen_cooldown == pytest.approx(MUTAGEN_COOLDOWN, abs=DT)
    world.advance(DT)
    assert hero.beast is None


def test_mask_canister_tubes_and_gloves_render_without_changing_state():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_alchemist")
    advance(world, 0.4)
    image = QImage(800, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    before = (hero.contact(), hero.hp)
    painter = QPainter(image)
    draw_stickman(painter, hero)
    painter.end()
    assert before == (hero.contact(), hero.hp)
    assert any(
        image.pixelColor(x, y).alpha()
        for y in range(245, 310)
        for x in range(270, 330)
    )


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_and_preview_entrypoint(edge):
    session = DesktopSession(
        Rect(0, 0, 700, 500),
        Rect(0, 0, 700, 450),
        FakeWindowSource(),
        max_stickmen=0,
        defenders=(),
        seed=3,
    )
    hero = session.spawn_at_edge(edge, variant="hero_alchemist")
    assert isinstance(hero, HeroAlchemist) and hero in session.heroes
    assert session.hero_health_bars == [("The Biologist", 1)]

    preview = RigPreviewController(700, 400)
    preview.spawn_hero_alchemist()
    assert isinstance(preview.selected, HeroAlchemist)
    assert preview.selected.variant == "hero_alchemist"
