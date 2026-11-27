"""Hero Sorcerer model, skull focus, orbiting skulls, and spawn wiring."""

import math

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.heroes.hero_sorcerer import HeroSorcerer
from dungeons_desktops.game.heroes.hero_sorcerer.blood_cloud import BloodCloud
from dungeons_desktops.game.heroes.hero_sorcerer.corpsenado import Corpsenado
from dungeons_desktops.game.heroes.hero_sorcerer.render import (
    BLOOD_MIST,
    BONE,
    GRIP_GLOW,
    STORM_GREY,
    STORM_RED,
    _orbit,
)
from dungeons_desktops.game.heroes.hero_sorcerer.rotation import (
    RAPID_BOLT_SLOTS,
    ROTATION,
    Ability,
)
from dungeons_desktops.game.heroes.hero_sorcerer.skeletal_grasp import SkeletalGrasp
from dungeons_desktops.game.heroes.hero_sorcerer.weapon import SkullFocus
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.preview.controller import RigPreviewController

DT = 1 / 60


def advance_until(world, predicate, frames=120):
    for _ in range(frames):
        world.advance(DT)
        if predicate():
            return
    pytest.fail("condition did not become true")


def test_hero_uses_base_sorcerer_body_movement_and_casting_stats():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_sorcerer")
    ordinary = world.add_stickman(Vec2(500, 300), "sorcerer")

    assert isinstance(hero, HeroSorcerer)
    assert isinstance(hero.weapon, SkullFocus)
    assert hero.weapon.name == "floating skull"
    assert hero.display_name == "The Darkblood" and hero.hp == hero.max_hp == 60
    assert "hero_sorcerer" in HEROES and "hero_sorcerer" not in CLASSES
    assert hero.layout.skeleton.bones == ordinary.layout.skeleton.bones
    assert hero.calling.speed == ordinary.calling.speed
    assert hero.calling.reach == ordinary.calling.reach
    assert hero.calling.cooldown == ordinary.calling.cooldown


def test_skull_focus_casts_arcing_life_drain_and_heals_on_hit():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    target = world.add_goblin(Vec2(400, 300), "flag")
    target.update = lambda dt: None
    hero.damage = 5

    missile = None
    for _ in range(180):
        world.advance(DT)
        if missile is None and world.spells.missiles:
            missile = world.spells.missiles[0]
        if target.damage:
            break

    assert missile is not None and missile.kind == "life_drain" and missile.owner is hero
    assert len(missile.darts) == 1
    midpoint = missile.dart(0, 0.5)
    straight = missile.origin.lerp(missile.target, 0.5)
    assert midpoint.distance_to(straight) > 1.0
    assert target.damage == 1
    assert hero.damage == 4


def test_rotation_has_basic_bolts_between_specials_and_ends_with_three_bolts():
    assert ROTATION == (
        Ability.BOLT,
        Ability.SKELETAL_ARMS,
        Ability.BOLT,
        Ability.CORPSENADO,
        Ability.BOLT,
        Ability.BLOOD_CLOUD,
        Ability.BOLT,
        Ability.BOLT,
        Ability.BOLT,
    )
    assert RAPID_BOLT_SLOTS == {6, 7, 8}


def test_automatic_casts_follow_the_entire_rotation_then_reset():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    target = world.add_goblin(Vec2(400, 300), "flag")
    target.update = lambda dt: None
    world.hurt_monster = lambda *args, **kwargs: False
    released = []
    original = hero._release

    def record_release(weapon, transforms, facing):
        released.append(hero.casting)
        original(weapon, transforms, facing)

    hero._release = record_release
    for _ in range(900):
        world.advance(DT)
        if len(released) == len(ROTATION) and hero.queue_index == 0:
            break

    assert released == list(ROTATION)
    assert hero.queue_index == 0


def test_closing_three_bolts_use_a_rapid_cast_and_reset_the_cycle():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    target = world.add_goblin(Vec2(400, 300), "flag")
    target.update = lambda dt: None
    hero.queue_index = 6
    release_times = []
    elapsed = 0.0
    original = world.spells.cast_missile

    def record_missile(*args, **kwargs):
        release_times.append(elapsed)
        return original(*args, **kwargs)

    world.spells.cast_missile = record_missile
    for _ in range(180):
        world.advance(DT)
        elapsed += DT
        if len(release_times) == 3 and hero.queue_index == 0:
            break

    assert len(release_times) == 3
    assert all(
        b - a < 0.5
        for a, b in zip(release_times, release_times[1:], strict=False)
    )
    assert hero.queue_index == 0
    assert hero.weapon.duration == pytest.approx(SkullFocus.RAPID_DURATION)


def test_corpsenado_casts_on_its_rotation_slot_patrols_and_deals_repeated_damage():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    target = world.add_goblin(Vec2(320, 300), "flag")
    target.update = lambda dt: None
    hero.queue_index = 3

    advance_until(world, lambda: hero.corpsenado is not None)

    storm = hero.corpsenado
    assert storm is not None
    assert hero.weapon.busy
    assert not world.spells.missiles

    for _ in range(60):
        world.advance(DT)
    assert target.damage >= 1

    storm.update(4.0)
    assert storm.position.x == storm.right
    assert storm.direction == -1


def test_corpsenado_renders_grey_and_red_grave_winds():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    hero.corpsenado = Corpsenado.summon(hero, Vec2(320, 300))
    hero.corpsenado.age = 2.0

    image = QImage(800, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_stickman(painter, hero)
    painter.end()

    colors = {
        image.pixelColor(x, y).rgb()
        for x in range(250, 390)
        for y in range(190, 330)
    }
    assert STORM_GREY.rgb() in colors
    assert STORM_RED.rgb() in colors


def test_cloud_of_leeching_blood_drains_enemies_and_heals_the_sorcerer():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    target = world.add_goblin(Vec2(320, 300), "flag")
    target.update = lambda dt: None
    hero.damage = 5
    hero.queue_index = 5

    advance_until(world, lambda: hero.blood_cloud is not None)
    cloud = hero.blood_cloud
    assert cloud is not None
    assert hero.weapon.busy
    assert not world.spells.missiles
    hero.weapon.cancel()
    hero._clear_rotation_cast()
    hero.cast_wait = 999.0

    for _ in range(100):
        world.advance(DT)

    assert cloud.ticks >= 1
    assert cloud.drain_flash > 0.0
    assert target.damage == 1
    assert hero.damage == 4


def test_blood_cloud_is_cut_out_by_desktop_windows_for_damage_and_rendering():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(120, 300), "hero_sorcerer")
    target = world.add_goblin(Vec2(360, 300), "flag")
    target.update = lambda dt: None
    cloud = BloodCloud(hero, target.center())
    hero.blood_cloud = cloud
    cloud.age = 2.0
    cloud.center = target.center()
    cover = Rect(cloud.center.x - 18, cloud.center.y - 18, 36, 36)
    world.boxes = [cover]

    cloud._drain_enemies()
    assert target.damage == 0

    image = QImage(800, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_stickman(painter, hero)
    painter.end()

    assert image.pixelColor(round(cloud.center.x), round(cloud.center.y)).alpha() == 0
    assert any(
        image.pixelColor(x, y).red() >= BLOOD_MIST.red()
        and image.pixelColor(x, y).alpha() > 0
        for x in range(round(cloud.center.x - 80), round(cloud.center.x + 81))
        for y in range(round(cloud.center.y - 45), round(cloud.center.y + 46))
        if not cover.contains(Vec2(x, y))
    )


def test_skeletal_grasp_uses_lich_surface_reach_and_holds_crushes_enemies():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    target = world.add_goblin(Vec2(320, 300), "flag")
    updates = 0

    def count_update(dt):
        nonlocal updates
        updates += 1

    target.update = count_update
    hero.queue_index = 1

    advance_until(world, lambda: hero.skeletal_grasp is not None)
    grasp = hero.skeletal_grasp
    assert grasp is not None and grasp.arms
    assert hero.weapon.busy
    assert not world.spells.missiles

    for _ in range(90):
        world.advance(DT)

    assert grasp.holds(target)
    assert sum(arm.held is target for arm in grasp.arms) == len(grasp.arms)
    assert target.damage >= 1
    assert updates < 90


def test_skeletal_grasp_renders_jointed_bone_arms_and_hands():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(200, 300), "hero_sorcerer")
    world.add_goblin(Vec2(320, 300), "flag")
    hero.skeletal_grasp = SkeletalGrasp.summon(hero, Vec2(320, 300))
    assert hero.skeletal_grasp is not None
    hero.skeletal_grasp.age = 1.0
    hero.skeletal_grasp.update(DT)

    image = QImage(800, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_stickman(painter, hero)
    painter.end()

    bone_pixels = sum(
        image.pixelColor(x, y).red() >= BONE.red() - 12
        and image.pixelColor(x, y).green() >= BONE.green() - 12
        and image.pixelColor(x, y).blue() >= BONE.blue() - 12
        for x in range(245, 390)
        for y in range(225, 305)
    )
    grip_pixels = sum(
        image.pixelColor(x, y).red() >= GRIP_GLOW.red() - 20
        and image.pixelColor(x, y).green() < 70
        and image.pixelColor(x, y).blue() < 90
        for x in range(245, 390)
        for y in range(225, 305)
    )
    assert bone_pixels > 0
    assert grip_pixels > 10


def test_three_skulls_orbit_at_evenly_spaced_phases_and_move():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_sorcerer")
    transforms = hero.transforms()
    first = [_orbit(hero, transforms, index)[0] for index in range(3)]
    assert all(
        first[index].distance_to(first[(index + 1) % 3]) > 10.0
        for index in range(3)
    )

    for _ in range(30):
        world.advance(DT)
    transforms = hero.transforms()
    moved = [_orbit(hero, transforms, index)[0] for index in range(3)]
    assert all(
        before.distance_to(after) > 2.0
        for before, after in zip(first, moved, strict=True)
    )


def test_skull_face_focus_and_all_three_orbiters_render():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(400, 300), "hero_sorcerer")
    hero.weapon.clock = 0.43
    transforms = hero.transforms()
    centers = [
        transforms[hero.layout.head].end,
        hero.weapon.tip(transforms, hero.facing),
        *[_orbit(hero, transforms, index)[0] for index in range(3)],
    ]
    assert len(centers) == 5

    image = QImage(800, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_stickman(painter, hero)
    painter.end()

    for center in centers:
        assert any(
            sum(
                abs(channel - expected)
                for channel, expected in zip(
                    image.pixelColor(x, y).getRgb()[:3],
                    BONE.getRgb()[:3],
                    strict=True,
                )
            ) <= 50
            for x in range(math.floor(center.x - 7), math.ceil(center.x + 8))
            for y in range(math.floor(center.y - 7), math.ceil(center.y + 8))
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
    hero = session.spawn_at_edge(edge, variant="hero_sorcerer")
    assert isinstance(hero, HeroSorcerer) and hero in session.heroes
    assert session.hero_health_bars == [("The Darkblood", 1)]

    preview = RigPreviewController(700, 400)
    preview.spawn_hero_sorcerer()
    assert isinstance(preview.selected, HeroSorcerer)
    assert preview.selected.variant == "hero_sorcerer"
