"""Boulder recovery permits pursuit and other attacks without allowing repeat throws."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.heroes.the_mighty.combat import BOULDER_COOLDOWN, Attack
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def scene(wander=False, boxes=()):
    world = SimWorld(list(boxes), 300, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_barbarian", wander=wander)
    target = world.add_goblin(Vec2(550, 300), "flag")
    target.max_hp = 1000
    return world, hero, target


@pytest.mark.parametrize("manual", [False, True])
def test_throw_cooldown_blocks_repeat_throws_and_survives_rage(manual, monkeypatch):
    _, hero, target = scene()
    releases = []
    throw = hero.combat.throw

    def record_throw(*args):
        releases.append(hero.time)
        throw(*args)

    monkeypatch.setattr(hero.combat, "throw", record_throw)
    hero.attack()
    assert hero.boulder_cooldown == 0  # Interrupted windups do not consume the throw.
    for frame in range(450):
        # Keep this enemy at long range as the hero pursues it.
        anchor = target.planner.anchor_near(hero.contact() + Vec2(400, 0), walk_only=True)
        target.follower.reset(anchor)
        target.locomotion.teleport(target.follower.command())
        if manual and frame % 10 == 0:
            hero.attack()
        hero.update(DT)
        if frame == 32:
            assert hero.boulder_cooldown == pytest.approx(BOULDER_COOLDOWN)
        if frame == 120:
            remaining = hero.boulder_cooldown
            hero.hurt(1, hero.center(), Vec2(0, 0), "test", "defeated")
            assert hero.boulder_cooldown == remaining
        if releases and hero.time - releases[0] < BOULDER_COOLDOWN:
            assert len(releases) == 1
    assert len(releases) == 2
    assert BOULDER_COOLDOWN <= releases[1] - releases[0] < BOULDER_COOLDOWN + 0.7


@pytest.mark.parametrize("wander", [False, True])
def test_paths_from_beyond_regular_seek_range_then_leaps_during_throw_cooldown(wander):
    _, hero, target = scene(wander)
    hero.attack()
    for _ in range(420):
        hero.update(DT)
        if hero.leap is not None:
            break
    assert hero.leap is not None and hero.weapon.action is Attack.LEAP
    assert hero.boulder_cooldown > 0
    assert hero.contact().x > 300
    assert hero.quarry is target
    for _ in range(90):
        hero.update(DT)
        if hero.leap is None:
            break
    assert target.damage == 6 + 8


def test_cooldown_pursuit_climbs_an_obstacle_instead_of_resetting_its_route():
    _, hero, _ = scene(True, [Rect(160, 100, 30, 200)])
    hero.attack()
    modes = set()
    for _ in range(240):
        hero.update(DT)
        modes.add(hero.locomotion.mode)
    assert PoseMode.CLIMB in modes
    assert hero.boulder_cooldown > 0
    assert hero.contact().y < 290
    assert hero.animated
