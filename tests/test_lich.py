import math

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.systems.lich import (
    CAST_MAX,
    CAST_MIN,
    CAST_RANGE,
    CAST_TIME,
    CLUSTER_RADIUS,
    CROWD,
    DOOR_COOLDOWN,
    DOOR_EMERGE,
    DOOR_FADE,
    DOOR_STEP_OUT,
    DOOR_SWAP,
    DOOR_TIME,
    SPELL_DELAY,
    SPELLBOOK,
    Lich,
)
from dungeons_desktops.systems.mortal import LICH_HP
from dungeons_desktops.systems.world import SimWorld

STEP = 1 / 60
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


def standing(world: SimWorld, x: float, y: float = FLOOR, variant: str = "paladin"):
    """An adventurer who stays put and doesn't fight back."""
    man = world.add_stickman(Vec2(x, y), variant)
    man.wander = False
    man.paralyze(120.0)
    return man


def quiet(world: SimWorld) -> SimWorld:
    """His spells only a gesture, for watching how he moves."""
    world.necromancy.cast = lambda *args: None
    return world


def still(lich: Lich) -> Lich:
    lich._wander_wait = 1e9
    return lich


def top_of(world: SimWorld, box: int):
    return next(s for s in world.lich_terrain.surfaces if s.walkable and s.box == box)


# ----- getting about ---------------------------------------------------------------


def test_it_spawns_on_the_floor_and_walks_along_it():
    world = world_with()
    lich = still(world.add_lich(Vec2(200, FLOOR)))
    assert lich.grounded and lich.position.y == FLOOR and lich.hp == lich.max_hp
    lich.goal = (lich.surface, 500.0)
    track: list[Vec2] = []
    assert run(
        world, 30.0, until=lambda: lich.goal is None, each=lambda: track.append(lich.position)
    )
    assert abs(lich.position.x - 500.0) < 1.0
    assert all(p.y == FLOOR for p in track)
    steps = [b.x - a.x for a, b in zip(track, track[1:], strict=False)]
    assert max(steps) <= 0.6 and min(steps) >= -0.01


def test_it_walks_along_a_window_top():
    world = world_with(Rect(300, 450, 500, 250))
    lich = still(world.add_lich(Vec2(400, 450)))
    assert lich.surface.box == 0 and lich.position.y == 450
    lich.goal = (lich.surface, 700.0)
    assert run(world, 30.0, until=lambda: lich.goal is None)
    assert abs(lich.position.x - 700.0) < 1.0 and lich.position.y == 450


def test_it_never_walks_in_place():
    world = world_with()
    lich = still(world.add_lich(Vec2(200, FLOOR)))
    lich.goal = (lich.surface, 260.0)
    samples = []

    def sample():
        samples.append((lich.phase, lich.position.x))

    run(world, 6.0, each=sample)
    for (phase_a, x_a), (phase_b, x_b) in zip(samples, samples[1:], strict=False):
        if x_a == x_b:
            assert phase_a == phase_b


def test_it_turns_round_smoothly():
    world = world_with()
    lich = still(world.add_lich(Vec2(400, FLOOR)))
    lich.heading = 1
    lich.yaw.value = Lich._rest_yaw(1)
    yaws = [lich.yaw.value]
    lich.heading = -1
    run(world, 1.5, each=lambda: yaws.append(lich.yaw.value))
    assert lich.facing == -1 and abs(yaws[-1] - Lich._rest_yaw(-1)) < 0.02
    assert max(abs(b - a) for a, b in zip(yaws, yaws[1:], strict=False)) < 0.12


def test_it_levitates_up_to_reach_a_foe_on_a_window_top():
    world = quiet(world_with(Rect(300, 400, 400, 300)))
    lich = world.add_lich(Vec2(1000, FLOOR))
    lich.door_wait = 1e9
    foe = standing(world, 450, 400)
    flew = []
    aloft = []

    def check():
        flew.append(lich.levitating)
        aloft.append(lich.levitating and lich.casting)
        if lich.levitating:
            assert not lich._inside(lich.position) or lich.position.y > FLOOR - 1

    settled = lambda: lich.grounded and lich.surface.box == 0  # noqa: E731
    assert run(world, 40.0, until=settled, each=check)
    assert any(flew) and any(aloft)
    run(world, 4.0)
    assert lich.grounded and CAST_MIN - 1 <= lich.range_to(foe) <= CAST_MAX + 1


def test_a_window_closing_under_it_floats_it_down_safely():
    world = world_with(Rect(300, 450, 500, 250))
    lich = still(world.add_lich(Vec2(550, 450)))
    run(world, 0.5)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert lich.levitating
    ys = [lich.position.y]
    landed = lambda: lich.grounded and lich.position.y == FLOOR  # noqa: E731
    assert run(world, 10.0, until=landed, each=lambda: ys.append(lich.position.y))
    assert max(b - a for a, b in zip(ys, ys[1:], strict=False)) < 1.0
    assert lich in world.liches and not math.isnan(lich.position.x)


def test_a_window_moving_carries_it():
    world = world_with(Rect(300, 450, 500, 250))
    lich = still(world.add_lich(Vec2(550, 450)))
    run(world, 0.5)
    world.apply_terrain(TerrainChange(moves={0: Vec2(40, -30)}), [Rect(340, 420, 500, 250)])
    assert lich.grounded and lich.position == Vec2(590, 420)


# ----- keeping its distance ------------------------------------------------------------


def test_it_keeps_a_stand_off_distance():
    world = world_with()
    quiet(world)
    lich = world.add_lich(Vec2(200, FLOOR))
    foe = standing(world, 800)
    run(world, 30.0)
    assert lich.foe is foe and lich.grounded
    assert CAST_MIN <= lich.range_to(foe) <= CAST_MAX
    assert lich.facing == 1


def test_it_backs_off_from_an_adventurer_who_comes_close_still_facing_him():
    world = world_with()
    quiet(world)
    lich = world.add_lich(Vec2(700, FLOOR))
    foe = standing(world, 780)
    run(world, 1.0)
    assert lich.foe is foe
    xs = []
    run(world, 2.0, each=lambda: xs.append((lich.position.x, lich.facing)))
    assert xs[-1][0] < 700 - 10
    assert all(facing == 1 for _, facing in xs[30:])
    run(world, 20.0)
    assert lich.position.x < 780 - CROWD


def test_it_floats_over_an_adventurer_rather_than_walk_through_him():
    world = world_with()
    quiet(world)
    lich = world.add_lich(Vec2(30, FLOOR))
    foe = standing(world, 110)
    flew = []
    run(world, 25.0, each=lambda: flew.append(lich.levitating))
    assert any(flew)
    assert lich.position.x > foe.center().x and lich.range_to(foe) >= CAST_MIN - 1


# ----- spells -------------------------------------------------------------------


def casts_of(world: SimWorld) -> list[tuple[float, str]]:
    """Record (time, spell) of each spell he lets fly, without it doing anything."""
    log: list[tuple[float, str]] = []
    world.necromancy.cast = lambda spell, *args: log.append((world.liches[0].time, spell))
    return log


def test_every_cast_is_the_next_spell_in_the_queue_whoever_the_foe():
    world = world_with()
    log = casts_of(world)
    lich = world.add_lich(Vec2(200, FLOOR))
    assert lich.spells == list(SPELLBOOK) and lich.spell == SPELLBOOK[0]
    foe = standing(world, 450)
    for _ in range(6):
        run(world, 3.0)
        world.stickmen.remove(foe)
        foe = standing(world, 440 + 20 * len(log) % 60)
    spells = [spell for _, spell in log]
    assert len(spells) >= 7
    assert spells == [SPELLBOOK[i % len(SPELLBOOK)] for i in range(len(spells))]


def test_no_spell_has_its_own_cooldown_only_the_delay_after_it():
    world = world_with()
    log = casts_of(world)
    lich = world.add_lich(Vec2(200, FLOOR))
    standing(world, 450)
    run(world, 14.0)
    assert len(log) >= 6
    for (a, spell), (b, _) in zip(log, log[1:], strict=False):
        assert abs(b - a - (CAST_TIME + SPELL_DELAY[spell])) < 3 * STEP, spell
    assert lich.spell_index == len(log) % len(SPELLBOOK)


def test_he_casts_on_the_move_as_soon_as_a_foe_is_in_range():
    world = world_with()
    casts_of(world)
    lich = world.add_lich(Vec2(150, FLOOR))
    lich.door_wait = 1e9
    foe = standing(world, 150 + CAST_RANGE - 20)
    started = []
    moving = []

    def watch():
        if lich.casting and lich.cast_left > CAST_TIME - 1.5 * STEP:
            started.append(lich.range_to(foe))
        if lich.casting:
            moving.append(abs(lich.speed))

    run(world, 4.0, each=watch)
    assert started and started[0] > CAST_MAX + 40
    assert max(moving) > 10.0


def test_each_cast_is_his_current_spell_at_the_foe():
    world = world_with()
    lich = world.add_lich(Vec2(200, FLOOR))
    foe = standing(world, 420, variant="barbarian")
    raised = []
    assert run(
        world, 6.0, until=lambda: lich.casts >= 1, each=lambda: raised.append(lich.gesture.value)
    )
    assert lich.last_cast == (SPELLBOOK[0], foe)
    run(world, 1.0, each=lambda: raised.append(lich.gesture.value))
    assert max(raised) > 0.8 and (foe.damage > 0 or not foe.animated)


def test_each_spell_has_its_own_gesture():
    poses = {}
    for spell in SPELLBOOK:
        world = world_with()
        lich = world.add_lich(Vec2(200, FLOOR))
        lich.spells = [spell]
        lich.door_wait = 1e9
        foe = standing(world, 420, variant="barbarian")
        foe.paralyze(30.0)
        frames = []
        run(world, 4.0, each=lambda lich=lich, frames=frames: frames.append(lich.joints()))
        assert lich.casts >= 1, spell
        root = [j.root for j in frames]
        hands = [(j.hands[0] - r, j.hands[1] - r) for j, r in zip(frames, root, strict=True)]
        poses[spell] = (
            min(h[0].y for h in hands),
            max(h[0].y for h in hands),
            max(j.finger for j in frames),
            max(j.jaw for j in frames),
            max(j.crackle for j in frames),
            max(h[1].x * lich.facing for h in hands),
        )
    assert poses["black_tentacles"][0] < -40 and poses["black_tentacles"][1] > -20
    assert poses["power_word_kill"][2] > 0.9 and poses["power_word_kill"][3] > 0.5
    assert poses["chain_lightning"][4] > 0.9 and poses["chain_lightning"][5] > 10
    assert all(poses[s][2] == 0 for s in SPELLBOOK if s != "power_word_kill")
    assert all(poses[s][4] == 0 for s in SPELLBOOK if s != "chain_lightning")


def test_his_door_takes_him_to_the_middle_of_a_big_group_over_a_nearer_loner():
    world = quiet(world_with())
    lich = world.add_lich(Vec2(200, FLOOR))
    loner = standing(world, 420)
    group = [standing(world, x) for x in (1000, 1040, 1080)]
    run(world, 0.1)
    assert lich.foe is loner
    lich.door_wait = 0.0
    assert door_open(world, lich, 1.0)
    assert lich.foe is group[1] and lich.door_groups == [3]
    run(world, DOOR_TIME + 0.1)
    assert lich.door is None and CAST_MIN - 1 <= lich.range_to(group[1]) <= CAST_MAX + 1
    assert all(lich.center().distance_to(m.center()) >= 99 for m in group)


def test_a_spread_out_group_counts_and_he_aims_at_its_middle():
    world = quiet(world_with())
    lich = world.add_lich(Vec2(200, FLOOR))
    standing(world, 420)
    group = [standing(world, x) for x in (900, 1100, 1180)]
    assert CLUSTER_RADIUS == 300
    lich.door_wait = 0.0
    assert door_open(world, lich, 1.0)
    assert lich.foe is group[1] and lich.door_groups == [3]
    run(world, DOOR_TIME + 0.1)
    assert CAST_MIN - 1 <= lich.range_to(group[1]) <= CAST_MAX + 1
    assert all(lich.center().distance_to(m.center()) >= 99 for m in group)
    assert not lich._inside(lich.position) and lich.grounded


def test_a_small_group_is_not_worth_a_door_while_his_foe_is_close():
    world = quiet(world_with())
    lich = world.add_lich(Vec2(200, FLOOR))
    standing(world, 420)
    for x in (1000, 1040):
        standing(world, x)
    lich.door_wait = 0.0
    assert not door_open(world, lich, 2.0)


def test_it_never_targets_a_thrall():
    world = world_with()
    lich = world.add_lich(Vec2(300, FLOOR))
    thralls = [standing(world, x) for x in (450, 600)]
    for thrall in thralls:
        thrall.enthrall()
    run(world, 5.0)
    assert lich.foe is None and lich.casts == 0 and lich.spell == SPELLBOOK[0]
    assert all(thrall.damage == 0 for thrall in thralls)


# ----- the desktop, HP and death -------------------------------------------------------


def test_it_follows_the_mimic_in_the_desktop_rotation_and_fills_the_health_bar():
    assert DEFENDERS[4:6] == ("mimic", "lich")
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(400, 400, 400, 200))])
    session = DesktopSession(screen, usable, source, seed=2, max_stickmen=0)
    session.rotate()  # past the chimera
    session.rotate()  # past the drow
    session.rotate()  # past the drake riders
    session.rotate()
    session.rotate()
    assert session.defender == "lich" and len(session.liches) == 1
    lich = session.liches[0]
    assert lich.position.y == 400
    assert session.live_monsters == [lich] and session.defender_health == 1.0
    session.hurt_monster(lich, 1, lich.center(), Vec2(0, 0))
    assert abs(session.defender_health - (LICH_HP - 1) / LICH_HP) < 1e-9
    session.hurt_monster(lich, LICH_HP, lich.center(), Vec2(0, -40))
    run(session, 0.1)
    assert session.defender == "minotaur" and not session.liches


def test_adventurers_can_find_and_hit_it():
    world = world_with()
    lich = world.add_lich(Vec2(500, FLOOR))
    assert lich in world.monsters() and world.locate(lich) == lich.center()
    assert world.monster_at(lich.center()) is lich
    assert world.closest_part(lich, Vec2(500, 600)) in lich.parts()


def test_it_has_hit_points_and_crumbles_and_fades():
    world = world_with(Rect(300, 450, 500, 250))
    lich = world.add_lich(Vec2(550, 450))
    assert lich.max_hp == LICH_HP
    world.hurt_monster(lich, LICH_HP - 1, lich.center(), Vec2(30, 0))
    assert not lich.dead and lich in world.liches
    world.hurt_monster(lich, 1, lich.center(), Vec2(30, 0))
    assert lich.dead and lich not in world.liches and lich in world.fallen
    assert {b.kind for b in lich.bits} >= {"skull", "crown"}
    run(world, 2.0)
    assert lich.flame == 0.0 and lich.slump == 1.0
    assert all(b.resting for b in lich.bits)
    assert all(b.position.y <= FLOOR for b in lich.bits)
    assert run(world, 15.0, until=lambda: lich not in world.fallen)


def test_killed_in_the_air_it_drops_to_the_ground():
    world = world_with(Rect(300, 450, 500, 250))
    lich = still(world.add_lich(Vec2(550, 450)))
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    run(world, 1.0)
    assert lich.levitating
    world.hurt_monster(lich, LICH_HP, lich.center(), Vec2(0, 0))
    run(world, 3.0)
    assert lich.position.y == FLOOR


# ----- dimension door ------------------------------------------------------------------


def door_open(world: SimWorld, lich: Lich, seconds: float = 3.0) -> bool:
    return run(world, seconds, until=lambda: lich.door is not None)


def test_it_dimension_doors_to_a_far_foe_and_lands_at_casting_range():
    world = world_with()
    lich = world.add_lich(Vec2(150, FLOOR))
    foe = standing(world, 1100)
    lich.door_wait = 0.5
    assert door_open(world, lich)
    assert lich.doors == 1 and abs(lich.door_wait - DOOR_COOLDOWN) < 0.1
    run(world, DOOR_TIME + 0.1)
    assert lich.door is None and lich.grounded and lich.position.y == FLOOR
    assert CAST_MIN <= lich.range_to(foe) <= CAST_MAX
    assert lich.facing == 1 if foe.center().x > lich.position.x else lich.facing == -1


def test_no_door_when_the_foe_is_close():
    world = world_with()
    lich = world.add_lich(Vec2(400, FLOOR))
    standing(world, 700)
    lich.door_wait = 0.0
    assert not door_open(world, lich, 8.0)
    assert lich.doors == 0


def test_the_door_has_a_twenty_second_cooldown():
    assert DOOR_COOLDOWN == 20.0
    world = quiet(world_with())
    lich = world.add_lich(Vec2(150, FLOOR))
    foes = [standing(world, 1350)]
    lich.door_wait = 0.0
    opened: list[float] = []
    clock = [0.0]

    def tick():
        clock[0] += STEP
        if lich.doors > len(opened):
            opened.append(clock[0])
        if lich.door is None and lich.range_to(foes[-1]) < 500:
            world.stickmen.remove(foes[-1])
            foes.append(standing(world, 1350 if lich.position.x < WIDTH / 2 else 50))

    run(world, 50.0, each=tick)
    assert len(opened) >= 2
    assert all(b - a >= DOOR_COOLDOWN - 0.05 for a, b in zip(opened, opened[1:], strict=False))
    assert opened[1] - opened[0] < DOOR_COOLDOWN + 2.0


def test_it_lands_on_a_window_top_but_never_inside_a_window():
    world = world_with(Rect(700, 450, 500, 250))
    lich = world.add_lich(Vec2(100, FLOOR))
    foe = standing(world, 1100, 450)
    lich.door_wait = 0.0
    assert door_open(world, lich)
    door = lich.door
    assert door is not None and door.surface is not None
    run(world, DOOR_TIME + 0.1)
    assert lich.grounded and not lich._inside(lich.position)
    assert CAST_MIN <= lich.range_to(foe) <= CAST_MAX
    assert lich.surface.box == 0 and lich.position.y == 450


def test_it_cannot_be_found_or_hurt_while_in_transit():
    world = world_with()
    lich = world.add_lich(Vec2(150, FLOOR))
    standing(world, 1100)
    lich.door_wait = 0.0
    assert door_open(world, lich)
    assert run(world, 1.0, until=lambda: lich.phased)
    assert lich not in world.monsters() and world.locate(lich) is None
    assert world.monster_at(lich.center()) is None
    assert not world.hurt_monster(lich, LICH_HP, lich.center(), Vec2(0, 0))
    assert lich.hp == LICH_HP and lich in world.liches
    run(world, DOOR_TIME)
    assert lich in world.monsters() and world.monster_at(lich.center()) is lich


def test_the_door_still_takes_its_time_and_he_is_only_untouchable_mid_transit():
    world = quiet(world_with())
    lich = world.add_lich(Vec2(150, FLOOR))
    standing(world, 1100)
    lich.door_wait = 0.0
    assert door_open(world, lich)
    frames = []
    run(
        world,
        3.0,
        until=lambda: lich.door is None,
        each=lambda: frames.append(
            (lich.door.time, lich.phased) if lich.door is not None else (None, False)
        ),
    )
    times = [t for t, _ in frames if t is not None]
    assert DOOR_TIME == 1.35 and DOOR_TIME - 2 * STEP <= max(times) <= DOOR_TIME + STEP
    phased = [t for t, gone in frames if gone]
    assert phased and min(phased) > DOOR_FADE and max(phased) < DOOR_EMERGE + DOOR_STEP_OUT
    assert lich.door is None and lich.hp == LICH_HP


def test_the_door_does_not_use_up_a_spell():
    world = world_with()
    lich = world.add_lich(Vec2(150, FLOOR))
    standing(world, 1100)
    lich.door_wait = 0.0
    run(world, 0.2)
    assert lich.spell_index == 0 and lich.casts == 0
    assert door_open(world, lich)
    assert lich.spell_index == 0
    run(world, DOOR_TIME + 3.0)
    assert lich.doors == 1 and lich.casts >= 1
    assert lich.spell_index == lich.casts % len(SPELLBOOK)


def test_the_destination_window_closing_mid_door_is_handled():
    world = world_with(Rect(700, 450, 500, 250))
    lich = world.add_lich(Vec2(100, FLOOR))
    standing(world, 1100, 450)
    lich.door_wait = 0.0
    assert door_open(world, lich)
    assert lich.door is not None and lich.door.surface.box == 0
    run(world, DOOR_SWAP * 0.5)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    run(world, DOOR_TIME)
    assert lich.door is None and not math.isnan(lich.position.x)
    assert not lich._inside(lich.position)
    assert run(world, 10.0, until=lambda: lich.grounded)
    assert lich.position.y == FLOOR


# ----- foes he can't reach ----------------------------------------------------------------


def perched(world: SimWorld) -> object:
    """An adventurer on a window top too narrow and too high for the lich to reach."""
    return standing(world, 700, 45)


def test_it_switches_from_an_unreachable_foe_to_one_it_can_reach():
    world = world_with(Rect(690, 45, 20, 300))
    quiet(world)
    lich = world.add_lich(Vec2(1100, FLOOR))
    high = perched(world)
    low = standing(world, 300)
    run(world, 0.1)
    assert lich.foe is high
    assert run(world, 2.0, until=lambda: lich.foe is low)
    run(world, 10.0)
    assert lich.foe is low and CAST_MIN <= lich.range_to(low) <= CAST_MAX


def test_with_only_an_unreachable_foe_it_waits_on_the_nearest_spot_below_him():
    world = world_with(Rect(690, 45, 20, 300))
    lich = world.add_lich(Vec2(1100, FLOOR))
    high = perched(world)
    start = lich.range_to(high)
    run(world, 20.0)
    assert lich.foe is high and lich.stranded
    assert lich.grounded and lich.position.y == FLOOR and not lich._inside(lich.position)
    assert abs(lich.position.x - 700) < 100 and lich.range_to(high) < start - 80
    assert lich.facing == -1
