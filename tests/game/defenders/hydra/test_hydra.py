import math

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.defenders.dragon.actor import climbing_wall
from dungeons_desktops.game.defenders.hydra.actor import (
    ACID_DAMAGE,
    ATTACK_COOLDOWN,
    ATTACK_GAP,
    BODY_LENGTH,
    CHASE_SPEED,
    CHOMP_DAMAGE,
    CHOMP_DEATH,
    DEATH,
    DIVE_COOLDOWN,
    GLOB_COOLDOWN,
    HEAD_REACH,
    HEADROOM,
    HIP,
    HYDRA_HP,
    LANDING,
    MIN_SURFACED,
    SEGMENTS,
    SHOULDER,
    SPACING,
    STRIDE,
    THIGH,
    TORSO,
    TURRET_OUT,
    UP,
    Exit,
    Hydra,
    Mode,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange

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
    man.paralyze(60.0)
    return man


def lying(world: SimWorld, x: float, y: float = FLOOR, facing: int = 1) -> Hydra:
    """A hydra already out of the ground, lying along the surface at (x, y)."""
    return world.add_hydra(Vec2(x, y), facing=facing, emerge=False)


def calm(hydra: Hydra) -> None:
    """No diving for a good while."""
    hydra.dive_cooldown = 1e9
    hydra._roam_after = 1e9


def shown(hydra: Hydra) -> list:
    return [s for s in hydra.segments if not s.hidden]


def finite(point: Vec2) -> bool:
    return math.isfinite(point.x) and math.isfinite(point.y)


# ----- the body --------------------------------------------------------------------------


def test_it_stands_on_four_legs_with_a_short_bulky_body_and_a_dragging_tail():
    world = world_with()
    hydra = lying(world, 400)
    calm(hydra)
    standing(world, 1200)
    run(world, 1.0)
    segments = hydra.segments
    assert len(segments) == SEGMENTS and all(s.grounded for s in segments)
    assert all(abs(s.contact.y - FLOOR) < 0.01 for s in segments)
    gaps = [a.contact.distance_to(b.contact) for a, b in zip(segments, segments[1:], strict=False)]
    assert all(abs(gap - SPACING) < 0.05 for gap in gaps)
    assert BODY_LENGTH <= 110.0
    torso, tail = segments[:TORSO], segments[TORSO:]
    assert all(FLOOR - s.center.y > s.radius + 5.0 for s in torso)
    assert min(s.radius for s in torso) > max(s.radius for s in tail[1:])
    assert FLOOR - tail[-1].center.y < tail[-1].radius + 2.0
    assert sorted((leg.segment, leg.near) for leg in hydra.legs) == [
        (SHOULDER, False),
        (SHOULDER, True),
        (HIP, False),
        (HIP, True),
    ]
    for leg in hydra.legs:
        assert abs(leg.foot.y - FLOOR) < 6.0
        assert leg.hip.distance_to(leg.knee) == pytest.approx(THIGH, abs=0.1)


def test_the_body_follows_the_path_its_front_took_over_a_window_edge():
    world = world_with(Rect(300, 550, 300, 150))
    hydra = lying(world, 520, 550)
    calm(hydra)
    standing(world, 1000)
    path = []
    worst = 0.0

    def follow() -> None:
        nonlocal worst
        path.append(hydra.lead)
        if hydra.mode is not Mode.WALK or len(path) < 120:
            return
        for s in hydra.segments[6:]:
            near = min(_distance_to_path(s.contact, path), _on_start(s.contact))
            worst = max(worst, near)

    assert run(world, 14.0, until=lambda: hydra.lead.x > 750 and hydra.lead.y == FLOOR, each=follow)
    run(world, 1.0, each=follow)
    assert worst < 1.5


def _on_start(point: Vec2) -> float:
    """How far `point` is off where the body lay at the start (along the window top)."""
    return abs(point.y - 550) if point.x <= 520 else 1e9


def _distance_to_path(point: Vec2, path: list[Vec2]) -> float:
    best = 1e9
    for a, b in zip(path, path[1:], strict=False):
        span = b - a
        length = span.length_sq()
        t = 0.0 if length < 1e-12 else max(0.0, min(1.0, (point - a).dot(span) / length))
        best = min(best, point.distance_to(a + span * t))
    return best


def test_it_trots_slowly_in_diagonal_pairs_and_planted_feet_do_not_slide():
    world = world_with()
    hydra = lying(world, 200)
    calm(hydra)
    standing(world, 1300)
    before: dict[tuple[int, bool], Vec2] = {}
    slides = []
    walked = []
    lifts = {key: 0 for key in ((SHOULDER, True), (SHOULDER, False), (HIP, True), (HIP, False))}

    def check() -> None:
        walked.append(hydra.lead.x)
        legs = {(leg.segment, leg.near): leg for leg in hydra.legs}
        assert len(legs) == 4
        for key, leg in legs.items():
            if leg.planted and key in before:
                slides.append(leg.foot.distance_to(before[key]))
            if not leg.planted and key in before:
                lifts[key] += 1
        assert legs[SHOULDER, True].planted == legs[HIP, False].planted
        assert legs[SHOULDER, False].planted == legs[HIP, True].planted
        assert legs[SHOULDER, True].planted or legs[SHOULDER, False].planted
        before.clear()
        before.update({key: leg.foot for key, leg in legs.items() if leg.planted})

    run(world, 6.0, each=check)
    distance = walked[-1] - walked[0]
    assert 120.0 < distance < 6.0 * CHASE_SPEED
    assert max(b - a for a, b in zip(walked, walked[1:], strict=False)) <= CHASE_SPEED * STEP + 1e-6
    assert slides and max(slides) < 0.3
    steps = distance / STRIDE
    assert all(steps - 1.5 <= count <= steps + 1.5 for count in lifts.values())


def test_it_plants_itself_once_its_heads_reach_and_stands_still():
    world = world_with()
    hydra = lying(world, 300)
    calm(hydra)
    foe = standing(world, 760)
    assert run(world, 14.0, until=lambda: any(h.target is foe for h in hydra.heads))
    run(world, 0.8)
    lead = hydra.lead
    feet = {(leg.segment, leg.near): leg.foot for leg in hydra.legs}
    run(world, 1.5)
    assert hydra.lead.distance_to(lead) < 3.0
    for leg in hydra.legs:
        assert leg.foot.distance_to(feet[leg.segment, leg.near]) < 3.0
    assert foe.center().distance_to(hydra.chest) > 60.0


# ----- necks and heads -------------------------------------------------------------------


def test_five_necks_stay_within_reach_and_never_go_nan():
    world = world_with(Rect(700, 500, 250, 200))
    hydra = lying(world, 400)
    for x, y in ((520, FLOOR), (300, FLOOR), (800, 500), (1100, FLOOR)):
        standing(world, x, y, "ranger")

    def check() -> None:
        assert len(hydra.heads) == 5
        for head in hydra.heads:
            assert finite(head.position) and all(finite(p) for p in head.neck)
            assert head.neck[0].distance_to(head.root) < 0.5
            assert head.position.distance_to(head.root) <= head.length + 0.5
            assert head.length < HEAD_REACH[head.index]
            step = head.length / (len(head.neck) - 1)
            for a, b in zip(head.neck, head.neck[1:], strict=False):
                assert a.distance_to(b) <= step + 0.5

    run(world, 12.0, each=check)
    middle = hydra.heads[2]
    assert middle.length == max(h.length for h in hydra.heads) and middle.scale > 1.0


def test_resting_heads_keep_their_mouths_shut_and_open_them_to_spray():
    world = world_with()
    hydra = lying(world, 300)
    calm(hydra)
    run(world, 2.0)
    assert all(head.mouth < 0.02 for head in hydra.heads)
    standing(world, 440, variant="rogue")
    widest = [0.0] * 5
    idle = [0.0] * 5

    def watch() -> None:
        for head in hydra.heads:
            busy = head.target is not None or head.spraying
            idle[head.index] = 0.0 if busy else idle[head.index] + STEP
            if idle[head.index] > 0.5:
                assert head.mouth < 0.02
            widest[head.index] = max(widest[head.index], head.mouth)

    run(world, 6.0, each=watch)
    assert max(widest) > 0.9


def test_heads_pick_their_own_targets_and_spray_acid_that_dissolves_them():
    world = world_with()
    said = []
    world.say = lambda actor, message: said.append(message)
    hydra = lying(world, 300)
    calm(hydra)
    rogue = standing(world, 440, variant="rogue")
    wizard = standing(world, 470, variant="wizard")
    started: list[tuple[float, int]] = []
    was = [False] * 5
    targets = set()

    def watch() -> None:
        for head in hydra.heads:
            if head.target is not None:
                targets.add(id(head.target))
            if head.spraying and not was[head.index]:
                started.append((hydra.clock, head.index))
            was[head.index] = head.spraying

    assert run(world, 15.0, until=lambda: not rogue.animated and not wizard.animated, each=watch)
    assert {rogue.demise.kind, wizard.demise.kind} == {"acid"}
    assert said.count(DEATH) == 2 and world.kills == 2 and hydra.kills == 2
    assert len(targets) == 2
    times = sorted(t for t, _ in started)
    assert len({i for _, i in started}) >= 2
    assert all(b - a >= ATTACK_GAP - 1e-6 for a, b in zip(times, times[1:], strict=False))


def test_close_foes_get_a_heavy_chomp_far_ones_acid_on_staggered_per_head_timers():
    world = world_with()
    said = []
    world.say = lambda actor, message: said.append(message)
    hydra = lying(world, 300)
    calm(hydra)
    run(world, 0.5)
    chest = hydra.chest
    paladin = standing(world, chest.x + 25 * hydra.facing, variant="paladin")
    far = standing(world, chest.x + 150 * hydra.facing, variant="barbarian")
    starts: list[tuple[float, int, str]] = []
    was = [""] * 5

    def watch() -> None:
        for head in hydra.heads:
            now = "chomp" if head.chomping else "spray" if head.spraying else ""
            if now and now != was[head.index]:
                starts.append((hydra.clock, head.index, now))
            was[head.index] = now

    run(world, 8.0, each=watch)
    kinds = {kind for _, _, kind in starts}
    assert kinds == {"chomp", "spray"}
    assert hydra.chomps > 0 and hydra.sprays > 0
    assert paladin.damage >= CHOMP_DAMAGE or CHOMP_DEATH in said
    assert far.damage > 0
    times = sorted(t for t, _, _ in starts)
    assert all(b - a >= ATTACK_GAP - 1e-6 for a, b in zip(times, times[1:], strict=False))
    for index in range(5):
        own = [t for t, i, _ in starts if i == index]
        assert all(b - a >= ATTACK_COOLDOWN - 1e-6 for a, b in zip(own, own[1:], strict=False))


def test_heads_strike_a_foe_behind_it_without_the_body_turning():
    world = world_with()
    hydra = lying(world, 400)
    calm(hydra)
    run(world, 0.5)
    facing = hydra.facing
    behind = standing(world, hydra.chest.x - 60 * facing, variant="paladin")
    turned = []
    run(world, 4.0, each=lambda: turned.append(hydra.facing != facing or hydra.turn_wait > 0))
    assert not any(turned)
    assert behind.damage > 0 or not behind.animated


def test_one_spray_takes_a_few_hp_not_a_life():
    world = world_with()
    hydra = lying(world, 300)
    calm(hydra)
    barbarian = standing(world, 440, variant="barbarian")
    assert run(world, 6.0, until=lambda: barbarian.damage > 0)
    assert barbarian.damage == ACID_DAMAGE and barbarian.animated
    run(world, 0.5)
    assert barbarian.damage == ACID_DAMAGE


# ----- diving and breaking out -------------------------------------------------------------


def test_a_dive_hides_it_segment_by_segment_and_underground_it_cant_be_hit():
    world = world_with(Rect(200, 400, 500, 300))
    hydra = lying(world, 400, 400)
    calm(hydra)
    hydra.surfaced = MIN_SURFACED
    run(world, 0.5)
    hydra._dive()
    assert hydra.mode is Mode.DIVE and hydra.hole is not None and hydra.hole.box == 0
    hidden = []
    run(world, 5.0, until=lambda: hydra.underground, each=lambda: hidden.append(_hidden(hydra)))
    assert hydra.underground
    counts = [h for h in hidden if h is not None]
    assert counts[0] < 3 and counts[-1] >= len(hydra.segments) - 1
    assert all(b >= a for a, b in zip(counts, counts[1:], strict=False))
    assert DIVE_COOLDOWN[0] - 1.0 <= hydra.dive_cooldown <= DIVE_COOLDOWN[1]
    point = hydra.lead
    assert hydra not in world.monsters()
    assert world.locate(hydra) is None and not hydra.hits(point, 50.0)
    assert not world.hurt_monster(hydra, 3, point, Vec2(0, 0))
    assert hydra.hp == HYDRA_HP


def _hidden(hydra: Hydra) -> int | None:
    if hydra.mode is not Mode.DIVE:
        return None
    return sum(1 for s in hydra.segments if s.hidden)


def test_it_breaks_out_of_a_window_top_and_slithers_off():
    world = world_with(Rect(300, 450, 500, 250))
    hydra = world.add_hydra(Vec2(500, 450), facing=1)
    assert hydra.underground and hydra.exit is not None and hydra.exit.box == 0
    assert run(world, 2.0, until=lambda: hydra.mode is Mode.ERUPT)
    hole = hydra.hole
    assert hole is not None and hole.normal == UP and hole.point == Vec2(500, 450)
    assert any(h.center.distance_to(hole.point) < 1.0 for h in world.debris.holes)
    assert run(world, 4.0, until=lambda: hydra.mode is Mode.WALK)
    assert abs(hydra.lead.y - 450) < 0.01 and hydra.lead.x > 520
    for s in shown(hydra):
        assert not (300 < s.center.x < 800 and 451 < s.center.y < 700)
    assert run(
        world, 5.0, until=lambda: hydra.hole is None and not any(s.hidden for s in hydra.segments)
    )


def test_it_breaks_out_of_a_window_side_at_an_adventurer_climbing_it():
    world = world_with(Rect(600, 300, 300, 400))
    hydra = world.add_hydra(Vec2(750, 300), facing=1)
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 600)
    climber = world.add_stickman(Vec2(150, FLOOR), "ranger")
    climber.wander = False
    climber.follower.reset(Anchor(wall, wall.closest_point(Vec2(600, 480))))
    climber.paralyze(60.0)
    world.advance(STEP)
    assert climbing_wall(climber) is not None
    hydra.exit = hydra._pick_exit(hydra.lead)
    assert hydra.exit is not None and hydra.exit.side and hydra.exit.box == 0
    assert hydra.exit.normal == Vec2(-1.0, 0.0)
    assert run(world, 3.0, until=lambda: hydra.mode is Mode.TURRET)
    assert hydra.hole is not None and hydra.hole.side
    out = shown(hydra)
    assert out and all(s.center.x < 600 for s in out)
    assert any(s.hidden for s in hydra.segments)


def test_its_hole_rides_with_its_window():
    world = world_with(Rect(300, 450, 500, 250))
    hydra = world.add_hydra(Vec2(500, 450), facing=1)
    assert run(world, 2.5, until=lambda: hydra.mode is Mode.ERUPT and hydra.mode_time > 0.15)
    before = hydra.hole.point
    lead = hydra.lead
    world.apply_terrain(TerrainChange(moves={0: Vec2(40, -20)}), [Rect(340, 430, 500, 250)])
    assert hydra.hole.point == before + Vec2(40, -20)
    assert hydra.lead.distance_to(lead + Vec2(40, -20)) < 0.01
    assert any(h.center.distance_to(hydra.hole.point) < 1.0 for h in world.debris.holes)


def test_closing_its_window_mid_dive_sends_it_underground_and_it_comes_up_elsewhere():
    world = world_with(Rect(200, 400, 500, 300), Rect(900, 500, 300, 200))
    hydra = lying(world, 400, 400)
    calm(hydra)
    standing(world, 1000, 500)
    run(world, 0.3)
    hydra._dive()
    assert run(world, 2.0, until=lambda: any(s.hidden for s in hydra.segments))
    world.apply_terrain(TerrainChange(remap={0: None, 1: 0}), [world.boxes[1]])
    assert hydra.underground and hydra.hole is None
    assert run(world, 4.0, until=lambda: hydra.mode is Mode.ERUPT)
    assert hydra.hole is not None


def test_closing_its_window_mid_break_out_drops_it_as_a_crawling_body():
    world = world_with(Rect(300, 450, 500, 250))
    hydra = world.add_hydra(Vec2(500, 450), facing=1)
    assert run(world, 2.5, until=lambda: hydra.mode is Mode.ERUPT and hydra.mode_time > 0.15)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert hydra.mode is Mode.FALL and hydra.hole is None
    assert run(world, 4.0, until=lambda: hydra.mode is Mode.WALK)
    assert abs(hydra.lead.y - FLOOR) < 0.01
    assert not any(s.hidden for s in hydra.segments)


def test_it_stays_up_a_while_between_dives():
    world = world_with(Rect(200, 400, 400, 300), Rect(800, 400, 400, 300))
    hydra = world.add_hydra(Vec2(400, 400), facing=1)
    standing(world, 1000, 400)
    downs = []
    ups = []
    was = hydra.mode

    def watch() -> None:
        nonlocal was
        mode = hydra.mode
        if mode is not was:
            if mode in (Mode.DIVE, Mode.RETRACT):
                downs.append(hydra.clock)
            if was is Mode.UNDER:
                ups.append(hydra.clock)
        was = mode

    run(world, 30.0, each=watch)
    assert downs and ups
    for down in downs:
        last_up = max((u for u in ups if u < down), default=None)
        if last_up is not None:
            assert down - last_up >= MIN_SURFACED - 1e-6


# ----- HP and death -------------------------------------------------------------------------


def test_it_has_hydra_hp_dies_limp_and_fades():
    world = world_with()
    hydra = lying(world, 400)
    calm(hydra)
    assert hydra.hp == HYDRA_HP == 20
    head = hydra.heads[2].position
    assert world.monster_at(head) is hydra
    assert not world.hurt_monster(hydra, 3, head, Vec2(0, 0))
    assert hydra.hp == HYDRA_HP - 3
    assert world.hurt_monster(hydra, HYDRA_HP, hydra.center(), Vec2(0, -40))
    assert hydra.dead and hydra not in world.hydras and hydra in world.fallen
    run(world, 2.0)
    for head in hydra.heads:
        assert head.position.y > FLOOR - 25.0
    assert all(s.grounded or s.contact.y == FLOOR for s in hydra.segments)
    assert run(world, 20.0, until=lambda: hydra not in world.fallen)


def test_it_follows_the_drakes_in_the_desktop_rotation_and_fills_the_health_bar():
    assert DEFENDERS[:4] == ("chimera", "drow", "drakes", "hydra")
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(400, 400, 400, 200))])
    session = DesktopSession(screen, usable, source, seed=2, max_stickmen=0)
    session.rotate()  # past the chimera
    session.rotate()  # past the drow
    session.rotate()  # past the drake riders
    assert session.defender == "hydra" and len(session.hydras) == 1
    hydra = session.hydras[0]
    assert hydra.underground and hydra.exit is not None and hydra.exit.point.y == 400
    assert session.live_monsters == [hydra] and session.defender_health == 1.0
    assert run(session, 3.0, until=lambda: hydra.visible)
    session.hurt_monster(hydra, 1, hydra.center(), Vec2(0, 0))
    assert abs(session.defender_health - (HYDRA_HP - 1) / HYDRA_HP) < 1e-9
    session.hurt_monster(hydra, HYDRA_HP, hydra.center(), Vec2(0, -40))
    run(session, 0.1)
    assert session.defender == "mimic" and not session.hydras


def test_its_exit_is_a_window_side_only_off_screen_edges_and_clear_of_other_windows():
    world = world_with(Rect(5, 300, 395, 400), Rect(410, 300, 300, 400))
    hydra = lying(world, 250, 300)
    exits = hydra._side_exits()
    for exit_ in exits:
        assert not (exit_.box == 0 and exit_.normal.x < 0)
        assert not (exit_.box == 0 and exit_.normal.x > 0)
        assert not (exit_.box == 1 and exit_.normal.x < 0)
        assert 0.0 < exit_.out <= TURRET_OUT
    assert isinstance(exits[0], Exit)


MAXIMIZED = Rect(18, TOP + 40, WIDTH - 36, FLOOR - TOP - 40 - 24)


def climbing_lane(world: SimWorld, ys: tuple[float, ...]) -> list:
    """Adventurers frozen on the left side of the maximized window, in its cramped lane."""
    wall = next(s for s in world.planner.surfaces if s.wall and s.box == 0 and s.start.x == 18)
    men = []
    for y in ys:
        man = world.add_stickman(Vec2(700, FLOOR), "ranger")
        man.wander = False
        man.follower.reset(Anchor(wall, wall.closest_point(Vec2(18, y))))
        man.paralyze(60.0)
        men.append(man)
    world.advance(STEP)
    assert all(climbing_wall(m) is not None for m in men)
    return men


def test_it_never_comes_out_into_a_cramped_lane_beside_a_maximized_window():
    world = world_with(MAXIMIZED)
    hydra = lying(world, 700, MAXIMIZED.top)
    climbing_lane(world, (400,))
    assert hydra._side_exits() == []


def test_from_the_top_it_leans_over_and_drops_a_glob_that_clears_the_cramped_lane():
    world = world_with(MAXIMIZED)
    hydra = lying(world, 300, MAXIMIZED.top)
    calm(hydra)
    hydra.glob_cooldown = 0.0
    men = climbing_lane(world, (250, 450, 620))
    bystander = standing(world, 1000, MAXIMIZED.top)
    assert run(world, 10.0, until=lambda: all(not m.animated for m in men))
    assert hydra.globs == 1 and hydra.glob_cooldown > GLOB_COOLDOWN - 10.0
    assert bystander.animated and bystander.damage == 0
    run(world, 3.0)
    assert hydra.globs == 1


def test_from_below_it_burrows_up_onto_the_top_to_drop_its_glob():
    world = world_with(MAXIMIZED)
    hydra = lying(world, 700)
    hydra.glob_cooldown = 0.0
    hydra.surfaced = MIN_SURFACED
    men = climbing_lane(world, (300, 500))
    assert run(world, 14.0, until=lambda: all(not m.animated for m in men))
    assert hydra.globs == 1 and hydra.eruptions >= 1


def test_it_only_breaks_out_of_tops_and_floor_with_room_to_climb_out():
    low_window = Rect(560, FLOOR - 50, 200, 30)
    world = world_with(Rect(100, 400, 400, 300), low_window, Rect(900, 360, 300, 40))
    hydra = lying(world, 250, 400)
    standing(world, 650)
    exits = [e for e in hydra._exit_candidates() if not e.side]
    assert exits
    for exit_ in exits:
        for k in range(11):
            x = exit_.point.x + exit_.facing * LANDING * k / 10
            for rise in (5.0, 30.0, HEADROOM - 5.0):
                spot = Vec2(x, exit_.point.y - rise)
                assert not any(box.contains(spot) for box in world.boxes)


def test_it_squeezes_along_the_lane_under_a_maximized_window_and_bites_there():
    low = Rect(20, TOP + 40, WIDTH - 40, FLOOR - TOP - 40 - 24)
    world = world_with(low)
    under = Vec2(700, FLOOR)
    assert any(s.walkable and s.contains(under, 1.0) for s in world.hydra_planner.surfaces)
    hydra = lying(world, 700, low.top)
    standing(world, 900)
    exits = [e for e in hydra._exit_candidates() if not e.side]
    assert any(low.left < e.point.x < low.right and e.point.y == FLOOR for e in exits)
    world.hydras.remove(hydra)
    squeezed = lying(world, 700)
    calm(squeezed)
    man = world.stickmen[0]
    hp = man.hp
    assert run(world, 6.0, until=lambda: man.hp < hp or man not in world.stickmen)
    assert squeezed._over == frozenset({0})
