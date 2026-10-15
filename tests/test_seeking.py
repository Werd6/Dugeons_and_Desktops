"""Adventurers fighting from walls and ceilings, and going after the monsters they spot."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.creatures.goblin import build_goblin
from dungeons_desktops.creatures.stick_figure import build_stick_figure
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind
from dungeons_desktops.rig.locomotion import LocomotionDriver, LocomotionInput, PoseMode
from dungeons_desktops.rig.weapons import Banner, GoblinSword, SpearThrower, Sword
from dungeons_desktops.systems.actors import SEEK_RADIUS, Stickman
from dungeons_desktops.systems.world import SimWorld

DT = 1.0 / 60.0
FLOOR = 700.0
WINDOW = Rect(400, 250, 300, 450)
"""Its left wall is climbed facing +x."""
LEDGE = Rect(300, 470, 85, 230)
"""Behind a climber on that wall, with a gap he can reach across."""


def run(world: SimWorld, seconds: float, until=None) -> bool:
    for _ in range(int(seconds / DT)):
        world.advance(DT)
        if until is not None and until():
            return True
    return False


def frozen(monster):
    monster.update = lambda dt: None
    return monster


def climber(world: SimWorld, variant: str, y: float) -> Stickman:
    wall = next(s for s in world.planner.surfaces if s.kind is SurfaceKind.LEFT and s.box == 0)
    man = Stickman(world, Anchor(wall, wall.closest_point(Vec2(WINDOW.left, y))), variant)
    world.stickmen.append(man)
    return man


def hits_on(world: SimWorld) -> list:
    hits = []
    hurt = world.hurt_monster

    def counting(monster, amount, point, push, **how):
        hits.append(monster)
        return hurt(monster, amount, point, push, **how)

    world.hurt_monster = counting
    return hits


def climbing_world() -> SimWorld:
    return SimWorld([WINDOW, LEDGE], FLOOR, 1200.0, ceiling=20.0, seed=3)


# ----- fighting from a wall ------------------------------------------------------


@pytest.mark.parametrize(
    ("variant", "y", "spot", "behind"),
    [
        ("barbarian", 275.0, Vec2(418, 250), False),
        ("barbarian", 480.0, Vec2(374, 470), True),
        ("rogue", 480.0, Vec2(374, 470), True),
        ("wizard", 480.0, Vec2(310, 470), True),
        ("druid", 480.0, Vec2(374, 470), True),
    ],
)
def test_a_climber_attacks_a_monster_in_reach_without_letting_go(variant, y, spot, behind):
    world = climbing_world()
    man = climber(world, variant, y)
    man.set_goal(Vec2(450, WINDOW.top))
    goblin = frozen(world.add_goblin(spot, "sword"))
    hits = hits_on(world)
    support = man.weapon.support_chain.bones[-1]
    grip = None
    for _ in range(int(3.0 / DT)):
        world.advance(DT)
        if man.weapon.busy and grip is None:
            grip = man.transforms()[support].end
            assert man.weapon.reverse is behind
        if grip is not None and man.weapon.busy:
            assert man.transforms()[support].end.distance_to(grip) < 8.0, "the other hand holds on"
        if hits:
            break
    assert hits == [goblin]
    assert man.animated and man.locomotion.mode is PoseMode.CLIMB


def test_a_climber_carries_on_up_once_the_fight_is_over():
    world = climbing_world()
    man = climber(world, "barbarian", 480.0)
    man.set_goal(Vec2(450, WINDOW.top))
    goblin = frozen(world.add_goblin(Vec2(374, 470), "sword"))
    hits = hits_on(world)
    assert run(world, 2.0, lambda: bool(hits))
    world.goblins.remove(goblin)
    assert run(world, 25.0, lambda: man.contact().y <= WINDOW.top + 1.0 and not man.follower.moving)
    assert man.animated


def test_a_climbing_ranger_holds_fire_until_the_window_corner_is_out_of_the_way():
    world = climbing_world()
    man = climber(world, "ranger", 275.0)
    man.set_goal(Vec2(450, WINDOW.top))
    frozen(world.add_goblin(Vec2(520, 250), "sword"))
    hits = hits_on(world)
    stuck_at_once = []
    seen = set()

    def watch() -> bool:
        for arrow in world.spells.arrows:
            if id(arrow) not in seen:
                seen.add(id(arrow))
                stuck_at_once.append(arrow.stuck is not None)
        return bool(hits)

    assert run(world, 5.0, watch)
    assert stuck_at_once and not any(stuck_at_once), "no arrow sticks in his own window"


def test_an_alchemist_on_a_wall_doesnt_blow_his_bomb_up_in_his_hand():
    world = climbing_world()
    man = climber(world, "alchemist", 275.0)
    man.set_goal(Vec2(450, WINDOW.top))
    frozen(world.add_goblin(Vec2(520, 250), "sword"))
    hits = hits_on(world)
    bursts = []
    seen = set()

    def watch() -> bool:
        for burst in world.vials.explosions:
            if id(burst) not in seen:
                seen.add(id(burst))
                bursts.append(burst.center)
        return bool(hits)

    assert run(world, 5.0, watch)
    assert all(b.distance_to(man.center()) > 40.0 for b in bursts)


def test_hanging_from_an_underside_he_still_fights():
    world = SimWorld(
        [Rect(800, 300, 200, 60), Rect(1004, 385, 120, 315)], FLOOR, 1300.0, ceiling=20.0, seed=3
    )
    ceiling = next(
        s for s in world.planner.surfaces if s.kind is SurfaceKind.CEILING and s.box == 0
    )
    man = Stickman(world, Anchor(ceiling, ceiling.closest_point(Vec2(996, 386))), "paladin")
    world.stickmen.append(man)
    frozen(world.add_goblin(Vec2(1014, 385), "sword"))
    hits = hits_on(world)
    assert run(world, 2.0, lambda: bool(hits))
    assert man.animated and man.locomotion.mode is PoseMode.HANG


# ----- goblins are unchanged --------------------------------------------------------


def standing() -> LocomotionInput:
    return LocomotionInput(PoseMode.WALK, Vec2(100.0, 300.0), 1, "floor")


@pytest.mark.parametrize("weapon_type", [GoblinSword, SpearThrower, Banner])
def test_goblin_weapons_dont_cling(weapon_type):
    """A goblin's weapon is held exactly in its `held_modes`, attacking or not."""
    layout = build_goblin()
    weapon = weapon_type(layout)
    driver = LocomotionDriver(layout, standing(), upper=None)
    weapon.start()
    for mode in (PoseMode.CLIMB, PoseMode.HANG):
        weapon.apply(driver.pose, mode, DT, frozenset())
        assert weapon.held is (mode in weapon.held_modes)


def test_an_adventurers_weapon_comes_out_on_a_wall_only_to_attack():
    layout = build_stick_figure()
    sword = Sword(layout)
    driver = LocomotionDriver(layout, standing(), upper=None)
    sword.apply(driver.pose, PoseMode.CLIMB, DT, frozenset())
    assert not sword.held
    sword.start()
    sword.apply(driver.pose, PoseMode.CLIMB, DT, frozenset())
    assert sword.held


# ----- going after monsters ---------------------------------------------------------


def open_world() -> SimWorld:
    return SimWorld([], FLOOR, 1400.0, ceiling=20.0, seed=3)


def test_a_wanderer_goes_after_a_monster_within_the_seek_radius():
    world = open_world()
    man = world.add_stickman(Vec2(100, FLOOR), "barbarian", wander=True)
    goblin = frozen(world.add_goblin(Vec2(100 + SEEK_RADIUS - 40, FLOOR), "sword"))
    hits = hits_on(world)
    run(world, 1.0)
    assert man.quarry is goblin
    assert run(world, 8.0, lambda: bool(hits))
    assert goblin.center().distance_to(man.center()) <= man.calling.reach + 12.0


def test_a_monster_beyond_the_seek_radius_goes_unnoticed():
    world = open_world()
    man = world.add_stickman(Vec2(100, FLOOR), "barbarian", wander=True)
    frozen(world.add_goblin(Vec2(100 + SEEK_RADIUS + 120, FLOOR), "sword"))
    for _ in range(int(3.0 / DT)):
        world.advance(DT)
        if man.center().distance_to(world.goblins[0].center()) > SEEK_RADIUS:
            assert man.quarry is None


@pytest.mark.parametrize("variant", ["ranger", "wizard", "alchemist"])
def test_a_shooter_closes_to_range_and_holds_there(variant):
    world = open_world()
    man = world.add_stickman(Vec2(100, FLOOR), variant, wander=True)
    goblin = frozen(world.add_goblin(Vec2(100 + SEEK_RADIUS - 20, FLOOR), "sword"))
    hits = hits_on(world)
    run(world, 8.0)
    distance = goblin.center().distance_to(man.center())
    assert hits
    assert distance <= man.calling.reach
    assert distance > 0.4 * man.calling.reach, "he stays back rather than walking up to it"


def test_a_cleric_hangs_near_the_fight():
    world = open_world()
    cleric = world.add_stickman(Vec2(100, FLOOR), "cleric", wander=True)
    goblin = frozen(world.add_goblin(Vec2(400, FLOOR), "sword"))
    run(world, 8.0)
    assert goblin.center().distance_to(cleric.center()) < 120.0


def test_a_monster_out_of_reach_in_the_air_is_given_up_on_and_he_wanders_again():
    world = open_world()
    man = world.add_stickman(Vec2(300, FLOOR), "barbarian", wander=True)
    dragon = frozen(world.add_dragon(Vec2(320, FLOOR - 300), facing=1))
    run(world, 1.0)
    assert dragon in man._shunned and man.quarry is None
    assert run(world, 3.0, lambda: man.follower.moving), "he wanders off instead of waiting"


def test_a_burrowed_worm_is_sought_only_by_a_druid():
    world = open_world()
    druid = world.add_stickman(Vec2(300, FLOOR), "druid", wander=True)
    barbarian = world.add_stickman(Vec2(320, FLOOR), "barbarian", wander=True)
    worm = frozen(world.add_worm(Vec2(500, FLOOR + 25), 0.0))
    run(world, 1.0)
    assert druid.quarry is worm
    assert barbarian.quarry is None


def test_a_player_led_adventurer_does_not_seek():
    world = open_world()
    man = world.add_stickman(Vec2(100, FLOOR), "barbarian")
    frozen(world.add_goblin(Vec2(300, FLOOR), "sword"))
    run(world, 2.0)
    assert man.quarry is None and not man.follower.moving
