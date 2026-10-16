import math

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.systems.actors import StickMode
from dungeons_desktops.systems.minotaur import (
    CHARGE_EDGE,
    CRUSH_DAMAGE,
    PUNCH_DAMAGE,
    RAGE_PACE,
    RAGE_TIME,
    SMASH_DAMAGE,
    STOMP_DAMAGE,
    STOMP_QUAKE,
    SWIPE_DAMAGE,
    THROW_COOLDOWN,
    THROW_DAMAGE,
    THROW_SELF,
    TRAMPLE_DAMAGE,
    Minotaur,
)
from dungeons_desktops.systems.mortal import MINOTAUR_HP
from dungeons_desktops.systems.world import SimWorld

STEP = 1 / 60
WALL_BLOWS = ("punch", "swipe")
"""Up a wall, it punches someone lined up with it, or swipes at anyone else in reach."""
FLOOR = 700.0
WIDTH = 1400.0
TOP = 20.0


def world_with(*boxes: Rect, seed: int = 3) -> SimWorld:
    return SimWorld(list(boxes), FLOOR, WIDTH, ceiling=TOP, seed=seed)


def run(world, seconds, until=None, each=None) -> bool:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()
        if until is not None and until():
            return True
    return until is None


def send(bull: Minotaur, point: Vec2) -> None:
    assert bull._route_to(bull.planner.anchor_near(point, walk_only=True))


def arrived(bull: Minotaur, point: Vec2, near: float = 6.0):
    return lambda: bull.grounded and not bull.route and bull.position.distance_to(point) <= near


def standing(world: SimWorld, x: float, y: float = FLOOR, variant: str = "paladin"):
    """An adventurer who stays put and doesn't fight back."""
    man = world.add_stickman(Vec2(x, y), variant)
    man.wander = False
    man.paralyze(60.0)
    return man


# ----- getting about ---------------------------------------------------------------


def test_it_spawns_on_the_floor_and_walks_along_it():
    world = world_with()
    bull = world.add_minotaur(Vec2(200, FLOOR))
    assert bull.grounded and bull.position.y == FLOOR and bull.hp == bull.max_hp
    send(bull, Vec2(600, FLOOR))
    track = []
    assert run(world, 30.0, until=arrived(bull, Vec2(600, FLOOR)), each=lambda: track.append(bull))
    assert all(abs(b.position.y - FLOOR) < 0.5 for b in track)


def test_it_walks_the_floor_under_a_window_hanging_over_the_bottom_edge():
    world = world_with(Rect(200, 200, 1000, FLOOR - 24 - 200))
    bull = world.add_minotaur(Vec2(80, FLOOR))
    send(bull, Vec2(1320, FLOOR))
    track = []
    assert run(world, 40.0, until=arrived(bull, Vec2(1320, FLOOR)), each=lambda: track.append(bull))
    assert track and all(abs(b.position.y - FLOOR) < 0.5 for b in track)


def test_it_walks_a_window_top_tucked_under_the_top_of_the_screen():
    top = 50.0
    world = world_with(Rect(200, top, 1000, 200))
    bull = world.add_minotaur(Vec2(280, top))
    assert bull.position.y == top
    send(bull, Vec2(1100, top))
    track = []
    assert run(world, 40.0, until=arrived(bull, Vec2(1100, top)), each=lambda: track.append(bull))
    assert track and all(abs(b.position.y - top) < 0.5 for b in track)


def test_it_walks_along_a_window_top():
    world = world_with(Rect(300, 450, 500, 250))
    bull = world.add_minotaur(Vec2(350, 450))
    assert bull.position.y == 450 and bull.surface.box == 0
    send(bull, Vec2(750, 450))
    assert run(world, 30.0, until=arrived(bull, Vec2(750, 450)))
    assert bull.position.y == 450


# ----- the charge ------------------------------------------------------------------


def test_it_charges_a_foe_along_its_surface_trampling_everyone_once():
    world = world_with(Rect(1200, 450, 150, 250))
    bull = world.add_minotaur(Vec2(150, FLOOR))
    men = [standing(world, x) for x in (450, 475, 500)]
    charged, trampled = [], set()

    def watch():
        if bull.action == "charge":
            charged.append(bull.position.x)
        for man in men:
            if man.damage:
                trampled.add(man)

    assert run(world, 10.0, until=lambda: bull.action == "winded", each=watch)
    assert charged and bull.trampled == 3 and trampled == set(men)
    assert all(man.damage == TRAMPLE_DAMAGE for man in men)
    assert bull.position.x > 500


def test_a_charge_stops_short_of_the_end_of_its_window_top():
    world = world_with(Rect(300, 450, 500, 250))
    bull = world.add_minotaur(Vec2(330, 450))
    bull.facing = 1
    man = standing(world, 760, 450)
    assert run(world, 10.0, until=lambda: bull.action == "winded")
    assert man.damage == TRAMPLE_DAMAGE
    assert bull.position.y == 450 and bull.position.x <= 800 - CHARGE_EDGE + 0.5
    run(world, 1.0)
    assert bull.surface is not None and bull.surface.box == 0


def test_no_charge_at_a_foe_on_another_surface():
    world = world_with(Rect(500, 450, 400, 250))
    bull = world.add_minotaur(Vec2(150, FLOOR))
    standing(world, 700, 450)
    actions = set()
    run(world, 4.0, each=lambda: actions.add(bull.action))
    assert "charge" not in actions and "windup" not in actions


# ----- fists and stomps ----------------------------------------------------------------


def blows(world: SimWorld, bull: Minotaur, seconds: float, until=None) -> list[str]:
    """Every smash, stomp or hurl it starts in `seconds`."""
    seen: list[str] = []
    last = [None]

    def watch():
        if bull.action in ("punch", "smash", "stomp", "hurl") and last[0] != bull.action:
            seen.append(bull.action)
        last[0] = bull.action

    run(world, seconds, until=until, each=watch)
    return seen


def melee_world(gap: float) -> tuple[SimWorld, Minotaur, object]:
    world = world_with()
    bull = world.add_minotaur(Vec2(400, FLOOR))
    bull.facing, bull.charge_wait = 1, 1e9
    man = standing(world, 400 + gap)
    return world, bull, man


def test_its_stomp_lands_on_a_foe_in_reach_for_6():
    world, bull, man = melee_world(12)
    assert blows(world, bull, 2.0, until=lambda: man.damage)[:1] == ["stomp"]
    run(world, 0.3)
    assert man.damage == STOMP_DAMAGE and bull.kills == {
        "charge": 0,
        "punch": 0,
        "smash": 0,
        "stomp": 0,
        "quake": 0,
        "crush": 0,
        "throw": 0,
        "swipe": 0,
    }


def test_its_stomp_shakes_the_ground_flattening_those_close_by_for_1():
    world, bull, man = melee_world(12)
    beyond = standing(world, 440)
    seen = blows(world, bull, 2.0, until=lambda: bull.action is None and man.damage)
    assert seen == ["stomp"]
    assert man.damage == STOMP_DAMAGE and beyond.damage == STOMP_QUAKE
    assert beyond.mode is StickMode.RAGDOLL


def test_its_fists_smash_the_ground_under_a_foe_for_5():
    world, bull, man = melee_world(36)
    assert blows(world, bull, 2.0, until=lambda: man.damage)[:1] == ["smash"]
    run(world, 0.3)
    assert man.damage == SMASH_DAMAGE


def test_it_hurls_someone_in_reach_at_a_farther_foe_for_8():
    world, bull, victim = melee_world(16)
    target = standing(world, 560)
    seen = blows(world, bull, 3.0, until=lambda: target.damage)
    assert seen[0] == "hurl"
    assert target.damage == THROW_DAMAGE and bull.kills["throw"] == 1
    assert bull.throw_wait > THROW_COOLDOWN - 2.0
    assert victim.damage == THROW_SELF and victim.mode is StickMode.RAGDOLL


def test_the_one_it_hurls_lands_down_range_not_back_where_it_grabbed_him():
    world, bull, victim = melee_world(16)
    standing(world, 700)
    grabbed = victim.contact().x
    flown = []

    def watch():
        if bull._thrown is not None:
            flown.append(victim.center().x)

    assert run(world, 3.0, until=lambda: victim.mode is StickMode.RAGDOLL and flown, each=watch)
    assert victim.center().x > max(flown) - 20.0
    assert run(world, 4.0, until=lambda: victim.animated)
    assert victim.contact().x > grabbed + 150.0


def test_it_never_swings_at_a_foe_out_of_reach():
    world = world_with()
    bull = world.add_minotaur(Vec2(400, FLOOR))
    bull.charge_wait = 1e9
    man = standing(world, 560)
    too_far: list[float] = []

    def watch():
        if bull.action in ("punch", "smash", "stomp", "hurl"):
            gap = abs(man.contact().x - bull.position.x)
            if gap > 70.0:
                too_far.append(gap)

    assert run(world, 8.0, until=lambda: not man.prey, each=watch)
    assert not too_far and man.damage > 0


def test_a_lone_foe_up_on_a_window_far_above_is_never_swung_at():
    world = world_with(Rect(200, 300, 400, 400))
    bull = world.add_minotaur(Vec2(700, FLOOR))
    bull.charge_wait = 1e9
    man = standing(world, 590, 300)
    seen = blows(world, bull, 1.5)
    assert not seen and man.damage == 0


# ----- rage ------------------------------------------------------------------------


def test_a_ranged_hit_enrages_it_and_a_blow_does_not():
    world = world_with()
    bull = world.add_minotaur(Vec2(400, FLOOR))
    world.hurt_monster(bull, 1, bull.center(), Vec2(0, 0))
    assert not bull.enraged and bull.pace == 1.0
    world.hurt_monster(bull, 1, bull.center(), Vec2(0, 0), ranged=True)
    assert bull.enraged and bull.rage_left == RAGE_TIME and bull.pace == RAGE_PACE > 1.0
    run(world, RAGE_TIME + 0.1)
    assert not bull.enraged


def time_to_walk(enraged: bool) -> float:
    world = world_with()
    bull = world.add_minotaur(Vec2(200, FLOOR))
    bull.facing = 1
    send(bull, Vec2(700, FLOOR))
    clock = [0.0]

    def tick():
        clock[0] += STEP
        if enraged:
            bull.rage_left = RAGE_TIME

    assert run(world, 40.0, until=arrived(bull, Vec2(700, FLOOR)), each=tick)
    return clock[0]


def test_enraged_it_moves_faster():
    assert time_to_walk(True) < 0.8 * time_to_walk(False)


def test_enraged_it_goes_for_whoever_shot_it():
    world = world_with()
    bull = world.add_minotaur(Vec2(400, FLOOR))
    near, archer = standing(world, 470), standing(world, 900, variant="ranger")
    run(world, 0.2)
    assert bull.foe is near
    world.hurt_monster(bull, 1, bull.center(), Vec2(0, 0), ranged=True, attacker=archer)
    run(world, 0.2)
    assert bull.provoker is archer and bull.foe is archer


# ----- climbing and falling --------------------------------------------------------


def test_it_climbs_a_wall_and_punches_the_archer_above_it():
    """An archer clinging to the wall above it used to pin it at the bottom."""
    world = world_with(Rect(500, 450, 300, 250))
    bull = world.add_minotaur(Vec2(200, FLOOR))
    man = world.add_stickman(Vec2(200, FLOOR), "ranger")
    man.wander = False
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 500)
    man.follower.reset(Anchor(wall, wall.closest_point(Vec2(500, 580))))
    man.paralyze(60.0)
    climbed, punched = [], []

    def watch():
        if bull.on_wall:
            climbed.append(bull.position.y)
        if bull.action in WALL_BLOWS and bull.on_wall:
            punched.append(bull.position.y)

    assert run(world, 20.0, until=lambda: man.damage > 0, each=watch)
    assert climbed and punched
    assert man.damage in (PUNCH_DAMAGE, SWIPE_DAMAGE)


def test_an_archer_on_the_ground_pulls_it_off_the_wall():
    world = world_with(Rect(500, 450, 300, 250))
    bull = world.add_minotaur(Vec2(200, FLOOR))
    climber = world.add_stickman(Vec2(200, FLOOR), "ranger")
    climber.wander = False
    climber.paralyze(60.0)
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 500)
    climber.follower.reset(Anchor(wall, wall.closest_point(Vec2(500, 580))))
    archer = standing(world, 1000, variant="ranger")
    fired = []

    def watch():
        if bull.on_wall and not fired:
            world.hurt_monster(bull, 1, bull.center(), Vec2(0, 0), ranged=True, attacker=archer)
            fired.append(bull.position.y)

    down = lambda: fired and bull.grounded and bull.surface is not None and not bull.on_wall  # noqa: E731
    assert run(world, 20.0, until=down, each=watch)
    assert bull.foe is archer
    run(world, 1.5)
    assert not bull.on_wall


def test_it_does_not_climb_to_a_wall_its_punch_cannot_reach():
    world = world_with(Rect(500, 400, 300, 80))
    bull = world.add_minotaur(Vec2(200, FLOOR))
    man = world.add_stickman(Vec2(200, FLOOR), "ranger")
    man.wander = False
    man.paralyze(30.0)
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 500)
    man.follower.reset(Anchor(wall, wall.point_at(wall.high - 8)))
    run(world, 0.5)
    spot = bull._wall_spot(man)
    assert spot is None or spot.point.y > wall.low + 40.0
    climbed = []
    run(world, 8.0, each=lambda: climbed.append(bull.position.y) if bull.on_wall else None)
    assert all(y > wall.low + 40.0 for y in climbed)
    assert bull.foe is man


def clinging(world: SimWorld, surface, y: float, variant: str = "ranger"):
    """An archer stuck to `surface` (a side, or a hang under a window) at height `y`."""
    man = world.add_stickman(Vec2(150, FLOOR), variant)
    man.wander = False
    man.follower.reset(Anchor(surface, surface.closest_point(Vec2(surface.start.x, y))))
    man.paralyze(60.0)
    return man


class Stillness:
    """The longest it has stood (or walked in place) within 8 px of one spot with a foe
    and nothing to do: never longer than 2 s, however it's being shot at."""

    def __init__(self, world: SimWorld, bull: Minotaur, shooter=None) -> None:
        self.world, self.bull, self.shooter = world, bull, shooter
        self.since, self.spot, self.longest, self.frames = 0.0, bull.position, 0.0, 0

    def __call__(self) -> None:
        bull, self.frames = self.bull, self.frames + 1
        now = self.frames * STEP
        shooter = self.shooter
        if shooter is not None and self.frames % 60 == 0 and shooter in self.world.stickmen:
            self.world.hurt_monster(
                bull, 0, bull.center(), Vec2(0, 0), ranged=True, attacker=shooter
            )
        idle = bull.foe is not None and bull.action is None
        if not idle or bull.position.distance_to(self.spot) > 8.0:
            self.since, self.spot = now, bull.position
        self.longest = max(self.longest, now - self.since)


def test_shot_from_a_window_side_it_climbs_up_and_punches_the_archer():
    world = world_with(Rect(500, 450, 300, 250))
    bull = world.add_minotaur(Vec2(200, FLOOR))
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 500)
    archer = clinging(world, wall, 590)
    still = Stillness(world, bull, archer)
    assert run(world, 15.0, until=lambda: archer.damage > 0, each=still)
    assert bull.on_wall and archer.damage in (PUNCH_DAMAGE, SWIPE_DAMAGE)
    assert still.longest < 2.0


def test_shot_from_the_screen_edge_it_climbs_up_and_punches_the_archer():
    world = world_with(Rect(700, 450, 300, 250))
    bull = world.add_minotaur(Vec2(400, FLOOR))
    edge = next(s for s in world.planner.surfaces if s.wall and s.box is None and s.start.x == 0)
    archer = clinging(world, edge, 560)
    still = Stillness(world, bull, archer)
    assert run(world, 20.0, until=lambda: archer.damage > 0, each=still)
    assert bull.on_wall and archer.damage in (PUNCH_DAMAGE, SWIPE_DAMAGE)
    assert still.longest < 2.0


def test_it_leaves_an_archer_out_of_reach_for_one_it_can_get_at():
    """One hanging under a window far above it can't be reached: it stood under him."""
    world = world_with(Rect(500, 250, 300, 120))
    bull = world.add_minotaur(Vec2(200, FLOOR))
    hang = next(s for s in world.planner.surfaces if s.kind.name == "CEILING" and s.box == 0)
    archer = clinging(world, hang, hang.start.y)
    man = standing(world, 1100)
    still = Stillness(world, bull, archer)
    assert run(world, 2.0, until=lambda: bull.foe is man, each=still)
    assert run(world, 15.0, until=lambda: man.damage > 0, each=still)
    assert archer.damage == 0 and still.longest < 2.0


@pytest.mark.parametrize("gap, bottom", [(6, 620), (6, 650), (14, 620), (14, 650)])
def test_it_climbs_a_narrow_slot_clipping_the_window_beside_and_punches_the_archer(gap, bottom):
    """A window beside the wall leaves a slot an archer fits up and it barely does: it
    used to stand at the bottom of the wall. Like at the screen's edges, it squeezes up
    anyway, its bulk clipping into the window beside."""
    beside = Rect(300, 300, 200 - gap, bottom - 300)
    world = world_with(Rect(500, 450, 300, 250), beside)
    bull = world.add_minotaur(Vec2(200, FLOOR))
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 500)
    archer = clinging(world, wall, 560)
    still = Stillness(world, bull, archer)
    assert run(world, 12.0, until=lambda: archer.damage > 0, each=still)
    assert bull.on_wall and archer.damage in (PUNCH_DAMAGE, SWIPE_DAMAGE)
    # Up either side of the slot, its bulk clipping the window across it.
    assert bull.surface.start.x in (500, beside.right)
    assert still.longest < 2.0


def facing_walls(gap: float) -> tuple[SimWorld, object, object]:
    """Two windows `gap` apart: the right side of the left one, the left side of the
    right one (its own walls, and the adventurers')."""
    world = world_with(Rect(300, 300, 200, 400), Rect(500 + gap, 300, 300, 400))
    mine = next(
        s for s in world.minotaur_planner.surfaces if s.wall and s.box == 0 and s.start.x == 500
    )
    theirs = next(
        s for s in world.planner.surfaces if s.wall and s.box == 1 and s.start.x == 500 + gap
    )
    return world, mine, theirs


def hanging_on(world: SimWorld, wall, y: float) -> Minotaur:
    bull = world.add_minotaur(Vec2(100, FLOOR))
    bull.route, bull.surface, bull.facing = [], wall, wall.facing
    bull.position = wall.point_at(y)
    return bull


class WallWatch:
    """Its lowest footing, whether it ever let go of the walls, and its blows."""

    def __init__(self, bull: Minotaur) -> None:
        self.bull, self.lowest, self.left_wall, self.blows = bull, bull.position.y, False, []

    def __call__(self) -> None:
        bull = self.bull
        self.lowest = max(self.lowest, bull.position.y)
        self.left_wall |= not bull.on_wall and bull.action is None
        if bull.action and (not self.blows or self.blows[-1] != bull.action):
            self.blows.append(bull.action)


def test_it_swipes_across_a_narrow_gap_at_a_foe_on_the_facing_wall():
    """A foe on the facing wall, level with it and in arm's reach: it used to slide all
    the way down, cross the floor and climb back up his wall to punch him."""
    world, mine, theirs = facing_walls(72)
    man = clinging(world, theirs, 470, "paladin")
    run(world, 0.3)
    bull = hanging_on(world, mine, 520)
    watch = WallWatch(bull)
    assert run(world, 2.0, until=lambda: man.damage > 0, each=watch)
    assert man.damage == SWIPE_DAMAGE and watch.blows[:1] == ["swipe"]
    assert not watch.left_wall and watch.lowest < 560
    assert bull.on_wall and bull.surface is mine


def test_it_swipes_up_at_a_foe_above_it_on_its_own_wall():
    world, mine, _ = facing_walls(200)
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 500)
    man = clinging(world, wall, 540, "paladin")
    run(world, 0.3)
    bull = hanging_on(world, mine, 640)
    watch = WallWatch(bull)
    assert run(world, 2.0, until=lambda: man.damage > 0, each=watch)
    assert watch.blows[:1] == ["swipe"] and man.damage == SWIPE_DAMAGE
    assert not watch.left_wall and watch.lowest <= 640.5


def test_it_climbs_its_own_wall_to_swipe_across_at_a_foe_high_on_the_facing_wall():
    """Out of reach for now, but a short climb up its own wall puts him in reach: no
    sliding down to cross the floor and climb his."""
    world, mine, theirs = facing_walls(72)
    man = clinging(world, theirs, 400, "paladin")
    run(world, 0.3)
    bull = hanging_on(world, mine, 660)
    assert bull._swipe_lands(man) is None
    watch = WallWatch(bull)
    assert run(world, 5.0, until=lambda: man.damage > 0, each=watch)
    assert man.damage == SWIPE_DAMAGE and bull.surface is mine
    assert not watch.left_wall and watch.lowest <= 660.5


def test_it_never_swipes_at_a_foe_across_a_wide_gap():
    world, mine, theirs = facing_walls(160)
    man = clinging(world, theirs, 470, "paladin")
    run(world, 0.3)
    bull = hanging_on(world, mine, 520)
    swung = []

    def watch():
        if bull.action == "swipe" and bull.surface is mine:
            swung.append(bull.position.y)

    run(world, 3.0, until=lambda: man.damage > 0, each=watch)
    assert not swung and man.damage == 0


def test_a_window_moving_elsewhere_leaves_it_in_its_narrow_slot():
    world = world_with(
        Rect(500, 450, 300, 250), Rect(300, 300, 194, 320), Rect(1000, 200, 200, 100)
    )
    bull = world.add_minotaur(Vec2(200, FLOOR))
    wall = next(
        s for s in world.minotaur_planner.surfaces if s.wall and s.box == 0 and s.start.x == 500
    )
    bull.route = []
    bull.surface, bull.position = wall, wall.point_at(600)
    moved = [world.boxes[0], world.boxes[1], Rect(1050, 220, 200, 100)]
    world.apply_terrain(TerrainChange(moves={2: Vec2(50, 20)}), moved)
    assert bull.on_wall and bull.surface.box == 0 and bull.position.y == 600


def test_it_climbs_up_a_window_side_to_an_adventurer_on_top():
    world = world_with(Rect(500, 450, 300, 250))
    bull = world.add_minotaur(Vec2(200, FLOOR))
    standing(world, 650, 450)
    climbing = []
    on_top = lambda: bull.grounded and bull.surface.box == 0 and bull.position.y == 450  # noqa: E731
    assert run(world, 20.0, until=on_top, each=lambda: climbing.append(bull.climb_speed > 0.0))
    assert any(climbing)


def test_a_fall_flattens_whoever_it_lands_on():
    world = world_with(Rect(300, 400, 400, 120))
    bull = world.add_minotaur(Vec2(500, 400))
    under = standing(world, 500)
    clear = standing(world, 620)
    bull._loose()
    # Drop him into the open air under the window, or the first step re-lands on it.
    bull.position = Vec2(500, 580)
    bull.velocity = Vec2(0, 0)
    assert bull.flight is not None
    bull.flight.start = bull.position
    bull.flight.launch = Vec2(0, 0)
    landed = lambda: bull.grounded and bull.position.y == FLOOR  # noqa: E731
    assert run(world, 5.0, until=landed)
    assert under.damage == CRUSH_DAMAGE and under.mode is StickMode.RAGDOLL
    assert bull.kills["crush"] == 0
    assert clear.damage == 0 and clear.animated


def test_a_window_closing_under_it_drops_it_to_the_floor():
    world = world_with(Rect(300, 450, 500, 250))
    bull = world.add_minotaur(Vec2(550, 450))
    run(world, 0.5)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    landed = lambda: bull.grounded and bull.land_left <= 0 and bull.position.y == FLOOR  # noqa: E731
    assert run(world, 5.0, until=landed)
    assert bull in world.minotaurs and not math.isnan(bull.position.x)
    run(world, 3.0)
    assert bull.position.y == FLOOR


# ----- whom it fights --------------------------------------------------------------


def test_it_never_targets_a_thrall():
    world = world_with()
    bull = world.add_minotaur(Vec2(400, FLOOR))
    bull.facing = 1
    thralls = [standing(world, x) for x in (446, 600)]
    for thrall in thralls:
        thrall.enthrall()
    actions = set()
    run(world, 4.0, each=lambda: actions.add(bull.action))
    melee = {"windup", "charge", "stomp", "punch", "smash", "hurl"}
    assert bull.foe is None and not actions & melee
    assert all(thrall.damage == 0 for thrall in thralls)


def test_it_follows_the_lich_in_the_desktop_rotation_and_fills_the_health_bar():
    assert DEFENDERS[5:7] == ("lich", "minotaur")
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(400, 400, 400, 200))])
    session = DesktopSession(screen, usable, source, seed=2, max_stickmen=0)
    session.rotate()  # past the chimera
    session.rotate()  # past the drow
    session.rotate()  # past the drake riders
    session.rotate()
    session.rotate()
    session.rotate()
    assert session.defender == "minotaur" and len(session.minotaurs) == 1
    bull = session.minotaurs[0]
    assert session.live_monsters == [bull] and session.defender_health == 1.0
    session.hurt_monster(bull, MINOTAUR_HP // 2, bull.center(), Vec2(0, 0))
    assert session.defender_health == 0.5
    session.hurt_monster(bull, MINOTAUR_HP, bull.center(), Vec2(0, -40))
    run(session, 0.1)
    assert session.defender == "displacer" and not session.minotaurs


def test_it_has_hit_points_and_dies_and_fades():
    world = world_with()
    bull = world.add_minotaur(Vec2(500, FLOOR))
    assert bull.max_hp == MINOTAUR_HP
    assert world.monster_at(bull.center()) is bull
    world.hurt_monster(bull, 10, bull.center(), Vec2(30, 0))
    assert not bull.dead and bull in world.minotaurs
    world.hurt_monster(bull, MINOTAUR_HP - 10, bull.center(), Vec2(30, 0))
    assert bull.dead and bull not in world.minotaurs and bull in world.fallen
    assert run(world, 15.0, until=lambda: bull not in world.fallen)
