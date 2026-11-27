"""Changing window bounds or entering fullscreen must not despawn living characters."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import SUPPORTED_DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.adventurers.actor import StickMode
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind

SCREEN = Rect(0, 0, 1400, 900)
USABLE = Rect(0, 30, 1400, 800)
WINDOW = WindowRecord(1, Rect(300, 400, 400, 250))
FULLSCREEN = WindowRecord(2, Rect(0, 30, 1400, 800))
DT = 1 / 60


def scene(defenders=()):
    source = FakeWindowSource([WINDOW])
    world = DesktopSession(SCREEN, USABLE, source, max_stickmen=0, defenders=defenders, seed=5)
    return world, source


def run(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


@pytest.mark.parametrize("variant", [
    "fighter", "hero_fighter", "hero_druid", "hero_barbarian",
    "hero_wizard", "hero_rogue", "hero_paladin", "hero_ranger", "hero_cleric",
    "hero_alchemist", "hero_sorcerer",
])
@pytest.mark.parametrize("change", ["shrink", "fullscreen"])
def test_living_heroes_and_adventurers_survive_loss_of_window_support(variant, change):
    world, source = scene()
    actor = world.add_stickman(Vec2(650, 400), variant)
    actor.damage = 1
    health = actor.hp
    if change == "shrink":
        source.records = [WindowRecord(1, Rect(300, 400, 200, 250))]
        assert world.poll()
    else:
        # Quartz can briefly omit the app window as it switches fullscreen Spaces.
        source.records = []
        assert world.poll()
        run(world, 0.25)
        source.records = [FULLSCREEN]
        assert world.poll()
    run(world, 5)
    assert actor in world.stickmen and actor.animated and not actor.gone
    if variant == "hero_cleric":
        assert actor.hp >= health  # His normal healing pulse may restore the test wound.
    else:
        assert actor.hp == health
    assert world.kills == 0
    assert actor.planner.owns(actor.follower.current_anchor().surface)
    if variant.startswith("hero_"):
        assert actor in world.heroes


@pytest.mark.parametrize("kind", [SurfaceKind.RIGHT, SurfaceKind.CEILING])
def test_climbing_or_hanging_adventurer_recovers_after_resize(kind):
    world, source = scene()
    surface = next(s for s in world.planner.surfaces if s.box == 0 and s.kind is kind)
    anchor = Anchor(surface, surface.point_at((surface.low + surface.high) / 2))
    actor = world._add_stickman(anchor, "paladin", False)
    assert actor.follower.current_anchor().surface.box == 0
    assert not actor.follower.current_anchor().surface.walkable
    source.records = [WindowRecord(1, Rect(300, 400, 600, 320))]
    assert world.poll()
    assert actor.mode is StickMode.RAGDOLL
    run(world, 5)
    assert actor in world.stickmen and actor.animated and actor.hp == actor.max_hp


def test_repeated_fullscreen_transitions_cannot_turn_falling_characters_into_corpses():
    world, source = scene()
    party = [world.add_stickman(Vec2(x, 400), "fighter") for x in (450, 550, 650)]
    for _ in range(3):
        for records in ([], [FULLSCREEN], [], [WINDOW]):
            source.records = records
            assert world.poll()
            run(world, 0.2)
    run(world, 5)
    assert all(actor in world.stickmen and actor.animated for actor in party)
    assert all(actor.hp == actor.max_hp for actor in party)
    assert world.kills == 0


def test_stealth_immunity_does_not_leave_slayer_on_a_removed_window():
    world, source = scene()
    actor = world.add_stickman(Vec2(650, 400), "hero_rogue")
    run(world, 3.1)
    assert actor.stealthed
    source.records = []
    assert world.poll()
    run(world, 5)
    assert actor in world.stickmen and actor.animated and actor.hp == actor.max_hp
    assert actor.planner.owns(actor.follower.current_anchor().surface)


def test_window_changes_do_not_revive_a_character_killed_in_combat():
    world, source = scene()
    actor = world.add_stickman(Vec2(650, 400), "fighter")
    actor.hurt(100, actor.center(), Vec2(0, 0), "test", "defeated")
    source.records = [FULLSCREEN]
    assert world.poll()
    run(world, 5)
    assert actor not in world.stickmen and actor.hp == 0 and world.kills == 1


@pytest.mark.parametrize("kind", SUPPORTED_DEFENDERS)
def test_defenders_keep_identity_and_health_through_resize_and_fullscreen(kind):
    world, source = scene((kind,))
    defenders = list(world.live_monsters)
    for defender in defenders:
        defender.damage = 1
    health = [defender.hp for defender in defenders]
    for records in (
        [WindowRecord(1, Rect(300, 400, 200, 250))], [], [FULLSCREEN], [WINDOW],
    ):
        source.records = records
        assert world.poll()
        run(world, 0.2)
    run(world, 1)
    assert all(defender in world.live_monsters for defender in defenders)
    assert [defender.hp for defender in defenders] == health
    assert world.monster_kills == 0 and not world.fallen
