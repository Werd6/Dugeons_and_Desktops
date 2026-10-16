from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.overlay import DEFENDER_BARS
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.defenders.elementals.actor import (
    ELEMENTAL_HP,
    FORM_HP,
    HEIGHT,
    KINDS,
    MELEE_COOLDOWN,
    MELEE_DAMAGE,
    PACE,
    SHIFT_TIME,
    WALK,
    Action,
    Elemental,
    FlyMover,
)
from dungeons_desktops.game.defenders.elementals.powers import (
    PATCH_DAMAGE,
    BurningPatch,
    Caught,
    FireballShot,
    Shockwave,
    Wave,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange

STEP = 1 / 60
FLOOR = 800.0
WINDOW = Rect(300, 400, 400, 200)
HIGH = Rect(750, 250, 200, 300)
TALL = Rect(760, 350, 180, 470)
"""Its sides reach the floor."""


def world_with(*boxes: Rect, seed: int = 2) -> SimWorld:
    return SimWorld(list(boxes or (WINDOW,)), FLOOR, 1000.0, ceiling=0.0, seed=seed)


def run(world, seconds: float, until=None, each=None) -> bool:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()
        if until is not None and until():
            return True
    return until is None


def unkillable(*stickmen):
    """Record what hurts them instead of hurting them, so a test can watch a fight."""
    hits = []
    for stickman in stickmen:

        def hurt(amount, point, push, source, death, bleed=True, who=stickman):
            hits.append((who, source, amount))
            return False

        stickman.hurt = hurt
    return hits


def standing(world, point, variant="barbarian"):
    stickman = world.add_stickman(point, variant)
    stickman.stop()
    return stickman


def calm(elemental: Elemental, melee: bool = True, special: bool = True) -> None:
    if melee:
        elemental.melee_wait = 999.0
    if special:
        elemental.special_wait = 999.0
    elemental.burrow_wait = 999.0


def all_effects(world, kind):
    return [
        fx
        for e in world.elementals + world.fallen
        for fx in getattr(e, "effects", ())
        if isinstance(fx, kind)
    ]


# ----- one elemental, four forms -----------------------------------------------


def test_elementals_are_opt_in_and_spawn_as_a_single_water_form():
    world = DesktopSession(
        Rect(0, 0, 1400, 900),
        Rect(0, 30, 1400, 800),
        FakeWindowSource([WindowRecord(1, WINDOW)]),
        seed=3,
        max_stickmen=0,
        defenders=("elementals",),
    )
    assert "elementals" not in DEFENDERS
    assert world.defender == "elementals"
    assert DEFENDER_BARS["elementals"][0] == "Elemental"
    assert [e.kind for e in world.elementals] == ["water"]
    assert world.defender_max_hp == ELEMENTAL_HP == 4 * FORM_HP == 20


def test_it_is_a_little_smaller_than_the_minotaur():
    assert 50.0 < HEIGHT < 64.0


def test_every_five_damage_it_turns_to_the_next_form_and_twenty_kills_it():
    world = world_with()
    elemental = world.add_elemental(Vec2(500, WINDOW.top))
    calm(elemental)
    seen = [elemental.kind]
    for _ in range(3):
        assert not world.hurt_monster(elemental, FORM_HP, elemental.center(), Vec2(30, 0))
        assert elemental.action is Action.SHIFT and not elemental.vulnerable
        assert run(world, SHIFT_TIME + 0.2, until=lambda: elemental.action is not Action.SHIFT)
        seen.append(elemental.kind)
    assert seen == list(KINDS)
    assert world.hurt_monster(elemental, FORM_HP, elemental.center(), Vec2(30, 0))
    assert elemental.dead and elemental in world.fallen and not world.elementals


def test_a_big_hit_cannot_skip_a_form_and_hits_while_it_shifts_are_ignored():
    world = world_with()
    elemental = world.add_elemental(Vec2(500, WINDOW.top))
    calm(elemental)
    world.hurt_monster(elemental, 12, elemental.center(), Vec2(30, 0))
    assert elemental.damage == FORM_HP and elemental.action is Action.SHIFT
    world.hurt_monster(elemental, 3, elemental.center(), Vec2(30, 0))
    assert world.monster_at(elemental.center()) is None
    assert elemental.damage == FORM_HP
    run(world, SHIFT_TIME + 0.1)
    assert elemental.kind == "earth" and elemental.vulnerable


# ----- movement ------------------------------------------------------------------


def test_water_races_an_adventurer_on_another_window_floating_up_its_side():
    world = world_with(WINDOW, TALL)
    elemental = world.add_elemental(Vec2(400, WINDOW.top))
    calm(elemental)
    man = standing(world, Vec2(850, TALL.top))
    unkillable(man)
    speeds, walls = [], []

    def watch():
        speeds.append(abs(elemental.mover.drift.x) + abs(elemental.mover.drift.y))
        anchor = elemental.mover.follower.current_anchor()
        walls.append(anchor is not None and anchor.surface.wall)

    assert run(world, 15.0, until=lambda: elemental.in_reach(man, slack=2.0), each=watch)
    assert max(speeds) > 1.5 * WALK
    assert any(walls)


def test_fire_is_faster_still_relentless_and_never_wanders():
    assert PACE["fire"] > PACE["water"] > PACE["air"] > PACE["earth"]
    world = world_with()
    fire = world.add_elemental(Vec2(500, WINDOW.top), kind="fire")
    mover = fire.mover
    assert mover.patience == 0.0 and mover.replan_every <= 0.2 and not mover.wanders
    start = fire.feet
    run(world, 4.0)
    assert (fire.feet - start).length() < 4.0


def test_fire_switches_to_a_reachable_adventurer_when_its_quarry_cannot_be_reached():
    world = world_with()
    fire = world.add_elemental(Vec2(350, WINDOW.top), kind="fire")
    calm(fire)
    near = standing(world, Vec2(480, WINDOW.top))
    far = standing(world, Vec2(900, FLOOR))
    unkillable(near, far)
    mover = fire.mover
    reachable = mover._go

    def go(point):
        return point.x < 700 and reachable(point)

    mover._go = go
    run(world, 0.2)
    assert run(world, 3.0, until=lambda: fire.target is near and fire.in_reach(near, slack=2.0))


def test_earth_burrows_to_an_adventurer_on_another_window_and_emerges_beside_him():
    world = world_with(WINDOW, HIGH)
    earth = world.add_elemental(Vec2(350, WINDOW.top), kind="earth")
    calm(earth)
    earth.burrow_wait = 0.0
    earth.surfaced = 99.0
    man = standing(world, Vec2(850, HIGH.top))
    unkillable(man)
    assert run(world, 3.0, until=lambda: earth.sunk >= 1.0)
    assert earth.action is Action.BURROW
    assert not world.hurt_monster(earth, 1, earth.center(), Vec2(0, 0)) and earth.damage == FORM_HP
    assert world.monster_at(earth.center()) is None
    assert run(world, 4.0, until=lambda: earth.action is not Action.BURROW)
    assert abs(earth.feet.y - HIGH.top) < 4.0
    assert abs(earth.feet.x - man.contact().x) < 60.0


def test_air_flies_straight_up_to_an_adventurer_without_a_route():
    world = world_with(WINDOW, HIGH)
    air = world.add_elemental(Vec2(900, FLOOR), kind="air")
    calm(air)
    assert isinstance(air.mover, FlyMover) and air.surface() is None
    man = standing(world, Vec2(850, HIGH.top))
    unkillable(man)
    heights = []
    assert run(
        world,
        12.0,
        until=lambda: air.in_reach(man, slack=2.0),
        each=lambda: heights.append(air.feet.y),
    )
    assert all(b <= a + 0.5 for a, b in zip(heights, heights[1:], strict=False))
    assert air.feet.y < HIGH.bottom


def test_it_rides_a_moving_window_and_drops_when_it_closes():
    world = world_with()
    elemental = world.add_elemental(Vec2(500, WINDOW.top))
    calm(elemental)
    run(world, 0.5)
    x = elemental.feet.x
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(330, 380, 400, 200)])
    assert abs(elemental.feet.y - 379) < 1.0 and abs(elemental.feet.x - (x + 30)) < 1.0
    run(world, 0.5)
    assert abs(elemental.feet.y - 379) < 1.0
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    run(world, 3.0)
    assert abs(elemental.feet.y - FLOOR) < 4.0


# ----- fighting ------------------------------------------------------------------


def test_its_punch_hits_for_one_and_respects_its_cooldown():
    world = world_with()
    elemental = world.add_elemental(Vec2(450, WINDOW.top))
    calm(elemental, melee=False)
    man = standing(world, Vec2(475, WINDOW.top))
    hits = unkillable(man)
    times, clock = [], [0.0]

    def watch():
        clock[0] += STEP
        if len(hits) > len(times):
            times.append(clock[0])

    run(world, 5.0, each=watch)
    assert len(hits) >= 2
    assert all(amount == MELEE_DAMAGE == 1 for _, _, amount in hits)
    assert all(b - a >= MELEE_COOLDOWN - 0.05 for a, b in zip(times, times[1:], strict=False))


def test_the_tidal_surge_sweeps_people_along_and_off_the_window_edge():
    world = world_with()
    water = world.add_elemental(Vec2(560, WINDOW.top), facing=1)
    calm(water, special=False)
    water.special_wait = 0.0
    men = [standing(world, Vec2(x, WINDOW.top)) for x in (650, 690)]
    run(world, 0.1)
    assert run(world, 2.0, until=lambda: all_effects(world, Wave))
    run(world, 3.0)
    assert all(man.damage >= 1 for man in men)
    assert any(man.contact().x > WINDOW.right or man.contact().y > WINDOW.top + 20 for man in men)


def test_the_seismic_slam_only_knocks_down_people_on_its_own_surface():
    world = world_with()
    earth = world.add_elemental(Vec2(450, WINDOW.top), kind="earth", facing=1)
    calm(earth, special=False)
    earth.special_wait = 0.0
    above = standing(world, Vec2(540, WINDOW.top))
    below = standing(world, Vec2(470, FLOOR))
    hits = unkillable(above, below)
    assert run(world, 2.0, until=lambda: all_effects(world, Shockwave))
    run(world, 1.0)
    assert (above, "earth elemental", 2) in hits
    assert not any(who is below for who, _, _ in hits)
    assert not above.animated


def test_the_whirlwind_dashes_diagonally_up_then_carries_and_flings_him():
    world = world_with(WINDOW)
    air = world.add_elemental(Vec2(250, 480), kind="air", facing=1)
    calm(air, special=False)
    air.special_wait = 0.0
    man = standing(world, Vec2(330, WINDOW.top))
    run(world, 0.1)
    assert run(
        world, 3.0, until=lambda: air.action is Action.SPECIAL and air.special.direction is not None
    )
    way = air.special.direction
    assert way.x > 0.2 and way.y < -0.2
    assert run(world, 2.0, until=lambda: all_effects(world, Caught))
    assert man.damage >= 1
    run(world, 1.0)
    assert not all_effects(world, Caught) and not man.animated


def test_the_fireball_bursts_and_leaves_burning_ground_that_hurts():
    world = world_with()
    fire = world.add_elemental(Vec2(250, FLOOR), kind="fire", facing=1)
    calm(fire, special=False)
    fire.special_wait = 0.0
    fire.mover.update = lambda dt, target, hunt, rooted: None
    man = standing(world, Vec2(480, FLOOR))
    hits = unkillable(man)
    assert run(world, 2.0, until=lambda: all_effects(world, FireballShot))
    assert run(world, 3.0, until=lambda: all_effects(world, BurningPatch))
    assert any(who is man and amount == 2 for who, _, amount in hits)
    patch = all_effects(world, BurningPatch)[0]
    victim = standing(world, Vec2(patch.x, patch.y))
    burns = unkillable(victim)
    assert run(world, 1.5, until=lambda: burns)
    assert burns[0][1:] == ("fire elemental", PATCH_DAMAGE)


def test_it_collapses_and_fades_when_killed():
    world = world_with()
    elemental = world.add_elemental(Vec2(500, WINDOW.top), kind="fire")
    calm(elemental)
    run(world, 0.5)
    for part in elemental.parts():
        assert world.monster_at(part) is elemental
    assert world.hurt_monster(elemental, FORM_HP, elemental.center(), Vec2(40, -40))
    assert elemental in world.fallen and not world.elementals
    run(world, 1.5)
    assert elemental.collapse == 1.0
    run(world, 10.0)
    assert elemental not in world.fallen


def test_whirlwind_carries_a_victim_along_its_direction_before_release():
    world = world_with()
    man = standing(world, Vec2(500, WINDOW.top))
    run(world, 0.1)
    man.knock_down(man.center() + Vec2(0, 10), 10, 1.5, 1)
    start = man.center()
    way = Vec2(0.6, -0.8)
    effect = Caught(man, way)
    for _ in range(10):
        assert effect.update(world, STEP)
    displacement = man.center() - start
    assert displacement.distance_to(way * 50.0) < 0.01


def test_wave_keeps_its_victim_with_the_front_until_the_edge():
    world = world_with()
    man = standing(world, Vec2(600, WINDOW.top))
    run(world, 0.1)
    wave = Wave(595, WINDOW.top, WINDOW.left, WINDOW.right, 0, 1)
    for _ in range(10):
        assert wave.update(world, STEP)
    assert man in wave.swept and not man.animated
    assert abs(man.center().x - (wave.x - 5)) < 0.01
    assert man.damage == 1
