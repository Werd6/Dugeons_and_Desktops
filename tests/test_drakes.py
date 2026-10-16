from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DEFENDERS, DRAKE_PACK, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.systems.drakes import (
    ARROW_DAMAGE,
    BITE_DAMAGE,
    BOLT_COOLDOWN,
    BOLT_DAMAGE,
    BOLT_GRAVITY,
    BOLT_SPEED,
    COLOURS,
    GROUND_FIGHT,
    HOVER_HEIGHT,
    HOVER_RANGE,
    HOVER_TIME,
    LAND_SCATTER,
    STANDOFF,
    DrakeMode,
    Missile,
    lobbed,
)
from dungeons_desktops.systems.mortal import DRAKE_HP, KOBOLD_HP
from dungeons_desktops.systems.world import SimWorld

STEP = 1 / 60


def run(world: SimWorld, seconds: float, until=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if until is not None and until():
            return


def test_the_pack_rides_in_three_drakes_of_different_random_colours_on_the_front_window():
    window = Rect(300, 300, 600, 400)
    packs = set()
    for seed in range(8):
        world = DesktopSession(
            Rect(0, 0, 1400, 900),
            Rect(0, 30, 1400, 800),
            FakeWindowSource([WindowRecord(1, window)]),
            seed=seed,
            max_stickmen=0,
            defenders=DEFENDERS[DEFENDERS.index("drakes") :],
        )
        assert world.defender == "drakes"
        colours = [d.variant for d in world.drakes]
        assert len(colours) == DRAKE_PACK == 3 and len(set(colours)) == 3
        assert set(colours) <= set(COLOURS)
        assert all(d.support is not None and d.support.start.y == window.top for d in world.drakes)
        assert world.defender_max_hp == DRAKE_PACK * (DRAKE_HP + KOBOLD_HP)
        assert world.defender_health == 1.0
        packs.add(frozenset(colours))
    assert len(packs) > 1


def unkillable(*stickmen):
    """Record what hurts them instead of hurting them, so a test can watch a fight."""
    hits = []
    for stickman in stickmen:

        def hurt(amount, point, push, source, death, bleed=True, who=stickman):
            hits.append((who, source, amount))
            return False

        stickman.hurt = hurt
    return hits


def tough(world):
    for drake in world.drakes:
        drake.max_hp = 999


def test_on_foot_it_runs_up_to_an_adventurer_on_its_own_surface_and_bites_him():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=1)
    drake = world.add_drake(Vec2(300, 400), "red", facing=1)
    tough(world)
    man = world.add_stickman(Vec2(450, 400))
    man.stop()
    hits = unkillable(man)
    drake.ground_timer = GROUND_FIGHT
    run(world, 4.0, until=lambda: drake.flying)
    assert drake.mode is DrakeMode.WALK
    assert abs(drake.x - man.contact().x) <= STANDOFF + 3.0
    assert (man, "drake", BITE_DAMAGE) in hits


def test_after_its_ground_fight_it_takes_off_and_holds_station_off_to_the_side_above_him():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=1)
    drake = world.add_drake(Vec2(300, 400), "red", facing=1)
    tough(world)
    man = world.add_stickman(Vec2(500, 400))
    man.stop()
    unkillable(man)
    run(world, GROUND_FIGHT + 1.0, until=lambda: drake.flying)
    assert drake.mode is DrakeMode.FLY
    run(world, HOVER_TIME - 1.5)
    assert drake.mode is DrakeMode.FLY
    offset = drake.body - man.center()
    assert HOVER_RANGE - 20.0 <= abs(offset.x) <= HOVER_RANGE + 20.0
    assert HOVER_HEIGHT - 20.0 <= -offset.y <= HOVER_HEIGHT + 20.0


def test_it_hovers_for_seven_seconds_then_dives_on_an_adventurer_on_the_ground():
    world = SimWorld([], 400.0, 1400.0, ceiling=0.0, seed=1)
    drake = world.add_drake(Vec2(100, 400), "red", facing=1)
    tough(world)
    man = world.add_stickman(Vec2(1100, 400))
    man.stop()
    unkillable(man)
    run(world, 2.0, until=lambda: drake.flying)
    assert drake.mode is DrakeMode.FLY
    run(world, HOVER_TIME + 0.5, until=lambda: drake.mode is DrakeMode.DIVE)
    assert drake.mode is DrakeMode.DIVE and abs(drake.mode_time) < 0.1
    run(world, 4.0, until=lambda: not drake.flying)
    assert drake.mode is DrakeMode.WALK
    assert abs(drake.x - man.contact().x) < LAND_SCATTER[1] + 4.0


def test_the_pack_flies_to_an_adventurer_on_another_window_and_dives_in_around_him():
    boxes = [Rect(100, 300, 300, 100), Rect(560, 220, 300, 180)]
    world = SimWorld(boxes, 400.0, 1000.0, ceiling=0.0, seed=2)
    for i, colour in enumerate(COLOURS):
        world.add_drake(Vec2(160 + i * 18, 300), colour)
    tough(world)
    man = world.add_stickman(Vec2(720, 220))
    man.stop()
    unkillable(man)
    dived = set()

    def landed() -> bool:
        dived.update(d.variant for d in world.drakes if d.mode is DrakeMode.DIVE)
        return len(dived) == len(COLOURS) and not any(d.flying for d in world.drakes)

    run(world, 14.0, until=landed)
    assert dived == set(COLOURS)
    for drake in world.drakes:
        assert drake.mode is DrakeMode.WALK
        assert drake.support is not None and drake.support.start.y == 220.0


def test_the_pack_comes_down_at_scattered_spots_not_one_heap():
    world = SimWorld([], 400.0, 1400.0, ceiling=0.0, seed=4)
    for i, colour in enumerate(COLOURS):
        world.add_drake(Vec2(100 + i * 15, 400), colour)
    tough(world)
    man = world.add_stickman(Vec2(800, 400))
    man.stop()
    unkillable(man)
    spots = {}

    def watch() -> bool:
        for d in world.drakes:
            if d.mode is DrakeMode.DIVE and d.landing is not None and d.mode_time > 0.5:
                spots.setdefault(d.variant, d.landing.x)
        return len(spots) == len(COLOURS)

    run(world, 20.0, until=watch)
    xs = sorted(spots.values())
    assert len(xs) == len(COLOURS)
    assert min(b - a for a, b in zip(xs, xs[1:], strict=False)) > 8.0
    assert all(abs(x - man.contact().x) <= LAND_SCATTER[1] + 1.0 for x in xs)


def test_the_kobold_shoots_whoever_is_nearest_him_not_the_drakes_quarry():
    world = SimWorld([], 400.0, 1400.0, ceiling=0.0, seed=1)
    drake = world.add_drake(Vec2(300, 400), "blue", facing=1)
    tough(world)
    near = world.add_stickman(Vec2(450, 400))
    far = world.add_stickman(Vec2(1000, 400))
    for man in (near, far):
        man.stop()
    hits = unkillable(near, far)
    drake.bolt_cooldown = 99.0
    drake._walk = lambda dt: None
    for _ in range(round(6.0 / STEP)):
        drake.quarry, drake.retarget = far, 99.0
        world.advance(STEP)
    arrows = [who for who, source, amount in hits if source == "kobold"]
    assert len(arrows) >= 2 and all(who is near for who in arrows)
    assert all(amount == ARROW_DAMAGE for _, source, amount in hits if source == "kobold")


def test_every_four_seconds_the_drake_spits_a_breath_bolt_at_its_quarry():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=1)
    drake = world.add_drake(Vec2(300, 400), "green", facing=1)
    tough(world)
    man = world.add_stickman(Vec2(480, 400))
    man.stop()
    hits = unkillable(man)
    drake.bolt_cooldown = 0.5
    drake.bow_cooldown = 99.0
    drake.ground_timer = 99.0
    bolts = 0
    for _ in range(round((0.5 + 2 * BOLT_COOLDOWN + 0.5) / STEP)):
        before = drake.bolt_cooldown
        world.advance(STEP)
        bolts += drake.bolt_cooldown > before
    assert bolts == 3
    assert hits.count((man, "drake", BOLT_DAMAGE)) >= 2


def test_a_bolt_bursts_in_a_flask_sized_blast_that_hurts_everyone_in_it():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=1)
    drake = world.add_drake(Vec2(200, 400), "white", facing=1)
    a = world.add_stickman(Vec2(500, 400))
    b = world.add_stickman(Vec2(520, 400))
    c = world.add_stickman(Vec2(500 + world.vials.blast_radius + 40, 400))
    for man in (a, b, c):
        man.stop()
    hits = unkillable(a, b, c)
    drake._burst(Vec2(510, 398))
    assert drake.blasts and drake.blasts[0].radius == world.vials.blast_radius
    assert sorted(id(who) for who, *_ in hits) == sorted([id(a), id(b)])
    assert all((source, amount) == ("drake", BOLT_DAMAGE) for _, source, amount in hits)


def test_with_nobody_about_it_wanders_then_flies_off_to_another_window():
    boxes = [Rect(100, 300, 200, 100), Rect(600, 250, 200, 150)]
    world = SimWorld(boxes, 400.0, 1000.0, ceiling=0.0, seed=4)
    drake = world.add_drake(Vec2(200, 300), "white")
    start = drake.support
    drake.ground_timer = 0.5
    run(world, 1.0)
    assert drake.flying and drake.landing is not None
    run(world, 10.0, until=lambda: not drake.flying)
    assert drake.mode is DrakeMode.WALK and drake.support is not start


def test_a_drake_whose_window_closes_takes_wing_and_lands_somewhere_else():
    world = SimWorld([Rect(300, 250, 300, 150)], 400.0, 1000.0, ceiling=0.0, seed=6)
    drake = world.add_drake(Vec2(450, 250), "blue")
    drake.ground_timer = 99.0
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert drake.flying
    run(world, 8.0, until=lambda: not drake.flying)
    assert drake.mode is DrakeMode.WALK
    assert drake.support is not None and drake.support.start.y == 400.0


def test_a_drake_shot_down_in_flight_falls_lies_there_and_fades():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=3)
    drake = world.add_drake(Vec2(400, 400), "black")
    drake.ground_timer = 0.0
    run(world, 0.6)
    assert drake.flying
    world.hurt_monster(drake, DRAKE_HP, drake.body, Vec2(50.0, 0.0))
    assert drake not in world.drakes and drake in world.fallen and drake.dead
    run(world, 2.0)
    assert abs(drake.body.y - (400.0 - 4.0)) < 0.5
    run(world, 4.0)
    assert drake not in world.fallen


def test_adventurers_can_find_and_hit_a_drake():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=3)
    drake = world.add_drake(Vec2(400, 400), "green")
    assert drake in world.monsters()
    assert world.locate(drake) == drake.body
    assert world.monster_at(drake.body) is drake
    assert world.monster_at(drake.rider_head) is drake
    part = world.closest_part(drake, drake.rider_head + Vec2(0.0, -10.0))
    assert part == drake.rider_head


def test_a_bolt_flies_through_windows_and_bursts_where_it_was_aimed():
    world = SimWorld([Rect(380, 300, 60, 100)], 400.0, 1000.0, ceiling=0.0, seed=1)
    drake = world.add_drake(Vec2(250, 400), "red", facing=1)
    drake.bow_cooldown = drake.bolt_cooldown = 99.0
    drake._walk = lambda dt: None
    target = Vec2(560, 380)
    drake.bolts.append(
        Missile(drake.mouth, lobbed(drake.mouth, target, BOLT_SPEED, BOLT_GRAVITY), target=target)
    )
    blasts = []
    for _ in range(round(2.5 / STEP)):
        world.advance(STEP)
        blasts += [b.center for b in drake.blasts if b.center not in blasts]
    assert blasts == [target]
