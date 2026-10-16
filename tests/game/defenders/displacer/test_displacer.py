import math

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.defenders.displacer.actor import (
    BODY_HEIGHT,
    CHEST,
    CLAW_DAMAGE,
    CLAW_REACH,
    DISPLACER_HP,
    FOE_COMMIT,
    FRENZY_MAX,
    FRENZY_POUNCES,
    FRENZY_RANGE,
    HALF_LENGTH,
    HOLD_BACK,
    MELEE_COOLDOWN,
    OVERLAP,
    POUNCE_COOLDOWN,
    POUNCE_DAMAGE,
    POUNCE_RANGE,
    RUSE_COOLDOWN,
    RUSE_TIME,
    SLIDE_MAX,
    STAB_DAMAGE,
    STAB_REACH,
    STAB_TIMES,
    TURN_COOLDOWN,
    Displacer,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange

STEP = 1 / 60
FLOOR = 700.0
WIDTH = 1200.0
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


def tame(beast: Displacer) -> Displacer:
    """No spontaneous leaps, so it goes where it's sent on foot."""
    beast.leap_wait = 1e9
    return beast


def send(beast: Displacer, point: Vec2) -> None:
    assert beast._route_to(point)
    beast.goal = point


def arrived(beast: Displacer, point: Vec2, near: float = 4.0):
    return lambda: (
        not beast.airborne
        and beast.follower.route is None
        and beast.position.distance_to(point) <= near
    )


def surface_of(world: SimWorld, box: int, kind: str):
    return next(s for s in world.displacer_planner.surfaces if s.box == box and getattr(s, kind))


# ----- prowling and climbing -------------------------------------------------------


def test_it_prowls_along_a_window_top_upright():
    world = world_with(Rect(300, 400, 500, 300))
    beast = tame(world.add_displacer(Vec2(340, 400)))
    assert beast.support.box == 0 and beast.support.walkable
    goal = Vec2(760, 400)
    send(beast, goal)
    phases = []

    def check():
        assert beast.support is not None and beast.support.box == 0
        assert beast.up.distance_to(Vec2(0, -1)) < 1e-6
        assert abs(beast.body.y - (400 - BODY_HEIGHT)) < 1e-6
        phases.append(beast.phase)

    assert run(world, 20.0, until=arrived(beast, goal), each=check)
    assert max(phases) - min(phases) > 1.0, "its legs cycled"


def test_it_climbs_a_wall_to_a_higher_top():
    world = world_with(Rect(200, 550, 200, 150), Rect(400, 300, 200, 400))
    beast = tame(world.add_displacer(Vec2(250, 550)))
    assert beast.support.box == 0
    goal = Vec2(500, 300)
    send(beast, goal)
    walls = set()

    def check():
        surface = beast.support
        if surface is not None and not surface.horizontal and not beast.follower.in_transition:
            walls.add(surface.box)
            assert abs(beast.up.y) < 1e-6, "body square to the wall"

    assert run(world, 30.0, until=arrived(beast, goal), each=check)
    assert 1 in walls and beast.support.box == 1 and beast.support.walkable


def test_it_crawls_along_an_underside_upside_down():
    world = world_with(Rect(300, 250, 500, 100))
    beast = tame(world.add_displacer(Vec2(250, FLOOR)))
    goal = Vec2(550, 350)
    send(beast, goal)
    assert run(world, 60.0, until=arrived(beast, goal))
    assert beast.support.hanging and beast.support.box == 0
    assert beast.up.distance_to(Vec2(0, 1)) < 1e-6
    assert beast.body.y > 350 and abs(beast.position.y - 350) < 1e-6
    send(beast, Vec2(700, 350))
    assert run(world, 10.0, until=arrived(beast, Vec2(700, 350)))
    assert beast.support.hanging


# ----- leaps and pounces -----------------------------------------------------------


def leap_to(world: SimWorld, beast: Displacer, anchor: Anchor) -> None:
    assert beast._try_leap(anchor, "leap")
    went = []
    assert run(
        world,
        5.0,
        until=lambda: beast.pending is None and not beast.airborne and beast.land_left <= 0,
        each=lambda: went.append(beast.airborne),
    )
    assert any(went), "it flew"
    assert beast.support is anchor.surface
    assert beast.position.distance_to(anchor.point) <= SLIDE_MAX


def test_a_leap_lands_on_another_windows_top():
    world = world_with(Rect(200, 450, 200, 250), Rect(600, 350, 250, 350))
    beast = tame(world.add_displacer(Vec2(300, 450)))
    top = surface_of(world, 1, "walkable")
    leap_to(world, beast, Anchor(top, top.point_at(700)))
    assert beast.up.distance_to(Vec2(0, -1)) < 1e-6


def test_a_leap_lands_on_a_wall():
    world = world_with(Rect(200, 450, 200, 250), Rect(600, 200, 250, 150))
    beast = tame(world.add_displacer(Vec2(300, 450)))
    wall = next(s for s in world.displacer_planner.surfaces if s.box == 1 and not s.horizontal)
    leap_to(world, beast, Anchor(wall, wall.point_at((wall.low + wall.high) / 2)))
    assert abs(beast.up.y) < 1e-6


def test_a_leap_from_the_floor_lands_upside_down_on_an_underside():
    world = world_with(Rect(500, 380, 300, 100))
    beast = tame(world.add_displacer(Vec2(420, FLOOR)))
    under = surface_of(world, 0, "hanging")
    leap_to(world, beast, Anchor(under, under.point_at(600)))
    assert beast.up.distance_to(Vec2(0, 1)) < 1e-6 and beast.body.y > 480


def drawn(beast: Displacer, victim) -> None:
    """As if its illusion had drawn `victim`: fair game for a pounce."""
    beast.ruse_wait = 1e9
    beast.fair, beast.fair_left = victim, 1e9


def test_it_pounces_from_farther_onto_a_drawn_adventurer_for_10_damage():
    assert POUNCE_RANGE >= 250.0 and POUNCE_DAMAGE == 10
    world = world_with(Rect(300, 450, 300, 250))
    beast = world.add_displacer(Vec2(900, FLOOR))
    beast.leap_wait = 0.0
    victim = world.add_stickman(Vec2(650, FLOOR), "paladin")
    victim.paralyze(30.0)
    drawn(beast, victim)
    launches = []

    def check():
        leap = beast.leap
        if leap is not None and leap.kind == "pounce" and not launches:
            launches.append(leap.start.distance_to(victim.center()))

    assert run(world, 20.0, until=lambda: launches and not beast.airborne, each=check)
    assert launches[0] > 170.0
    assert beast.position.distance_to(victim.contact()) < 15.0
    assert victim.damage == 10 and not victim.animated
    assert world.kills == 1 and world.kill_marks


def test_it_never_pounces_from_afar_on_someone_its_illusion_hasnt_drawn():
    world = world_with(Rect(300, 450, 300, 250))
    beast = world.add_displacer(Vec2(900, FLOOR))
    beast.leap_wait = 0.0
    beast.ruse_wait = 1e9
    victim = world.add_stickman(Vec2(650, FLOOR), "paladin")
    victim.paralyze(30.0)
    pounces = []
    run(world, 10.0, each=lambda: beast.leap and beast.leap.kind == "pounce" and pounces.append(1))
    assert not pounces and victim.damage == 0
    assert beast.intent.value == "stalk"
    assert beast.body.distance_to(victim.center()) > HOLD_BACK - 30.0


def test_a_pounce_he_dodged_lands_where_he_was_and_does_no_harm():
    world = world_with(Rect(300, 450, 300, 250))
    beast = world.add_displacer(Vec2(900, FLOOR))
    beast.leap_wait = 0.0
    victim = world.add_stickman(Vec2(700, FLOOR), "paladin")
    victim.paralyze(30.0)
    drawn(beast, victim)
    assert run(world, 20.0, until=lambda: beast.leap is not None and beast.leap.kind == "pounce")
    where = beast.leap.target.point
    beast.leap.quarry = world.add_stickman(Vec2(100, FLOOR), "paladin")
    assert run(world, 3.0, until=lambda: not beast.airborne)
    assert beast.position.distance_to(where) < 1.0
    assert victim.damage == 0 and world.kills == 0


# ----- its illusion ------------------------------------------------------------------


def ruse(variant: str = "barbarian", paralysed: bool = False):
    world = world_with(Rect(900, 450, 260, 250))
    beast = world.add_displacer(Vec2(150, FLOOR))
    man = world.add_stickman(Vec2(500, FLOOR), variant)
    if paralysed:
        man.paralyze(60.0)
    return world, beast, man


def test_its_illusion_goes_out_the_moment_it_starts_stalking_then_after_a_cooldown():
    for x in (110.0, 390.0):
        world = world_with(Rect(900, 450, 260, 250))
        beast = tame(world.add_displacer(Vec2(150, FLOOR)))
        beast.rest = 1e9
        run(world, 2.0)
        assert beast.ghost is None
        man = world.add_stickman(Vec2(150 + x, FLOOR), "paladin")
        man.paralyze(60.0)
        assert run(world, 1.0, until=lambda beast=beast: beast.intent.value == "stalk")
        assert beast.ghost is not None, x
        ghost = beast.ghost
        assert ghost.illusion and ghost.owner is beast and ghost.ghost is None
        assert ghost.position.distance_to(beast.position) < 30.0 and ghost.presence < 0.5
    assert run(world, RUSE_TIME + 2.0, until=lambda: beast.ghost is None)
    assert beast.ruse_wait == RUSE_COOLDOWN
    seen = []
    run(world, RUSE_COOLDOWN - 0.2, each=lambda: seen.append(beast.ghost))
    assert not any(seen)
    assert run(world, 1.0, until=lambda: beast.ghost is not None)


def test_adventurers_go_for_its_illusion_over_the_beast_even_when_its_nearer():
    world, beast, man = ruse("paladin", paralysed=True)
    assert beast._split(man)
    run(world, 0.3)
    ghost = beast.ghost
    assert ghost.feinting
    near_beast = beast.center() + (beast.center() - ghost.center()).normalized() * 5.0
    assert world.nearest_monster(near_beast, 200.0)[0] is ghost
    assert [m for m, _ in world.monsters_near(near_beast, 200.0)][:2] == [ghost, beast]


def test_its_illusion_feints_from_both_sides_without_harm():
    world, beast, man = ruse("paladin", paralysed=True)
    beast.leap_wait = 1e9
    sides = set()

    def check():
        ghost = beast.ghost
        if ghost is not None and ghost.act == "strike" and not ghost.airborne:
            sides.add(ghost.body.x > man.center().x)
            assert ghost.body.distance_to(man.center()) < 40.0

    run(world, RUSE_TIME + 1.0, each=check)
    assert sides == {True, False}
    assert man.damage == 0 and man.animated


def test_the_adventurer_turns_on_its_illusion_and_his_blows_pass_through():
    world, beast, man = ruse("barbarian")
    beast.leap_wait = 1e9
    hits = []

    def check():
        ghost = beast.ghost
        if ghost is not None and man.foe is ghost and ghost.shimmer > 0.0:
            hits.append(ghost)

    assert run(world, RUSE_TIME, until=lambda: hits, each=check)
    ghost = hits[0]
    assert ghost in world.monsters() and world.locate(ghost) is not None
    assert world.monster_at(ghost.center()) is ghost
    assert ghost not in world.displacers and not ghost.dead and ghost.damage == 0
    assert not world.hurt_monster(ghost, DISPLACER_HP, ghost.center(), Vec2(0, 0))
    assert not ghost.dead and beast.damage == 0 and world.monster_kills == 0


def test_the_ruse_ends_in_the_real_beast_pouncing_on_him():
    for variant in ("barbarian", "rogue", "wizard"):
        world, beast, man = ruse(variant)
        during = []

        def check(beast=beast, during=during):
            leap = beast.leap
            if leap is not None and leap.kind == "pounce" and not during:
                ghost = beast.ghost
                during.append(ghost is not None and ghost.feinting)

        assert run(world, 12.0, until=lambda man=man: not man.animated, each=check), variant
        assert during == [True] and man.damage == 10 and world.kills == 1


def test_it_pounces_while_he_fights_its_illusion_without_waiting_for_it_to_cross():
    for variant in ("barbarian", "rogue", "wizard"):
        world, beast, man = ruse(variant)
        crouched = []

        def check(beast=beast, man=man, crouched=crouched):
            leap = beast.pending
            if leap is not None and leap.kind == "pounce" and not crouched:
                ghost = beast.ghost
                crouched.append((ghost.feints, ghost.act, man.foe is ghost))

        assert run(world, 6.0, until=lambda man=man: not man.animated, each=check), variant
        assert len(crouched) == 1, variant
        feints, act, engaged = crouched[0]
        assert feints <= 1 and act in ("out", "strike") and engaged, (variant, crouched)


# ----- its frenzy --------------------------------------------------------------------


def frenzy_world(spots=(480, 570, 660, 750, 840)):
    world = world_with()
    beast = world.add_displacer(Vec2(250, FLOOR))
    beast.leap_wait = 0.0
    men = [world.add_stickman(Vec2(x, FLOOR), "paladin") for x in spots]
    thrall = world.add_stickman(Vec2(525, FLOOR), "paladin")
    thrall.enthrall()
    far = world.add_stickman(Vec2(1150, FLOOR), "paladin")
    for stickman in (*men, thrall, far):
        stickman.paralyze(60.0)
    drawn(beast, men[0])
    return world, beast, men, thrall, far


def test_a_landed_pounce_sends_it_into_a_frenzy_of_pounces_on_whoever_is_near():
    world, beast, men, thrall, far = frenzy_world()
    leaps, longest = [], [0.0]

    def check():
        leap = beast.leap
        if leap is not None and leap.kind == "frenzy" and leap not in leaps:
            leaps.append(leap)
            assert leap.start.distance_to(leap.quarry.center()) <= FRENZY_RANGE + 1.0
        longest[0] = max(longest[0], beast.frenzy_time)

    assert run(world, 6.0, until=lambda: beast.frenzy_left > 0.0, each=check)
    assert men[0].damage == POUNCE_DAMAGE and not leaps
    assert run(world, FRENZY_MAX + 1.0, until=lambda: beast.frenzy_left <= 0.0, each=check)
    assert len(leaps) == FRENZY_POUNCES
    assert [leap.quarry for leap in leaps] == men[1 : 1 + FRENZY_POUNCES]
    assert all(m.damage == POUNCE_DAMAGE for m in men[: 1 + FRENZY_POUNCES])
    assert longest[0] <= FRENZY_MAX + 1e-6
    assert thrall.damage == 0 and far.damage == 0


def test_after_its_frenzy_it_goes_back_to_its_usual_ways():
    world, beast, men, thrall, far = frenzy_world((480,))
    assert run(world, 6.0, until=lambda: beast.frenzy_left > 0.0)
    assert run(world, FRENZY_MAX, until=lambda: beast.frenzy_left <= 0.0)
    assert beast.leap_wait > POUNCE_COOLDOWN - 1.0
    pounces = []
    run(
        world,
        2.0,
        each=lambda: beast.leap and beast.leap.kind in ("pounce", "frenzy") and pounces.append(1),
    )
    assert not pounces and beast.intent.value != "fight"
    assert thrall.damage == 0


def test_its_illusion_stays_out_of_the_health_bar_and_rotation():
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(900, 400, 300, 200))])
    session = DesktopSession(
        screen, usable, source, seed=2, max_stickmen=0, defenders=("displacer", "mindflayer")
    )
    beast = session.displacers[0]
    man = session.add_stickman(Vec2(beast.position.x + 200, usable.bottom), "paladin")
    assert beast._split(man)
    run(session, 1.0)
    ghost = beast.ghost
    assert ghost is not None and ghost in session.monsters()
    assert session.live_monsters == [beast] and session.defender_health == 1.0
    session.hurt_monster(ghost, 5, ghost.center(), Vec2(0, 0))
    assert session.defender_health == 1.0 and session.monster_kills == 0


def test_its_illusion_vanishes_when_it_dies():
    world, beast, man = ruse("paladin", paralysed=True)
    assert run(world, 3.0, until=lambda: beast.ghost is not None and beast.ghost.feinting)
    ghost = beast.ghost
    world.hurt_monster(beast, DISPLACER_HP, beast.center(), Vec2(0, 0))
    assert ghost.vanishing and ghost not in world.monsters()
    assert run(world, 1.0, until=lambda: beast.ghost is None)


def test_its_illusion_vanishes_when_its_window_closes():
    world = world_with(Rect(100, 450, 400, 250))
    beast = tame(world.add_displacer(Vec2(200, 450)))
    man = world.add_stickman(Vec2(450, 450), "paladin")
    man.paralyze(60.0)
    assert beast._split(man)
    run(world, 0.6)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert beast.ghost is None or beast.ghost.vanishing
    assert run(world, 1.0, until=lambda: beast.ghost is None)


# ----- up close: claw swipes and tentacle stabs --------------------------------------


def facing_right(world: SimWorld, x: float = 250.0) -> Displacer:
    beast = tame(world.add_displacer(Vec2(x, FLOOR)))
    beast.heading = 1
    beast.head_yaw = beast.tail_yaw = 0.0
    return beast


def swing(beast: Displacer, kind: str) -> None:
    beast._start_attack(kind)
    while beast.attack is not None:
        beast._swing(STEP)


def standing(world: SimWorld, x: float, variant: str = "barbarian"):
    man = world.add_stickman(Vec2(x, FLOOR), variant)
    man.paralyze(30.0)
    return man


def test_between_two_foes_in_reach_it_attacks_instead_of_turning_back_and_forth():
    world = world_with()
    beast = facing_right(world)
    beast.harried = 1e9
    beast.ruse_wait = 1e9
    left, right = standing(world, 185, "paladin"), standing(world, 318, "paladin")
    clock, attacks, flips = [0.0], [0.0], []
    heading = [beast.heading]

    def check():
        clock[0] += STEP
        if beast.attack is not None and beast.attack_time <= STEP + 1e-9:
            attacks.append(clock[0])
        if beast.heading != heading[0]:
            heading[0] = beast.heading
            flips.append(clock[0])

    run(world, 4.0, each=check)
    attacks.append(clock[0])
    assert len(attacks) >= 5
    assert max(b - a for a, b in zip(attacks, attacks[1:], strict=False)) < 2.0
    assert len(flips) <= len(attacks) - 2
    assert left.damage > 0 and right.damage > 0


def test_it_sticks_with_its_foe_unless_someone_else_is_much_nearer():
    world = world_with()
    beast = facing_right(world)
    beast.harried = 1e9
    first = standing(world, 340)
    beast._fight(STEP, first)
    nearer = standing(world, 190)
    assert beast._choose_foe() is first
    beast.time += FOE_COMMIT
    assert beast._choose_foe() is nearer
    beast._fight(STEP, nearer)
    assert beast._choose_foe() is nearer
    close = standing(world, 272)
    assert beast._choose_foe() is close


def test_turning_about_on_the_spot_is_a_shuffle_not_a_walk():
    world = world_with()
    beast = facing_right(world)
    run(world, 0.5)
    beast._set_heading(-1)
    before = beast.phase
    assert run(world, 2.0, until=lambda: beast._turn_left() < 0.05)
    assert beast.phase - before < 0.3
    assert beast.body.distance_to(Vec2(250, FLOOR - BODY_HEIGHT)) < 3.0


def test_under_attack_it_fights_instead_of_stalking_and_sends_no_illusion():
    world = world_with()
    beast = tame(world.add_displacer(Vec2(150, FLOOR)))
    beast.rest = 1e9
    man = standing(world, 500, "paladin")
    world.hurt_monster(beast, 1, beast.center(), Vec2(0, 0))
    run(world, 0.5)
    assert beast.intent.value == "fight" and beast.foe is man and beast.ghost is None


def test_left_alone_a_while_it_goes_back_to_stalking_with_its_illusion():
    world = world_with()
    beast = tame(world.add_displacer(Vec2(150, FLOOR)))
    beast.rest = 1e9
    standing(world, 520, "paladin")
    beast.harried = 1.0
    run(world, 0.5)
    assert beast.intent.value == "fight" and beast.ghost is None
    assert run(world, 1.5, until=lambda: beast.ghost is not None)
    assert beast.intent.value == "stalk" and beast.harried <= 0.0


def test_an_illusion_already_out_carries_on_when_the_beast_is_attacked():
    world, beast, man = ruse("paladin", paralysed=True)
    assert run(world, 1.0, until=lambda: beast.ghost is not None)
    ghost = beast.ghost
    world.hurt_monster(beast, 1, beast.center(), Vec2(0, 0))
    run(world, 0.5)
    assert beast.ghost is ghost and not ghost.vanishing
    assert beast.intent.value == "fight"


def hanging_on(world: SimWorld, surface, point: Vec2, heading: int = 1) -> Displacer:
    """The beast put straight onto `surface` at `point`, settled there."""
    beast = tame(world.add_displacer(Vec2(50, FLOOR)))
    beast.rest = 1e9
    beast._attach(Anchor(surface, surface.closest_point(point)))
    beast.heading = heading
    beast.look_up = beast.up
    beast.head_yaw = beast.tail_yaw = 0.0 if heading > 0 else math.pi
    for _ in range(30):
        beast._animate(STEP)
    return beast


def stab(beast: Displacer, man) -> None:
    beast._stab_foe = man
    beast._aim_stab(man)
    swing(beast, "stab")


def test_its_tentacle_stab_spears_him_for_4_in_any_direction():
    world = world_with(Rect(300, 560, 300, 80))
    beast = hanging_on(world, surface_of(world, 0, "hanging"), Vec2(450, 640))
    below = standing(world, 455)
    assert beast.up.y > 0.9 and below.center().y > beast.body.y
    stab(beast, below)
    assert below.damage == STAB_DAMAGE == 4

    world = world_with(Rect(500, 400, 200, 300))
    wall = next(s for s in world.displacer_planner.surfaces if s.box == 0 and s.normal.x < -0.5)
    beast = hanging_on(world, wall, Vec2(500, 640))
    at_foot = standing(world, 475)
    assert abs(beast.up.y) < 1e-6 and at_foot.center().y > beast.body.y
    stab(beast, at_foot)
    assert at_foot.damage == 4

    world = world_with(Rect(150, 660, 80, 40))
    beast = facing_right(world)
    behind_above = world.add_stickman(Vec2(215, 660), "barbarian")
    behind_above.paralyze(30.0)
    behind = standing(world, 195)
    for man in (behind_above, behind):
        assert (man.center() - beast.body).x < 0.0
        stab(beast, man)
        assert man.damage == 4

    world = world_with()
    beast = facing_right(world)
    away = standing(world, 250 + 25 + STAB_REACH)
    stab(beast, away)
    assert away.damage == 0


def test_its_stab_follows_him_while_it_winds_up_but_a_dodge_after_can_miss():
    world = world_with()
    beast = facing_right(world)
    man = standing(world, 320)
    beast._stab_foe = man
    beast._aim_stab(man)
    beast._start_attack("stab")
    beast._swing(0.05)
    aimed = beast.stab_way
    beast._aim_stab(standing(world, 200))
    beast._swing(0.05)
    assert beast.stab_way.distance_to(aimed) < 1e-6
    beast.stab_way = Vec2(0.0, -1.0)
    beast.attack_time = STAB_TIMES[0]
    while beast.attack is not None:
        beast._swing(STEP)
    assert man.damage == 0


def test_its_claw_swipe_hits_up_close_for_4_but_not_out_of_reach():
    world = world_with()
    beast = facing_right(world)
    close, away = standing(world, 298), standing(world, 345)
    assert beast.to_world(CHEST).distance_to(close.center()) <= CLAW_REACH
    assert beast._claw_reaches(close) and not beast._claw_reaches(away)
    swing(beast, "claw")
    assert close.damage == CLAW_DAMAGE == 4 and away.damage == 0


def melee_log(world, beast, man, seconds: float):
    """Each attack it starts (time, kind) and whether it hurt `man`, who's kept alive."""
    log, clock, last = [], [0.0], [math.inf]

    def check():
        clock[0] += STEP
        if man.damage > 0 and log:
            log[-1][2] = True
        man.damage = 0
        now = beast.attack_time if beast.attack is not None else math.inf
        if now < last[0]:
            log.append([clock[0], beast.attack, False])
        last[0] = now

    run(world, seconds, each=check)
    return log


def test_it_claws_and_stabs_by_turns_never_swiping_the_air():
    world = world_with()
    beast = facing_right(world)
    beast.harried = 1e9
    man = standing(world, 300, "paladin")
    log = melee_log(world, beast, man, 6.0)
    kinds = [kind for _, kind, _ in log]
    assert len(kinds) >= 5
    assert all(a != b for a, b in zip(kinds, kinds[1:], strict=False)), kinds
    assert all(hit for _, _, hit in log), log
    times = [t for t, _, _ in log]
    assert all(b - a >= MELEE_COOLDOWN - 2 * STEP for a, b in zip(times, times[1:], strict=False))


def test_with_him_behind_or_under_it_it_stabs_instead_of_swiping():
    world = world_with(Rect(300, 560, 300, 80))
    beast = hanging_on(world, surface_of(world, 0, "hanging"), Vec2(450, 640))
    beast.harried = 1e9
    man = standing(world, 455, "paladin")
    log = melee_log(world, beast, man, 3.0)
    assert len(log) >= 2 and all(hit for _, _, hit in log), log
    assert all(kind == "stab" or hit for _, kind, hit in log)


def wall_foot(beast_at: Vec2):
    world = world_with(Rect(500, 450, 250, 250))
    beast = world.add_displacer(beast_at)
    beast.leap_wait = beast.ruse_wait = 1e9
    beast.harried = 1e9
    man = standing(world, 488, "paladin")
    return world, beast, man


def test_an_adventurer_at_the_foot_of_a_wall_gets_killed_from_either_side():
    for start in (Vec2(250, FLOOR), Vec2(650, 450)):
        world, beast, man = wall_foot(start)
        closest = [math.inf]

        def check(beast=beast, man=man, closest=closest):
            if beast.attack is not None:
                closest[0] = min(closest[0], beast.body.distance_to(man.center()))

        assert run(world, 8.0, until=lambda man=man: not man.animated, each=check), start
        assert man.damage >= man.max_hp
        assert closest[0] >= OVERLAP, (start, closest)


def test_it_never_attacks_a_thrall():
    world = world_with()
    beast = facing_right(world)
    thrall = standing(world, 298)
    thrall.enthrall()
    run(world, 3.0)
    swing(beast, "claw")
    stab(beast, thrall)
    assert thrall.damage == 0 and beast.attack is None


def test_its_illusion_never_attacks():
    world, beast, man = ruse("paladin", paralysed=True)
    beast.leap_wait = 1e9
    attacks = []

    def check():
        ghost = beast.ghost
        if ghost is not None and ghost.attack is not None:
            attacks.append(ghost.attack)
        if ghost is not None and ghost.frenzy_left > 0.0:
            attacks.append("frenzy")

    run(world, RUSE_TIME, each=check)
    assert not attacks and man.damage == 0


def test_its_illusion_never_frenzies():
    world, beast, man = ruse("paladin", paralysed=True)
    beast.leap_wait = 1e9
    near = world.add_stickman(Vec2(600, FLOOR), "paladin")
    near.paralyze(60.0)
    frenzied = []

    def check():
        ghost = beast.ghost
        if ghost is not None and (ghost.frenzy_left > 0.0 or ghost.fury > 0.0):
            frenzied.append(ghost)
        if ghost is not None and ghost.leap is not None and ghost.leap.kind == "frenzy":
            frenzied.append(ghost)

    run(world, RUSE_TIME, each=check)
    assert not frenzied and man.damage == 0 and near.damage == 0


# ----- hit points, the rotation and windows closing --------------------------------


def test_it_has_hit_points_and_dies_and_fades():
    world = world_with(Rect(300, 400, 400, 300))
    beast = world.add_displacer(Vec2(500, 400))
    assert beast.max_hp == DISPLACER_HP == 14
    assert world.monster_at(beast.center()) is beast
    world.hurt_monster(beast, 5, beast.center(), Vec2(30, 0))
    assert not beast.dead and beast in world.displacers
    world.hurt_monster(beast, DISPLACER_HP - 5, beast.center(), Vec2(30, 0))
    assert beast.dead and beast not in world.displacers and beast in world.fallen
    assert run(world, 15.0, until=lambda: beast not in world.fallen)


def test_it_follows_the_minotaur_in_the_desktop_rotation():
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(400, 400, 400, 200))])
    session = DesktopSession(screen, usable, source, seed=2, max_stickmen=0)
    session.rotate()  # past the chimera
    session.rotate()  # past the drow
    session.rotate()  # past the drake riders
    assert session.defender == "hydra"
    session.rotate()
    assert session.defender == "mimic"
    session.rotate()
    assert session.defender == "lich"
    session.rotate()
    assert session.defender == "minotaur"
    session.rotate()
    assert session.defender == "displacer" and len(session.displacers) == 1
    beast = session.displacers[0]
    session.hurt_monster(beast, DISPLACER_HP, beast.center(), Vec2(0, -40))
    run(session, 0.1)
    assert session.defender == "mindflayer" and not session.displacers


def test_it_survives_its_window_closing_under_it():
    world = world_with(Rect(300, 250, 500, 100))
    beast = tame(world.add_displacer(Vec2(250, FLOOR)))
    send(beast, Vec2(550, 350))
    assert run(world, 60.0, until=arrived(beast, Vec2(550, 350)))
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert run(world, 5.0, until=lambda: not beast.airborne and beast.land_left <= 0)
    assert beast.support.box is None and beast.position.y == FLOOR
    assert beast in world.displacers and not math.isnan(beast.body.x)
    beast.leap_wait = 0.0
    run(world, 5.0)
    assert not beast.airborne or beast.body.y < FLOOR


def test_a_leap_whose_target_window_closes_lands_somewhere_safe():
    world = world_with(Rect(200, 450, 200, 250), Rect(600, 300, 250, 400))
    beast = tame(world.add_displacer(Vec2(300, 450)))
    top = surface_of(world, 1, "walkable")
    assert beast._try_leap(Anchor(top, top.point_at(700)), "leap")
    assert run(world, 2.0, until=lambda: beast.airborne)
    world.apply_terrain(TerrainChange(remap={0: 0, 1: None}), [world.boxes[0]])
    assert run(world, 5.0, until=lambda: not beast.airborne and beast.land_left <= 0)
    assert beast.support is not None
    assert not Rect(200, 450, 200, 250).contains(beast.body)


# ----- its bending body and turning about ---------------------------------------


def clearance(world: SimWorld, point: Vec2) -> float:
    """How far `point` is from the nearest window or the floor (negative inside one)."""
    best = FLOOR - point.y
    for box in world.boxes:
        dx = max(box.left - point.x, 0.0, point.x - box.right)
        dy = max(box.top - point.y, 0.0, point.y - box.bottom)
        if dx == 0.0 and dy == 0.0:
            return -min(
                point.x - box.left, box.right - point.x, point.y - box.top, box.bottom - point.y
            )
        best = min(best, math.hypot(dx, dy))
    return best


def follow_round(world: SimWorld, beast: Displacer, goal: Vec2):
    """Send it to `goal`, checking its chest and hips stay their height off the surfaces
    under them all the way; the most its body bent on the way."""
    send(beast, goal)
    bends = []

    def check():
        spine = beast.spine()
        for x in (HALF_LENGTH, -HALF_LENGTH):
            gap = clearance(world, spine.at(x, 0.0))
            assert BODY_HEIGHT - 4.0 <= gap <= BODY_HEIGHT + 4.0, (beast.time, x, gap)
        front, back = spine.frame(HALF_LENGTH)[1], spine.frame(-HALF_LENGTH)[1]
        bends.append(math.acos(max(-1.0, min(1.0, front.dot(back)))))

    assert run(world, 30.0, until=arrived(beast, goal), each=check)
    return max(bends)


def test_its_body_bends_over_an_outside_corner_front_first():
    world = world_with(Rect(400, 300, 200, 400))
    beast = tame(world.add_displacer(Vec2(470, 300)))
    assert follow_round(world, beast, Vec2(600, 460)) > 1.2


def test_its_body_bends_up_an_inside_corner_hips_staying_on_the_floor():
    world = world_with(Rect(400, 300, 200, 400))
    beast = tame(world.add_displacer(Vec2(300, FLOOR)))
    assert follow_round(world, beast, Vec2(400, 560)) > 1.2


def test_its_body_bends_from_a_side_onto_an_underside():
    world = world_with(Rect(400, 200, 300, 120))
    beast = tame(world.add_displacer(Vec2(380, FLOOR)))
    send(beast, Vec2(400, 240))
    assert run(world, 30.0, until=arrived(beast, Vec2(400, 240)))
    assert follow_round(world, beast, Vec2(540, 320)) > 1.2


def test_it_turns_about_in_depth_head_first_never_flipping():
    world = world_with(Rect(300, 400, 500, 300))
    beast = tame(world.add_displacer(Vec2(520, 400)))
    send(beast, Vec2(600, 400))
    run(world, 1.0)
    send(beast, Vec2(420, 400))
    turns, leads, face_on = [beast.turn], [], []

    def check():
        turns.append(beast.turn)
        leads.append(beast.head_yaw - beast.tail_yaw)
        face_on.append(abs(math.cos(beast.head_yaw)) < 0.2)

    run(world, 0.6, each=check)
    assert turns[0] > 0.99 and turns[-1] < -0.99
    assert max(abs(b - a) for a, b in zip(turns, turns[1:], strict=False)) < 0.2
    assert any(face_on), "its face comes round toward us"
    assert max(leads) > 0.5, "the head leads, the tail comes round last"
    assert sum(1 for t in turns if abs(t) < 0.9) * STEP >= 0.15, "it takes its time"


def test_it_doesnt_dither_turning_back_and_forth():
    world = world_with(Rect(300, 400, 500, 300))
    beast = tame(world.add_displacer(Vec2(550, 400)))
    flips, last = [], beast.heading
    for i in range(30):
        send(beast, Vec2(520 if i % 2 else 580, 400))
        for _ in range(6):
            world.advance(STEP)
            if beast.heading != last:
                flips.append(beast.time)
                last = beast.heading
    gaps = [b - a for a, b in zip(flips, flips[1:], strict=False)]
    assert flips and min(gaps) >= TURN_COOLDOWN - STEP


def test_hit_testing_follows_the_drawn_body_round_corners_and_turns():
    world = world_with(Rect(400, 300, 200, 400))
    beast = tame(world.add_displacer(Vec2(470, 300)))
    send(beast, Vec2(600, 460))

    def check():
        middle, shoulders, hips, head = beast.parts()
        for point in (shoulders, hips, head):
            assert world.monster_at(point) is beast
        assert shoulders.distance_to(beast.to_world(Vec2(HALF_LENGTH, -1.0))) < 1e-9

    assert run(world, 30.0, until=arrived(beast, Vec2(600, 460)), each=check)
