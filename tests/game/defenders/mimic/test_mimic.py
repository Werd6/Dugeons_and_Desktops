import math

from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.overlay import DEFENDER_BARS
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.adventurers.actor import LURE_HASTE, Stickman
from dungeons_desktops.game.defenders.mimic.actor import (
    APPROACH,
    CAMO_COOLDOWN,
    CHOMP_AT,
    FRONT,
    GULP_TIME,
    HOP_RANGE,
    HOP_SLIDE,
    KNIFE_DAMAGE,
    LEAP_COOLDOWN,
    LEAP_DAMAGE,
    LURE_DELAY,
    MIMIC_HP,
    MOUNT_HOP,
    REEL_TIME,
    STOW_TIME,
    SWALLOW_TIME,
    TONGUE_OUT,
    TRAP_SNAP,
    Flail,
    Fumble,
    Knife,
    Mimic,
    Mode,
    Toss,
)
from dungeons_desktops.game.defenders.mimic.legs import MAX_STEPPING, REACH
from dungeons_desktops.game.defenders.mimic.render import draw_lure_alert, draw_mimic
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind, TerrainChange

STEP = 1 / 60
FLOOR = 700.0
WIDTH = 1200.0


def world_with(*boxes: Rect, seed: int = 3) -> SimWorld:
    return SimWorld(list(boxes), FLOOR, WIDTH, ceiling=20.0, seed=seed)


def run(world, seconds, until=None) -> bool:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if until is not None and until():
            return True
    return until is None


def record_deaths(monkeypatch) -> list[tuple[str, str]]:
    deaths = []
    hurt = Stickman.hurt

    def recording(self, amount, point, push, source, death, bleed=True):
        killed = hurt(self, amount, point, push, source, death, bleed)
        if killed:
            deaths.append((source, death))
        return killed

    monkeypatch.setattr(Stickman, "hurt", recording)
    return deaths


def revealed(world: SimWorld, mimic: Mimic) -> Mimic:
    mimic._start_reveal()
    run(world, 0.7)
    assert mimic.mode is Mode.HUNT
    return mimic


def test_disguised_it_is_just_a_chest():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    hero = world.add_stickman(Vec2(800, FLOOR), "barbarian")
    hero.lure = None
    assert mimic.mode is Mode.CHEST and not mimic.revealed
    assert mimic not in world.monsters()
    assert world.locate(mimic) is None and world.closest_part(mimic, hero.center()) is None
    assert world.monster_at(mimic.center()) is None
    assert world.monsters_near(mimic.center(), 500) == []
    assert not world.hurt_monster(mimic, MIMIC_HP, mimic.center(), Vec2(0, 0))
    assert mimic.damage == 0 and mimic in world.mimics
    assert abs(mimic.yaw - FRONT) < 1e-9


def test_it_lures_the_nearest_adventurer_who_stows_his_weapon_and_gets_swallowed(monkeypatch):
    deaths = record_deaths(monkeypatch)
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    near = world.add_stickman(Vec2(380, FLOOR), "barbarian")
    far = world.add_stickman(Vec2(900, FLOOR), "wizard")
    assert run(world, 1.0, until=lambda: near.lure is not None)
    assert near.lure is mimic and near in mimic.baited
    assert run(world, 10.0, until=lambda: mimic.mode is Mode.OPEN)
    assert mimic.victim is near and near not in mimic.baited
    assert isinstance(near.locomotion.upper, Fumble)
    assert abs(abs(near.contact().x - mimic.position.x) - 17.0) < 6.0
    run(world, STOW_TIME + 0.1)
    assert near.animated and near.weapon is not None and not near.weapon.held
    assert near.facing == (1 if mimic.position.x > near.contact().x else -1)
    assert mimic.crack == 0.0 or mimic.mode_time > STOW_TIME
    assert run(world, CHOMP_AT, until=lambda: mimic.tongue_tip is not None)
    assert near.animated and near.lure is mimic, "the trap springs: its tongue shoots out"
    assert run(world, TRAP_SNAP + TONGUE_OUT + 0.05, until=lambda: near.reeled is mimic)
    assert mimic.jaw > 0.9 and isinstance(near.locomotion.upper, Flail), "grabbed"
    assert near.lure is None and mimic.caught is near
    start = near.center().distance_to(mimic.mouth())
    run(world, REEL_TIME + 2 * STEP)
    assert mimic.reel_feet(near).distance_to(mimic.mouth()) < 3.0, "reeled up to its mouth"
    assert near.center().y < mimic.mouth().y and start > 10.0
    squeeze = near.squeeze()
    assert squeeze is not None and squeeze[0] == mimic.mouth()
    run(world, SWALLOW_TIME * 0.6)
    assert near.squeeze()[2] < 0.8 and mimic.reel_feet(near).y > mimic.mouth().y, "sinking in"
    assert run(world, SWALLOW_TIME, until=lambda: near not in world.stickmen)
    assert deaths == [("mimic", "Swallowed whole by a mimic!")], "swallowed whole"
    assert world.kills == 1 and mimic.chomps == 1 and near.reeled is None
    assert mimic.gulp > 0.5 and mimic.caught is None and mimic.tongue_tip is None
    run(world, GULP_TIME * 0.5)
    assert mimic.jaw < 0.1, "its lid snaps shut"
    assert run(world, 1.5, until=lambda: mimic.mode is Mode.HUNT)
    assert mimic in world.monsters() and world.locate(mimic) is not None
    assert far.animated and far.lure is None and not mimic.baited


def test_a_baited_rogue_sees_through_it_and_exposes_it_with_a_thrown_dagger():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    rogue = world.add_stickman(Vec2(380, FLOOR), "rogue")
    assert run(world, 1.0, until=lambda: rogue.lure is mimic), "baited like anyone"
    assert run(world, 10.0, until=lambda: mimic.spotter is rogue)
    assert mimic.mode is Mode.CHEST and isinstance(rogue.locomotion.upper, Toss)
    assert rogue.lure is None and rogue.reeled is mimic, "spotted: the bait's off"
    heights = []

    def thrown() -> bool:
        if mimic.knife is not None:
            return True
        heights.append(FLOOR - mimic.reel_feet(rogue).y)
        return False

    assert run(world, 2.0, until=thrown)
    assert max(heights) > 10.0, "he hops back"
    assert (
        rogue.reeled is None
        and rogue.animated
        and isinstance(rogue.locomotion.upper, type(rogue.weapon))
    )
    assert abs(rogue.contact().x - mimic.position.x) > APPROACH + 20.0
    assert mimic.mode is Mode.CHEST, "the dagger is still in the air"
    assert run(world, 0.5, until=lambda: mimic.revealed)
    assert mimic.knife is None and mimic.damage == KNIFE_DAMAGE and mimic.exposures == 1
    assert mimic.camo_left > CAMO_COOLDOWN - 0.5 and mimic.chomps == 0
    assert rogue in world.stickmen and rogue.animated and not rogue.swallowed
    assert run(world, 1.0, until=lambda: mimic.mode is Mode.HUNT)
    assert mimic in world.monsters()
    assert run(world, 1.0, until=lambda: mimic.target is rogue), "and it fights him"


def test_a_rogue_exposes_it_again_each_time_it_baits_him():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    rogue = sturdy(world.add_stickman(Vec2(380, FLOOR), "rogue"))
    assert run(world, 12.0, until=lambda: mimic.exposures == 1)
    run(world, 1.0)
    mimic.camo_left = 0.0
    assert run(world, 6.0, until=lambda: mimic.mode is Mode.CHEST)
    assert run(world, 15.0, until=lambda: mimic.exposures == 2), "baited and exposed again"
    assert mimic.lures == 2 and mimic.chomps == 0 and rogue.animated


def test_a_baited_adventurer_hurries_at_half_again_his_pace():
    assert LURE_HASTE == 1.5
    world = world_with()
    mimic = world.add_mimic(Vec2(900, FLOOR))
    baited = world.add_stickman(Vec2(200, FLOOR), "barbarian")
    control_world = world_with()
    control = control_world.add_stickman(Vec2(200, FLOOR), "barbarian")
    assert run(world, 1.0, until=lambda: baited.lure is mimic)

    def walk(stickman: Stickman, w: SimWorld, goal: float) -> float:
        start = stickman.follower.current_anchor()
        target = stickman.planner.anchor_near(Vec2(goal, FLOOR), 3.0, walk_only=True)
        stickman.follower.reset(start)
        stickman.follower.set_route(stickman.planner.plan(start, target))
        before = stickman.contact().x
        run(w, 1.0)
        return stickman.contact().x - before

    pace = walk(control, control_world, 900)
    before = baited.contact().x
    run(world, 1.0)
    assert baited.lure is mimic
    assert abs((baited.contact().x - before) / pace - 1.5) < 0.12, "1.5x while baited"
    mimic._unbait(baited, ignore=True)
    assert baited.lure is None
    assert abs(walk(baited, world, 1100) / pace - 1.0) < 0.12, "back to his pace"


def test_a_swallow_lets_go_if_the_mimic_dies_or_leaves():
    for ending in ("dies", "leaves"):
        world = world_with()
        mimic = world.add_mimic(Vec2(500, FLOOR))
        hero = world.add_stickman(Vec2(420, FLOOR), "paladin")
        assert run(world, 12.0, until=lambda h=hero, m=mimic: h.reeled is m)
        run(world, REEL_TIME * 0.5)
        if ending == "dies":
            mimic.die(mimic.center(), Vec2(0, 0))
        else:
            world.mimics.remove(mimic)
            mimic.let_go()
        run(world, STEP * 2)
        assert hero.reeled is None and mimic.caught is None and mimic.tongue_tip is None
        assert hero in world.stickmen and hero.damage == 0
        assert run(world, 3.0, until=lambda h=hero: h.animated), "he gets back up"


def test_an_adventurer_who_cannot_get_there_is_skipped():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    near = world.add_stickman(Vec2(420, FLOOR), "barbarian")
    far = world.add_stickman(Vec2(800, FLOOR), "rogue")
    planner = world.planner

    class Nowhere:
        def __getattr__(self, name):
            return getattr(planner, name)

        def plan(self, start, goal):
            return None

    class Stuck(Stickman):
        planner = property(lambda self: Nowhere())

    near.__class__ = Stuck
    assert run(world, 1.0, until=lambda: far.lure is not None)
    assert near.lure is None and mimic.baited == [far]


def test_with_a_full_bait_it_swaps_the_farthest_for_a_clearly_nearer_one_never_a_thrall():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    thrall = world.add_stickman(Vec2(470, FLOOR), "barbarian")
    thrall.enthrall()
    marks = [world.add_stickman(Vec2(x, FLOOR), "rogue") for x in (1000, 1080, 1150)]
    assert run(world, 1.0, until=lambda: len(mimic.baited) == 3)
    assert thrall.lure is None
    newcomer = world.add_stickman(Vec2(560, FLOOR), "ranger")
    assert run(world, 1.0, until=lambda: newcomer.lure is not None)
    farthest = max(marks, key=lambda s: s.contact().x)
    assert farthest.lure is None and newcomer in mimic.baited and len(mimic.baited) == 3
    assert not run(world, 10.0, until=lambda: thrall.lure is not None)


def test_it_baits_the_three_nearest_at_once_and_lets_the_rest_go_to_fight_it(monkeypatch):
    deaths = record_deaths(monkeypatch)
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    first = world.add_stickman(Vec2(400, FLOOR), "barbarian")
    second = world.add_stickman(Vec2(640, FLOOR), "paladin")
    third = world.add_stickman(Vec2(260, FLOOR), "cleric")
    fourth = world.add_stickman(Vec2(1100, FLOOR), "wizard")
    assert run(world, 1.0, until=lambda: len(mimic.baited) == 3)
    assert set(mimic.baited) == {first, second, third} and fourth.lure is None
    assert all(s.lure is mimic and s.lure_age >= 0.0 for s in (first, second, third))
    assert run(world, 10.0, until=lambda: mimic.mode is Mode.OPEN)
    assert mimic.victim is first and first not in mimic.baited
    assert run(world, 6.0, until=lambda: mimic.revealed)
    assert deaths == [("mimic", "Swallowed whole by a mimic!")] and first.swallowed
    assert not mimic.baited and second.lure is None and third.lure is None
    assert mimic.chomps == 1 and mimic.lures == 3
    for s in (second, third):
        assert s.animated and s.reeled is None and s.locomotion.upper is s.weapon
        assert abs(s.contact().x - mimic.position.x) < 120.0, "right there"
    mimic.camo_left = 1e9
    assert run(world, 6.0, until=lambda: mimic.damage > 0), "and they fight it"


def test_a_second_mark_who_arrives_mid_swallow_is_let_go_not_opening_it():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    first = world.add_stickman(Vec2(440, FLOOR), "barbarian")
    second = world.add_stickman(Vec2(600, FLOOR), "paladin")
    assert run(world, 1.0, until=lambda: len(mimic.baited) == 2)
    assert run(world, 10.0, until=lambda: mimic.mode is Mode.OPEN)
    assert mimic.victim is first
    assert run(world, 6.0, until=lambda: second.lure is None)
    assert mimic.mode is Mode.OPEN and mimic.victim in (first, None), "he never opens it"
    assert not isinstance(second.locomotion.upper, Fumble)
    assert run(world, 6.0, until=lambda: mimic.revealed) and second.lure is None


def test_a_rogues_reveal_lets_the_other_marks_go_too():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    rogue = world.add_stickman(Vec2(420, FLOOR), "rogue")
    other = world.add_stickman(Vec2(900, FLOOR), "barbarian")
    assert run(world, 1.0, until=lambda: len(mimic.baited) == 2)
    assert run(world, 10.0, until=lambda: mimic.spotter is rogue)
    assert other.lure is mimic, "still on his way"
    assert run(world, 2.0, until=lambda: mimic.revealed)
    assert other.lure is None and not mimic.baited and other.animated and not other.swallowed
    assert mimic.chomps == 0 and mimic.exposures == 1


def test_a_mark_who_dies_on_the_way_is_dropped():
    world = world_with()
    mimic = world.add_mimic(Vec2(500, FLOOR))
    a = world.add_stickman(Vec2(200, FLOOR), "barbarian")
    b = world.add_stickman(Vec2(900, FLOOR), "wizard")
    assert run(world, 1.0, until=lambda: len(mimic.baited) == 2)
    b.hurt(b.hp + 10, b.center(), Vec2(0, 0), "test", "test")
    run(world, 0.1)
    assert mimic.baited == [a] and a.lure is mimic


def watch_chomps(monkeypatch, mimic: Mimic) -> list[tuple[float, int, bool]]:
    """Every chomp on an adventurer: (sim time, damage, whether its jaws reached him)."""
    hits = []
    hurt = Stickman.hurt

    def checked(self, amount, point, push, source, death, bleed=True):
        if source == "mimic":
            hits.append((mimic.time, amount, mimic._reaches(self)))
        return hurt(self, amount, point, push, source, death, bleed)

    monkeypatch.setattr(Stickman, "hurt", checked)
    return hits


def sturdy(hero: Stickman) -> Stickman:
    hero.cooldown = 1e9
    hero.damage = -100
    return hero


def test_revealed_it_is_a_monster_that_leap_chomps_from_mid_range(monkeypatch):
    world = world_with()
    mimic = revealed(world, world.add_mimic(Vec2(300, FLOOR)))
    assert mimic in world.monsters() and world.monster_at(mimic.center()) is mimic
    assert world.closest_part(mimic, Vec2(0, FLOOR)) is not None
    hits = watch_chomps(monkeypatch, mimic)
    hero = sturdy(world.add_stickman(Vec2(410, FLOOR), "paladin"))
    run(world, 0.4, until=lambda: mimic.pending is not None)
    pending = mimic.pending
    assert pending is not None and not pending.hop
    assert pending.start.distance_to(pending.target.point) > HOP_RANGE
    assert run(world, 1.0, until=lambda: mimic.leap is not None)
    assert run(world, 1.0, until=lambda: hits)
    assert hits[0][1:] == (LEAP_DAMAGE, True) and mimic.leap is not None, "a chomp in mid-air"
    assert run(world, 1.0, until=lambda: mimic.attack == "land")
    gap = abs(mimic.center().x - hero.center().x)
    assert gap > 8.0, "it doesn't land on top of its foe"


def test_up_close_it_hop_chomps(monkeypatch):
    world = world_with()
    mimic = revealed(world, world.add_mimic(Vec2(300, FLOOR)))
    hits = watch_chomps(monkeypatch, mimic)
    sturdy(world.add_stickman(Vec2(335, FLOOR), "rogue"))
    run(world, 0.4, until=lambda: mimic.pending is not None)
    assert mimic.pending is not None and mimic.pending.hop
    assert run(world, 1.0, until=lambda: hits)
    assert hits[0][1:] == (LEAP_DAMAGE, True)


def test_its_chomps_wait_out_a_cooldown_and_never_bite_air(monkeypatch):
    world = world_with(Rect(500, 560, 200, 140))
    mimic = revealed(world, world.add_mimic(Vec2(300, FLOOR)))
    hits = watch_chomps(monkeypatch, mimic)
    hero = sturdy(world.add_stickman(Vec2(420, FLOOR), "barbarian"))
    run(world, 12.0)
    assert len(hits) >= 3 and all(amount == LEAP_DAMAGE and reached for _, amount, reached in hits)
    times = [t for t, _, _ in hits]
    assert min(b - a for a, b in zip(times, times[1:], strict=False)) >= LEAP_COOLDOWN
    assert mimic.leaps >= mimic.bites == len(hits) and hero.prey


def test_it_never_hunts_thralls():
    world = world_with()
    mimic = revealed(world, world.add_mimic(Vec2(300, FLOOR)))
    thrall = world.add_stickman(Vec2(340, FLOOR), "barbarian")
    thrall.enthrall()
    far = world.add_stickman(Vec2(560, FLOOR), "rogue")
    far.enthrall()
    run(world, 2.0)
    assert mimic.target is None and mimic.bites == mimic.leaps == 0
    assert far.reeled is None and thrall.reeled is None


def hunter(world: SimWorld, x: float, y: float = FLOOR) -> Mimic:
    mimic = revealed(world, world.add_mimic(Vec2(x, y)))
    mimic.camo_left = 1e9
    return mimic


def walk_to(world: SimWorld, mimic: Mimic, anchor: Anchor, seconds: float, each=None) -> None:
    assert mimic._route_to(anchor)
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()
        if not mimic.follower.moving and not mimic.airborne:
            return


def test_on_floors_it_hops_without_legs():
    world = world_with()
    mimic = hunter(world, 200)
    heights, slid = [], []
    last = mimic.position

    def watch():
        nonlocal last
        assert mimic.legs == 0.0
        heights.append(FLOOR - mimic.position.y)
        if mimic.hop is None and mimic.follower.step is not None:
            slid.append(abs(mimic.position.x - last.x))
        last = mimic.position

    walk_to(world, mimic, Anchor(mimic.support, Vec2(500, FLOOR)), 8.0, watch)
    assert abs(mimic.position.x - 500) < 1.0 and mimic.position.y == FLOOR
    assert max(heights) > 10.0, "it hops up off the floor"
    assert sum(slid) <= HOP_SLIDE * 2, "no walking in place: it only moves in the air"
    assert mimic.hop is None and mimic.legs == 0.0


def test_it_sprouts_legs_to_climb_and_folds_them_away_back_on_top():
    world = world_with(Rect(500, 450, 260, 170))
    mimic = hunter(world, 440)
    planner = world.mimic_planner
    wall = next(s for s in planner.surfaces if s.kind is SurfaceKind.LEFT and s.box == 0)
    under = next(s for s in planner.surfaces if s.kind is SurfaceKind.CEILING and s.box == 0)
    top = next(s for s in planner.surfaces if s.kind is SurfaceKind.TOP and s.box == 0)
    prev = {"center": mimic.center(), "up": mimic.up}
    jumps = []

    def smooth():
        jumps.append((mimic.center().distance_to(prev["center"]), mimic.up.distance_to(prev["up"])))
        prev["center"], prev["up"] = mimic.center(), mimic.up

    walk_to(world, mimic, Anchor(wall, wall.point_at(560.0)), 4.0, smooth)
    assert mimic.support is wall and mimic.legs == 1.0 and mimic.up.x < -0.99
    walk_to(world, mimic, Anchor(under, under.point_at(under.low + 60.0)), 4.0, smooth)
    assert mimic.support is under and mimic.legs == 1.0 and mimic.up.y > 0.99
    walk_to(world, mimic, Anchor(top, top.point_at(600.0)), 6.0, smooth)
    run(world, 0.5)
    assert mimic.support is top and mimic.legs == 0.0
    walk_to(world, mimic, Anchor(planner.surfaces[0], Vec2(380, FLOOR)), 6.0, smooth)
    run(world, 0.5)
    assert mimic.support is planner.surfaces[0] and mimic.legs == 0.0
    assert max(c for c, _ in jumps) < 12.0 and max(u for _, u in jumps) < 0.25, "no pops"


def test_mounting_a_wall_it_pivots_round_its_front_feet():
    world = world_with(Rect(500, 450, 260, 170))
    mimic = hunter(world, 470)
    wall = next(
        s for s in world.mimic_planner.surfaces if s.kind is SurfaceKind.LEFT and s.box == 0
    )
    seen = []

    def watch():
        step = mimic.follower.step
        if step is not None and step.surface is wall and not step.from_surface.wall:
            on_wall = [
                leg
                for leg in mimic.rig.legs
                if leg.planted and abs(leg.foot.x - wall.start.x) < 0.5
            ]
            seen.append((mimic._progress(), mimic.legs, on_wall, mimic.up))

    walk_to(world, mimic, Anchor(wall, wall.point_at(560.0)), 4.0, watch)
    assert seen and seen[0][1] == 0.0, "legs burst out mid-air"
    before = [legs for t, _, legs, _ in seen if t < MOUNT_HOP]
    assert any(before), "its front feet plant on the wall before it pivots"
    assert all(leg.side == 1 for legs in before for leg in legs), "only the front feet"
    hopping = [up for t, _, _, up in seen if t < MOUNT_HOP]
    assert hopping and all(up.y < -0.99 for up in hopping), "upright until it pivots"
    assert all(not any(b.contains(mimic.center()) for b in world.boxes) for _ in seen)


def test_its_legs_step_on_ik_planted_feet_in_alternating_groups():
    world = world_with(Rect(500, 450, 260, 170))
    mimic = hunter(world, 440)
    planner = world.mimic_planner
    wall = next(s for s in planner.surfaces if s.kind is SurfaceKind.LEFT and s.box == 0)
    under = next(s for s in planner.surfaces if s.kind is SurfaceKind.CEILING and s.box == 0)
    rig = mimic.rig
    last: dict[int, tuple] = {}
    worst = {"drift": 0.0, "jump": 0.0, "flips": 0, "up": 0, "stretch": 0.0, "mixed": 0}
    frames = []

    def watch():
        if mimic.legs < 1.0:
            last.clear()
            return
        frames.append(mimic.time)
        stepping = [leg for leg in rig.legs if leg.stepping]
        worst["up"] = max(worst["up"], len(stepping))
        worst["mixed"] += len({leg.group for leg in stepping}) > 1
        x_axis = Vec2(-mimic.up.y, mimic.up.x)
        for i, leg in enumerate(rig.legs):
            reach, knee = leg.foot - leg.hip, leg.knee - leg.hip
            bend = reach.dot(x_axis) * knee.dot(mimic.up) - reach.dot(mimic.up) * knee.dot(x_axis)
            worst["stretch"] = max(worst["stretch"], reach.length() / REACH)
            if i in last:
                foot, was_planted, was_bend = last[i]
                moved = leg.foot.distance_to(foot)
                worst["jump"] = max(worst["jump"], moved)
                if was_planted and leg.planted:
                    worst["drift"] = max(worst["drift"], moved)
                if abs(bend) > 2.0 and abs(was_bend) > 2.0 and bend * was_bend < 0.0:
                    worst["flips"] += 1
            last[i] = (leg.foot, leg.planted and not leg.stepping, bend)

    steps = rig.steps
    walk_to(world, mimic, Anchor(wall, wall.point_at(470.0)), 6.0, watch)
    walk_to(world, mimic, Anchor(under, under.point_at(under.low + 150.0)), 6.0, watch)
    assert mimic.support is under
    assert rig.steps - steps > 60, "it walks on its legs, a step at a time"
    assert worst["drift"] == 0.0, "a planted foot stays put"
    assert worst["flips"] == 0, "knees never flip"
    assert worst["jump"] < 7.0, "no foot teleports"
    assert worst["up"] <= MAX_STEPPING and worst["stretch"] < 1.1
    assert worst["mixed"] < 0.2 * len(frames), "the two groups take turns"
    assert rig.forced < 0.1 * (rig.steps - steps)
    run(world, 0.4)
    assert all(leg.planted for leg in rig.legs), "standing still, every foot planted"
    assert all(abs(leg.foot.y - under.start.y) < 0.5 for leg in rig.legs if leg.planted)
    lifted = rig.legs[0]
    rig._lift(lifted, lifted.foot + Vec2(4, 0))
    feet = [leg.foot for leg in rig.legs]
    landing = lifted.step_to
    world.boxes[0] = Rect(530, 430, 260, 170)
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}))
    assert mimic.support is not None and not mimic.support.walkable
    moved = [leg.foot - foot for leg, foot in zip(rig.legs, feet, strict=True)]
    assert all(m.distance_to(Vec2(30, -20)) < 1e-6 for m in moved), "its feet ride the window"
    assert lifted.step_to.distance_to(landing + Vec2(30, -20)) < 1e-6


def test_it_disguises_again_after_the_cooldown_off_walls_first():
    world = world_with(Rect(500, 400, 300, 200))
    mimic = revealed(world, world.add_mimic(Vec2(650, 400)))
    assert mimic.camo_left > CAMO_COOLDOWN - 1.0
    wall = next(
        s for s in world.mimic_planner.surfaces if s.kind is SurfaceKind.LEFT and s.box == 0
    )
    mimic._attach(Anchor(wall, wall.point_at((wall.low + wall.high) / 2)))
    mimic.camo_left = 0.0
    assert run(world, 6.0, until=lambda: mimic.mode is Mode.HIDE)
    assert mimic.support is not None and mimic.support.walkable
    assert mimic in world.monsters()
    assert run(world, 1.0, until=lambda: mimic.mode is Mode.CHEST)
    assert mimic not in world.monsters() and mimic.rise == 0.0 and mimic.yaw == FRONT
    hero = world.add_stickman(mimic.position + Vec2(150, 0), "cleric")
    run(world, LURE_DELAY * 0.5)
    assert hero.lure is None
    assert run(world, LURE_DELAY, until=lambda: hero.lure is mimic)


def test_fighters_lose_interest_when_it_disguises():
    world = world_with()
    mimic = revealed(world, world.add_mimic(Vec2(300, FLOOR)))
    hero = world.add_stickman(Vec2(360, FLOOR), "barbarian", wander=True)
    run(world, 1.0)
    mimic.camo_left = 0.0
    assert run(world, 3.0, until=lambda: mimic.mode is Mode.CHEST)
    damage = mimic.damage
    run(world, 1.0)
    assert hero.quarry is not mimic and mimic.damage == damage


def test_a_closing_window_drops_it_safely_in_either_form():
    for reveal in (False, True):
        world = world_with(Rect(400, 450, 300, 150))
        mimic = world.add_mimic(Vec2(550, 450))
        if reveal:
            revealed(world, mimic)
            mimic.camo_left = 1e9
        world.apply_terrain(TerrainChange(remap={0: None}), [])
        assert run(world, 2.0, until=lambda m=mimic: m.follower is not None)
        assert abs(mimic.position.y - FLOOR) < 1.0 and mimic.support.walkable
        assert mimic.mode is (Mode.HUNT if reveal else Mode.CHEST)


def test_it_rides_a_moving_window():
    world = world_with(Rect(400, 450, 300, 150))
    mimic = world.add_mimic(Vec2(550, 450))
    x = mimic.position.x
    world.boxes[0] = Rect(440, 420, 300, 150)
    world.apply_terrain(TerrainChange(moves={0: Vec2(40, -30)}))
    assert mimic.position == Vec2(x + 40, 420) and mimic.follower is not None


def test_it_follows_the_hydra_in_the_desktop_rotation_and_fills_the_health_bar():
    assert (
        DEFENDERS[3:5] == ("hydra", "mimic")
        and DEFENDER_BARS["mimic"][0] == "Mimic"
    )
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(400, 400, 400, 200))])
    session = DesktopSession(screen, usable, source, seed=2, max_stickmen=0)
    session.rotate()  # past the chimera
    session.rotate()  # past the drow
    session.rotate()  # past the drake riders
    session.rotate()
    assert session.defender == "mimic" and len(session.mimics) == 1 and not session.hydras
    mimic = session.mimics[0]
    assert mimic.position.y == 400
    assert session.live_monsters == [mimic] and session.defender_health == 1.0
    assert not session.hurt_monster(mimic, 1, mimic.center(), Vec2(0, 0))
    revealed(session, mimic)
    session.hurt_monster(mimic, 1, mimic.center(), Vec2(0, 0))
    assert abs(session.defender_health - (MIMIC_HP - 1) / MIMIC_HP) < 1e-9
    session.hurt_monster(mimic, MIMIC_HP, mimic.center(), Vec2(0, -40))
    run(session, 0.1)
    assert session.defender == "lich" and not session.mimics


def test_it_dies_spilling_coins_and_fades():
    world = world_with()
    mimic = revealed(world, world.add_mimic(Vec2(300, FLOOR)))
    assert world.hurt_monster(mimic, MIMIC_HP, mimic.center(), Vec2(50, -40))
    assert mimic.dead and mimic in world.fallen and mimic not in world.monsters()
    assert len(mimic.coins) > 0
    run(world, 1.0)
    assert mimic.crumple == 1.0 and mimic.jaw > 0.8
    assert all(coin.y >= 0.0 for coin in mimic.coins)
    run(world, mimic.linger + 1.5)
    assert mimic not in world.fallen and world.monster_kills == 1


def test_it_draws_in_every_form():
    QGuiApplication.instance() or QGuiApplication([])
    world = world_with(Rect(400, 450, 300, 150))
    mimic = world.add_mimic(Vec2(300, FLOOR))
    hero = world.add_stickman(Vec2(150, FLOOR), "barbarian")
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    for _ in range(40):
        run(world, 0.25)
        draw_mimic(painter, mimic, QColor(0, 0, 0))
        draw_lure_alert(painter, hero.center(), 4.5, 0.2)
    assert mimic.scales() == (1.0, 0.0) or mimic.mode is not Mode.CHEST
    mimic.yaw = math.pi / 3
    mimic.rise = 0.5
    draw_mimic(painter, mimic)
    revealed(world, mimic)
    assert mimic.scales()[0] == 0.0 and abs(abs(mimic.scales()[1]) - 1.0) < 1e-6
    for yaw in (0.0, 1.2, math.pi / 2, 2.0, math.pi):
        mimic.yaw = yaw
        draw_mimic(painter, mimic, QColor(0, 0, 0))
    mimic.jaw, mimic.crouch, mimic.tuck = 1.0, 0.6, 1.0
    draw_mimic(painter, mimic, QColor(0, 0, 0))
    mimic.legs, mimic.bounce, mimic.dust, mimic.gulp = 0.5, -0.8, 0.1, 0.5
    mimic.tongue_tip = mimic.mouth() + Vec2(120, -10)
    draw_mimic(painter, mimic, QColor(0, 0, 0))
    mimic.caught = hero
    draw_mimic(painter, mimic, QColor(0, 0, 0))
    mimic.knife = Knife(Vec2(250, 690), Vec2(270, 685), spin=1.0)
    draw_mimic(painter, mimic, QColor(0, 0, 0))
    painter.end()
