"""The sorcerer shares caster behavior, with an orb and a single fire spark."""

from random import Random

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.model import CLASSES, build_stick_figure
from dungeons_desktops.game.adventurers.spells import Spells
from dungeons_desktops.game.adventurers.weapons import FireOrb
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.render.scene import draw_spells, draw_stickman
from dungeons_desktops.rig.locomotion import LocomotionDriver, LocomotionInput, PoseMode
from dungeons_desktops.rig.skeleton import forward_kinematics

DT = 1 / 60


def scene(distance=220):
    world = SimWorld([], 200.0, 800.0, ceiling=0.0, seed=3)
    sorcerer = world.add_stickman(Vec2(100, 200), "sorcerer")
    goblin = world.add_goblin(Vec2(100 + distance, 200), "flag")
    goblin.update = lambda dt: None
    return world, sorcerer, goblin


def test_sorcerer_releases_one_fire_spark_from_its_orb_and_hits_once():
    world, sorcerer, goblin = scene()
    assert CLASSES["sorcerer"].reach == CLASSES["wizard"].reach
    shot = None
    for _ in range(120):
        world.advance(DT)
        if shot is None and world.spells.missiles:
            shot = world.spells.missiles[0]
            assert (
                shot.origin.distance_to(sorcerer.weapon.tip(sorcerer.transforms(), sorcerer.facing))
                < 0.01
            )
        if goblin.damage:
            break
    assert shot is not None and shot.kind == "fire" and len(shot.darts) == 1
    assert shot.owner is sorcerer and shot.monster is goblin and not shot.hostile
    assert goblin.damage == 1
    assert any(spark.color == "fire" for spark in world.spells.sparks)


def test_sorcerer_waits_outside_wizard_range():
    world, sorcerer, goblin = scene(distance=350)
    for _ in range(180):
        world.advance(DT)
    assert not sorcerer.weapon.busy and not world.spells.missiles and goblin.damage == 0


@pytest.mark.parametrize("facing", [-1, 1])
def test_orb_floats_above_the_hand_and_releases_once_during_a_cast(facing):
    layout = build_stick_figure()
    orb = FireOrb(layout)
    state = LocomotionInput(PoseMode.WALK, Vec2(100, 200), facing, "floor")
    driver = LocomotionDriver(layout, state, upper=orb)
    driver.update(DT, state)
    orb.start()
    releases = 0
    for _ in range(60):
        driver.update(DT, state)
        transforms = forward_kinematics(layout.skeleton, driver.pose)
        hand = transforms[orb.hand_chain.bones[-1]].end
        center = orb.tip(transforms, facing)
        assert center.x == pytest.approx(hand.x)
        assert 4 < hand.y - center.y < 8
        assert {stroke.kind for stroke in orb.strokes(transforms, facing)} == {"orb", "flash"}
        releases += orb.take_release()
    assert releases == 1
    assert not orb.strokes(transforms, facing, slung=True)


def test_fire_spark_uses_shared_target_loss_and_owner_hit_handling():
    spells = Spells(Random(2))
    target, owner = object(), object()
    origin, destination = Vec2(0, 0), Vec2(100, 0)
    spells.cast_missile(origin, target, destination, owner=owner, kind="fire")
    assert spells.missiles[0].dart(0, 0.5) == Vec2(50, 0)
    hits = spells.update(1.0, lambda _: destination, lambda _: None, [], 200)
    assert len(hits) == 1 and hits[0].owner is owner and hits[0].monster is target
    spells.cast_missile(origin, target, destination, owner=owner, kind="fire")
    assert not spells.update(1.0, lambda _: None, lambda _: None, [], 200)
    assert not spells.missiles


@pytest.mark.parametrize("facing", [-1, 1])
def test_sorcerer_costume_orb_and_fire_spark_render(facing):
    world, sorcerer, _ = scene()
    world.goblins.clear()
    world.advance(DT)
    sorcerer.follower.facing = facing
    world.advance(DT)
    assert sorcerer.facing == facing
    image = QImage(400, 240, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        draw_stickman(painter, sorcerer)
        world.spells.cast_missile(Vec2(200, 180), None, Vec2(300, 180), kind="fire")
        draw_spells(painter, world.spells)
    finally:
        painter.end()
    colors = {image.pixelColor(x, y).name() for x in range(70, 130) for y in range(160, 205)}
    assert "#fa74b8" in colors  # Pink limbs.
    assert "#ffd6ea" in colors  # Pale scarf.
    assert "#ff6eb0" in colors  # Floating orb.
