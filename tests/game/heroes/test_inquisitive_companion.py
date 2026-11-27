"""The passive cat follows surface routes and is never a combat target."""

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import PoseMode


def test_cat_follows_up_a_window_and_moves_with_its_support():
    world = SimWorld([Rect(180, 100, 200, 200)], 300, 600, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_wizard")
    cat = hero.cat
    assert cat not in world.actors and cat not in world.monsters()
    hero.set_goal(Vec2(250, 100))
    modes = set()
    for _ in range(60 * 25):
        world.advance(1 / 60)
        modes.add(cat.follower.command().mode)
    assert PoseMode.CLIMB in modes
    assert cat.feet.distance_to(hero.contact()) <= 15 and cat.feet.y == 100
    before = cat.feet
    world.apply_terrain(TerrainChange(moves={0: Vec2(20, -10)}), [Rect(200, 90, 200, 200)])
    assert cat.feet == before + Vec2(20, -10)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    for _ in range(20):
        world.advance(1 / 60)
    assert cat.opacity == 0


def test_each_iggy_has_its_own_cat_and_it_returns_after_getting_up():
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(100, 300), "hero_wizard")
    other = world.add_stickman(Vec2(400, 300), "hero_wizard")
    assert hero.cat is not other.cat and hero.cat.owner is hero
    hero.go_ragdoll()
    for _ in range(30):
        world.advance(1 / 60)
    assert hero.cat.opacity == 0 and other.cat.opacity == 1
    hero.get_up()
    for _ in range(30):
        world.advance(1 / 60)
    assert hero.cat.opacity == 1 and hero.cat.feet.distance_to(hero.contact()) < 20
