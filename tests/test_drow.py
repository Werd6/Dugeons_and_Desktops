from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.overlay import DEFENDER_BARS
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.actors.mortal import DROW_HP, LIZARD_HP
from dungeons_desktops.game.defenders.drow.actor import (
    CROSSBOW_DAMAGE,
    LIZARD_LEGS,
    PERCH_RANGE,
    Drow,
    Lizard,
)
from dungeons_desktops.game.defenders.drow.darkness import FADE_TIME, GLOBE_TIME
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Move
from dungeons_desktops.navigation.terrain import TerrainChange

STEP = 1 / 60
BOXES = [Rect(200, 250, 400, 200), Rect(750, 150, 300, 300)]


def run(world, seconds: float, until=None, each=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()
        if until is not None and until():
            return


def unkillable(*stickmen):
    hits = []
    for stickman in stickmen:

        def hurt(amount, point, push, source, death, bleed=True, who=stickman):
            hits.append((who, source, amount))
            return False

        stickman.hurt = hurt
    return hits


def where(lizard: Lizard) -> str:
    support = lizard.support
    if support is None:
        return "air"
    if support.walkable:
        return "top"
    return "under" if support.hanging else "wall"


def test_the_drow_ride_in_after_the_chimera_two_lizards_on_the_front_window():
    window = Rect(300, 300, 600, 400)
    world = DesktopSession(
        Rect(0, 0, 1400, 900),
        Rect(0, 30, 1400, 800),
        FakeWindowSource([WindowRecord(1, window)]),
        seed=3,
        max_stickmen=0,
    )
    world.rotate()  # past the chimera
    assert DEFENDERS[1] == "drow" and world.defender == "drow"
    assert DEFENDER_BARS["drow"][0] == "Drow lizard riders"
    assert len(world.lizards) == 2 and all(z.mounted for z in world.lizards)
    assert all(z.support is not None and z.support.start.y == window.top for z in world.lizards)
    assert world.lizards[0].center().distance_to(world.lizards[1].center()) > 30.0
    assert world.defender_max_hp == 2 * (LIZARD_HP + DROW_HP)
    assert world.defender_health == 1.0


def test_lizards_patrol_up_walls_and_along_undersides():
    world = SimWorld(BOXES, 800.0, 1400.0, ceiling=0.0, seed=3)
    lizards = [world.add_lizard(Vec2(300, 250), 1), world.add_lizard(Vec2(850, 150), -1)]
    seen = set()
    run(world, 40.0, each=lambda: seen.update(where(z) for z in lizards))
    assert {"top", "wall", "under"} <= seen


def test_its_four_feet_plant_on_what_its_climbing_and_stay_put():
    world = SimWorld(BOXES, 800.0, 1400.0, ceiling=0.0, seed=3)
    lizard = world.add_lizard(Vec2(300, 250), 1)
    rig = lizard.rig
    last = {}
    worst = {"drift": 0.0, "off": 0.0, "stepping": 0}

    def check():
        worst["stepping"] = max(worst["stepping"], sum(leg.stepping for leg in rig.legs))
        for i, leg in enumerate(rig.legs):
            if leg.planted:
                if i in last:
                    worst["drift"] = max(worst["drift"], leg.foot.distance_to(last[i]))
                off = min(
                    s.closest_point(leg.foot).distance_to(leg.foot)
                    for s in world.displacer_planner.surfaces
                )
                worst["off"] = max(worst["off"], off)
                last[i] = leg.foot
            else:
                last.pop(i, None)

    steps = rig.steps
    run(world, 20.0, each=check)
    assert rig.steps - steps > 100, "it scurries on its legs, a step at a time"
    assert worst["stepping"] <= LIZARD_LEGS.max_stepping
    assert worst["drift"] < 0.01, "a planted foot stays put"
    assert worst["off"] < 0.5, "planted feet are on a surface"
    assert rig.forced < rig.steps * 0.1


def test_it_skirmishes_from_perches_off_from_its_foe_while_the_rider_shoots():
    world = SimWorld([Rect(500, 600, 200, 200)], 800.0, 1400.0, ceiling=0.0, seed=4)
    lizard = world.add_lizard(Vec2(300, 800), 1)
    man = world.add_stickman(Vec2(820, 800))
    man.stop()
    hits = unkillable(man)
    gaps = []
    run(world, 20.0, each=lambda: gaps.append(lizard.center().distance_to(man.center())))
    shots = [h for h in hits if h[1] == "drow"]
    assert len(shots) >= 3 and all(amount == CROSSBOW_DAMAGE for _, _, amount in shots)
    assert min(gaps[120:]) > PERCH_RANGE[0] * 0.5, "it keeps its distance"


def test_it_climbs_down_a_wall_rather_than_drop_off_a_window():
    for bottom in (800, 740):
        world = SimWorld([Rect(300, 500, 300, bottom - 500)], 800.0, 1100.0, ceiling=0.0, seed=2)
        lizard = world.add_lizard(Vec2(450, 500), 1)
        assert lizard._route_to(Vec2(150, 800))
        steps = lizard.follower.route.steps
        assert any(s.move is Move.CLIMB and s.end.y >= bottom - 1.0 for s in steps)
        hops = [s for s in steps if s.move in (Move.JUMP, Move.DROP)]
        assert all(abs(s.end.y - s.start.y) <= 800 - bottom + 1.0 for s in hops)


def test_it_never_leaps_or_pounces_on_adventurers():
    world = SimWorld([Rect(500, 600, 200, 200)], 800.0, 1400.0, ceiling=0.0, seed=5)
    lizards = [world.add_lizard(Vec2(300, 800), 1), world.add_lizard(Vec2(600, 600), -1)]
    men = [world.add_stickman(Vec2(x, 800), wander=True) for x in (420, 900, 1100)]
    unkillable(*men)
    leaps = []
    run(world, 30.0, each=lambda: leaps.extend(z.leap for z in lizards if z.leap is not None))
    assert not leaps


def test_its_legs_stay_with_it_through_a_jump_up():
    world = SimWorld([Rect(500, 690, 200, 60)], 800.0, 1100.0, ceiling=0.0, seed=2)
    lizard = world.add_lizard(Vec2(300, 800), 1)
    run(world, 0.2)
    lizard._think = lambda dt: None
    assert lizard._route_to(Vec2(600, 690))
    assert any(s.move is Move.JUMP for s in lizard.follower.route.steps)
    worst = {"jump": 0.0, "reach": 0.0, "air": False}
    last = None

    def check():
        nonlocal last
        legs = lizard.rig.legs
        rel = [leg.foot - leg.hip for leg in legs]
        if last is not None:
            jump = max(a.distance_to(b) for a, b in zip(rel, last, strict=True))
            worst["jump"] = max(worst["jump"], jump)
        last = rel
        worst["reach"] = max(worst["reach"], max(r.length() for r in rel))
        worst["air"] |= lizard.airborne

    run(world, 6.0, each=check)
    assert worst["air"], "it did jump"
    assert worst["jump"] < 16.0, "no foot snaps about"
    assert worst["reach"] < LIZARD_LEGS.reach * 1.35, "no leg stretches out of shape"


def test_the_rider_picks_off_whoever_faerie_fire_lights_up_first():
    world = SimWorld([], 800.0, 1400.0, ceiling=0.0, seed=2)
    lizard = world.add_lizard(Vec2(600, 800), 1)
    near = world.add_stickman(Vec2(760, 800))
    far = world.add_stickman(Vec2(840, 800))
    for man in (near, far):
        man.stop()
    unkillable(near, far)
    lizard.globe_cooldown = 99.0
    run(world, 0.1)
    assert lizard.mark is near
    far.faerie = 5.0
    run(world, 0.1)
    assert lizard.mark is far


def test_a_globe_of_darkness_blinds_and_lights_up_everyone_in_it_till_it_fades():
    world = SimWorld([], 800.0, 1400.0, ceiling=0.0, seed=2)
    inside = [world.add_stickman(Vec2(x, 800)) for x in (600, 630)]
    outside = world.add_stickman(Vec2(900, 800))
    world.darkness.burst(Vec2(615, 780))
    run(world, 0.5)
    for man in inside:
        assert man.blind > 0.0 and man.faerie > 0.0 and not man._can_act()
    assert outside.blind == 0.0 and outside.faerie == 0.0 and outside._can_act()
    start = [m.contact() for m in inside]
    run(world, 3.0)
    assert any(m.contact().distance_to(s) > 3.0 for m, s in zip(inside, start, strict=True)), (
        "they grope about"
    )
    run(world, GLOBE_TIME + FADE_TIME)
    for man in inside:
        assert man.blind == 0.0 and man.faerie == 0.0 and man._can_act()
    assert not world.darkness.globes


def test_the_rider_throws_his_globe_at_the_thick_of_them():
    world = SimWorld([], 800.0, 1400.0, ceiling=0.0, seed=2)
    lizard = world.add_lizard(Vec2(500, 800), 1)
    bunch = [world.add_stickman(Vec2(x, 800)) for x in (690, 700, 715)]
    loner = world.add_stickman(Vec2(560, 800))
    for man in (*bunch, loner):
        man.stop()
    unkillable(*bunch, loner)
    lizard.globe_cooldown = 0.0
    run(world, 2.5, until=lambda: bool(world.darkness.globes))
    assert len(world.darkness.globes) == 1
    assert world.darkness.globes[0].center.distance_to(Vec2(702, 790)) < 25.0
    assert lizard.globe_cooldown > 5.0


def test_the_mounted_drow_cant_be_hit_blows_meant_for_him_land_on_his_lizard():
    world = SimWorld([], 800.0, 1400.0, ceiling=0.0, seed=2)
    lizard = world.add_lizard(Vec2(500, 800), 1)
    assert world.monster_at(lizard.rider_head) is lizard
    assert (
        world.closest_part(lizard, lizard.rider_shoulder + Vec2(0, -3)).distance_to(
            lizard.rider_shoulder
        )
        < 1.0
    )
    world.hurt_monster(lizard, 1, lizard.rider_head, Vec2(0.0, 0.0))
    assert lizard.hp == LIZARD_HP - 1 and lizard.mounted and not world.drow


def test_when_its_lizard_dies_the_drow_leaps_off_and_cuts_his_way_in_on_foot():
    world = SimWorld([Rect(300, 600, 300, 100)], 800.0, 1000.0, ceiling=0.0, seed=2)
    lizard = world.add_lizard(Vec2(450, 600), 1)
    world.hurt_monster(lizard, LIZARD_HP, lizard.center(), Vec2(0.0, 0.0))
    assert lizard.dead and not lizard.mounted and lizard in world.fallen
    assert len(world.drow) == 1
    drow = world.drow[0]
    assert isinstance(drow, Drow) and drow in world.monsters()
    heights = []
    run(world, 1.5, each=lambda: heights.append(drow.contact().y))
    assert any(abs(y - 600.0) < 0.5 for y in heights), "he lands on the window top"
    man = world.add_stickman(Vec2(700, 800))
    man.stop()
    hits = unkillable(man)
    run(world, 12.0, until=lambda: len(hits) >= 4)
    assert len([h for h in hits if h[1] == "drow"]) >= 4, "two cuts a swing"


def test_on_foot_the_drow_are_quicker_than_goblins():
    world = SimWorld([], 800.0, 1400.0, ceiling=0.0, seed=2)
    drow = world.add_drow(Vec2(200, 800))
    goblin = world.add_goblin(Vec2(200, 800))
    man = world.add_stickman(Vec2(1200, 800))
    man.stop()
    unkillable(man)
    run(world, 3.0)
    assert drow.contact().x - 200 > 1.3 * (goblin.contact().x - 200) > 0.0


def test_the_pack_holds_the_screen_until_the_dismounted_drow_are_dead_too():
    window = Rect(300, 300, 600, 400)
    world = DesktopSession(
        Rect(0, 0, 1400, 900),
        Rect(0, 30, 1400, 800),
        FakeWindowSource([WindowRecord(1, window)]),
        seed=3,
        max_stickmen=0,
        defenders=DEFENDERS[DEFENDERS.index("drow") :],
    )
    for lizard in list(world.lizards):
        world.hurt_monster(lizard, LIZARD_HP, lizard.center(), Vec2(0.0, 0.0))
    run(world, 0.1)
    assert world.defender == "drow" and len(world.drow) == 2
    assert abs(world.defender_health - DROW_HP / (LIZARD_HP + DROW_HP)) < 1e-9
    for drow in list(world.drow):
        world.hurt_monster(drow, DROW_HP, drow.center(), Vec2(0.0, 0.0))
    run(world, 0.1)
    assert world.defender == "drakes" and not world.drow and not world.lizards


def test_a_lizard_rides_its_window_and_falls_when_it_closes():
    world = SimWorld([Rect(300, 300, 300, 100)], 800.0, 1000.0, ceiling=0.0, seed=2)
    lizard = world.add_lizard(Vec2(450, 300), 1)
    run(world, 0.2)
    before = lizard.position
    feet = [leg.foot for leg in lizard.rig.legs]
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(330, 280, 300, 100)])
    assert lizard.position.distance_to(before + Vec2(30, -20)) < 1.0
    for leg, foot in zip(lizard.rig.legs, feet, strict=True):
        if leg.planted:
            assert leg.foot.distance_to(foot + Vec2(30, -20)) < 1.0
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    run(world, 3.0)
    assert lizard.support is not None and lizard.support.box is None
