from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.adventurers.actor import GOBLIN_DAMAGE, StickMode
from dungeons_desktops.game.adventurers.model import BASE_HP
from dungeons_desktops.game.defenders.goblins.actor import (
    REGROUP_BOOST,
    SPEAR_MAX_ARC,
    SWORD_START_REACH,
    Goblin,
)
from dungeons_desktops.game.defenders.goblins.weapons import GoblinSword
from dungeons_desktops.game.effects.ballistics import GRAVITY, lob_velocity
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1.0 / 60.0


def run(controller: RigPreviewController, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        controller.advance(DT)


def scene(goblin_x: float, stickman_x: float) -> tuple[RigPreviewController, Goblin]:
    controller = RigPreviewController(1000, 600)
    controller.boxes.clear()
    controller._terrain_changed(moved_box=None, delta=Vec2(0.0, 0.0))
    hero = controller.selected
    anchor = controller.planner.anchor_near(Vec2(stickman_x, controller.floor_y))
    hero.follower.reset(anchor)
    hero.locomotion.teleport(hero.follower.command())
    goblin = controller.add_goblin(Vec2(goblin_x, controller.floor_y - 5))
    return controller, goblin


def test_lob_lands_on_a_still_target():
    origin, target = Vec2(100, 400), Vec2(300, 450)
    velocity = lob_velocity(origin, target, Vec2(0, 0), [], floor_y=1000.0)
    flight = (target.x - origin.x) / velocity.x
    landing = origin + velocity * flight + Vec2(0.0, 0.5 * GRAVITY * flight * flight)
    assert landing.distance_to(target) < 1e-6


def test_lob_arcs_over_a_wall_in_the_way():
    wall = Rect(180, 300, 20, 200)
    origin, target = Vec2(100, 480), Vec2(300, 480)
    velocity = lob_velocity(origin, target, Vec2(0, 0), [wall], floor_y=500.0)
    flight = (target.x - origin.x) / velocity.x
    for i in range(1, 50):
        t = flight * i / 50
        point = origin + velocity * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
        assert not wall.contains(point)


def world_with(boxes=(), seed=3) -> SimWorld:
    return SimWorld(list(boxes), 700.0, 1200.0, ceiling=20.0, seed=seed)


def test_a_pack_is_a_standard_bearer_three_swords_and_two_spears():
    world = world_with()
    kinds = [world.add_goblin(Vec2(200 + 15 * i, 700)).kind for i in range(7)]
    pack = kinds[:6]
    assert (pack.count("flag"), pack.count("sword"), pack.count("spear")) == (1, 3, 2)
    assert kinds[6] == kinds[0]


def test_a_stickman_takes_four_goblin_hits_to_kill():
    world = world_with()
    stickman = world.add_stickman(Vec2(500, 700))
    assert stickman.hp == BASE_HP == 4

    def hit():
        return stickman.hurt(GOBLIN_DAMAGE, stickman.center(), Vec2(100, -50), "goblin", "dead")

    for _ in range(BASE_HP - 1):
        assert not hit()
    assert stickman.animated and world.kills == 0
    assert hit()
    assert stickman.mode is StickMode.RAGDOLL and world.kills == 1
    assert world.gore.drops


def test_the_pack_runs_down_the_same_stickman_together():
    world = world_with()
    for i in range(3):
        world.add_goblin(Vec2(150 + 12 * i, 700))
    quarry = world.add_stickman(Vec2(800, 700))
    start = [g.contact().distance_to(quarry.contact()) for g in world.goblins]
    run(world, 3.0)
    assert all(g.target is quarry for g in world.goblins)
    now = [g.contact().distance_to(quarry.contact()) for g in world.goblins]
    assert all(b < a - 100 for a, b in zip(start, now, strict=True))


def test_sword_goblin_cuts_a_stickman_down_in_four_hits():
    world = world_with()
    world.add_goblin(Vec2(300, 700), "sword")
    quarry = world.add_stickman(Vec2(450, 700))
    for _ in range(int(15 / DT)):
        world.advance(DT)
        if not quarry.animated:
            break
    assert quarry.mode is StickMode.RAGDOLL
    assert quarry.damage == BASE_HP and world.kills == 1


def test_sword_goblin_runs_down_and_hits_a_stickman_walking_away(monkeypatch):
    swings = []
    start = GoblinSword.start
    monkeypatch.setattr(GoblinSword, "start", lambda self: swings.append(1) or start(self))
    world = world_with()
    world.add_goblin(Vec2(300, 700), "sword")
    quarry = world.add_stickman(Vec2(360, 700))
    quarry.wander = False
    quarry.set_goal(Vec2(1150, 700))
    for _ in range(int(8 / DT)):
        world.advance(DT)
        if not quarry.animated:
            break
    assert quarry.damage >= 2
    assert quarry.damage >= 0.7 * len(swings)


def test_spears_fly_flat():
    world = world_with()
    world.add_goblin(Vec2(300, 700), "spear")
    world.add_stickman(Vec2(500, 700)).wander = False
    peak = 700.0
    for _ in range(int(6 / DT)):
        world.advance(DT)
        for spear in world.spears.spears:
            peak = min(peak, spear.position.y)
    assert world.spears.spears and 700.0 - peak < SPEAR_MAX_ARC + 30


def test_spear_goblin_throws_from_range_and_wounds():
    world = world_with()
    thrower = world.add_goblin(Vec2(300, 700), "spear")
    quarry = world.add_stickman(Vec2(450, 700))
    thrown = False
    for _ in range(int(10 / DT)):
        world.advance(DT)
        thrown |= bool(world.spears.spears)
        if quarry.damage:
            break
    assert thrown and quarry.damage >= 1
    assert thrower.contact().distance_to(quarry.contact()) > 30


def test_flag_bearer_follows_but_never_attacks():
    world = world_with()
    bearer = world.add_goblin(Vec2(300, 700), "flag")
    quarry = world.add_stickman(Vec2(420, 700))
    run(world, 6.0)
    assert quarry.animated and quarry.damage == 0
    assert bearer.contact().distance_to(quarry.contact()) < 60
    assert not world.spears.spears


def test_the_pack_climbs_up_to_a_stickman_on_a_window():
    box = Rect(500, 450, 300, 250)
    world = world_with([box])
    for i in range(3):
        world.add_goblin(Vec2(150 + 12 * i, 700))
    quarry = world.add_stickman(Vec2(650, box.top))
    modes = set()
    for _ in range(int(40 / DT)):
        world.advance(DT)
        modes |= {g.locomotion.mode for g in world.goblins}
        if not quarry.animated:
            break
    assert PoseMode.CLIMB in modes
    assert quarry.mode is StickMode.RAGDOLL and world.kills == 1


def test_downed_stickman_fades_out_and_despawns():
    controller, _ = scene(goblin_x=300, stickman_x=500)
    other = controller.add_stickman(Vec2(950, controller.floor_y))
    hero = controller.selected
    controller.goblins.clear()
    hero.go_ragdoll()

    run(controller, 2.0)
    assert hero in controller.stickmen and hero.fade == 0.0
    run(controller, 0.8)
    assert 0.0 < hero.fade <= 1.0 or hero not in controller.stickmen
    run(controller, 0.5)

    assert hero not in controller.stickmen
    assert controller.selected is other
    assert other.animated and other.locomotion.mode is PoseMode.WALK


def test_last_stickman_despawning_brings_a_new_one():
    controller, _ = scene(goblin_x=300, stickman_x=500)
    hero = controller.selected
    hero.go_ragdoll()
    controller.goblins.clear()
    run(controller, 3.5)

    assert hero not in controller.stickmen
    assert len(controller.stickmen) == 1
    assert controller.selected.animated


def test_dragging_a_goblin_drops_it_on_the_surface_below():
    controller = RigPreviewController(1000, 600)
    goblin = controller.add_goblin(Vec2(30, controller.floor_y - 5))
    controller.stickmen.clear()
    run(controller, 0.3)
    box = controller.boxes[1]

    controller.press(goblin.center())
    assert goblin.held
    drop_at = Vec2(box.x + 50, box.top - 60)
    controller.drag(drop_at)
    run(controller, 0.2)
    controller.drop(drop_at)
    assert not goblin.held
    assert goblin.contact().y == box.top
    assert abs(goblin.contact().x - (box.x + 50)) < 1.0


def test_goblin_rides_a_dragged_box():
    controller = RigPreviewController(1000, 600)
    box = controller.boxes[0]
    goblin = controller.add_goblin(Vec2(box.x + 75, box.top - 5))
    controller.stickmen.clear()
    run(controller, 0.2)
    before = goblin.contact()

    controller.press(Vec2(box.x + 140, box.top + 80))
    controller.drag(Vec2(box.x + 180, box.top + 60))
    controller.drop()

    assert goblin.contact().y == before.y - 20
    assert abs(goblin.contact().x - (before.x + 40)) < 1.0


def still(stickman):
    stickman.update = lambda dt: None
    return stickman


def test_with_the_flag_up_the_whole_band_hunts_whoever_is_nearest_the_flag():
    world = world_with()
    sword = world.add_goblin(Vec2(150, 700), "sword")
    flag = world.add_goblin(Vec2(900, 700), "flag")
    near_sword = still(world.add_stickman(Vec2(250, 700)))
    near_flag = still(world.add_stickman(Vec2(1050, 700)))
    run(world, 0.5)
    assert world.goblin_pack.target is near_flag
    assert sword.target is near_flag and flag.target is near_flag
    assert near_sword is not near_flag


def test_with_the_flag_down_each_goblin_hunts_its_nearest():
    world = world_with()
    left = world.add_goblin(Vec2(150, 700), "sword")
    right = world.add_goblin(Vec2(1000, 700), "spear")
    flag = world.add_goblin(Vec2(600, 700), "flag")
    near_left = still(world.add_stickman(Vec2(260, 700)))
    near_right = still(world.add_stickman(Vec2(1120, 700)))
    world.hurt_monster(flag, flag.max_hp, flag.center(), Vec2(0.0, 0.0))
    run(world, 0.5)
    assert world.goblin_pack.flag is None and world.goblin_pack.target is None
    assert left.target is near_left and right.target is near_right


def test_goblins_heading_for_the_flag_speed_up():
    world = world_with()
    sword = world.add_goblin(Vec2(150, 700), "sword")
    flag = world.add_goblin(Vec2(900, 700), "flag")
    sword.velocity = Vec2(100.0, 0.0)
    assert sword._regroup_pace() == REGROUP_BOOST
    sword.velocity = Vec2(-100.0, 0.0)
    assert sword._regroup_pace() == 1.0
    assert flag._regroup_pace() == 1.0
    world.hurt_monster(flag, flag.max_hp, flag.center(), Vec2(0.0, 0.0))
    sword.velocity = Vec2(100.0, 0.0)
    assert sword._regroup_pace() == 1.0


def put(world: SimWorld, stickman, x: float) -> None:
    stickman.follower.reset(world.planner.anchor_near(Vec2(x, 700)))


def test_the_band_turns_as_soon_as_the_flag_is_clearly_nearer_someone_else():
    world = world_with()
    swords = [world.add_goblin(Vec2(80 + 12 * i, 700), "sword") for i in range(3)]
    flag = world.add_goblin(Vec2(500, 700), "flag")
    flag.update = lambda dt: None
    first = still(world.add_stickman(Vec2(560, 700)))
    second = still(world.add_stickman(Vec2(430, 700)))
    pack = world.goblin_pack
    run(world, 0.5)
    assert pack.target is first

    put(world, first, 575)
    run(world, 2.0)
    assert pack.target is first, "a near tie mustn't flip the band over"

    put(world, first, 650)
    run(world, 0.5)
    assert pack.target is second
    assert all(g.target is second for g in swords)


def test_the_band_follows_the_flag_when_it_is_carried_off():
    world = world_with()
    swords = [world.add_goblin(Vec2(150 + 12 * i, 700), "sword") for i in range(4)]
    flag = world.add_goblin(Vec2(200, 700), "flag")
    near_band = still(world.add_stickman(Vec2(300, 700)))
    far_off = still(world.add_stickman(Vec2(1000, 700)))
    run(world, 0.5)
    assert world.goblin_pack.target is near_band

    flag.pick_up(flag.center())
    flag.hold_at(Vec2(990, 650))
    run(world, 0.5)
    assert all(g.target is far_off for g in swords)
    flag.place(Vec2(990, 650))
    run(world, 1.0)
    assert all(g.target is far_off for g in world.goblins)


def test_the_band_spreads_around_its_quarry_and_the_swords_still_land_blows(monkeypatch):
    world = world_with()
    for i in range(11):
        world.add_goblin(Vec2(200 + 12 * i, 700))
    quarry = still(world.add_stickman(Vec2(800, 700)))
    hits = []
    quarry.hurt = lambda *args: hits.append(1) or False
    strikers = set()
    resolve = Goblin._resolve_attack

    def resolve_attack(self):
        before = len(hits)
        resolve(self)
        if len(hits) > before:
            strikers.add(self)

    monkeypatch.setattr(Goblin, "_resolve_attack", resolve_attack)
    run(world, 8.0)
    crowded = 0
    frames = int(6.0 / DT)
    for _ in range(frames):
        world.advance(DT)
        points = [g.contact() for g in world.goblins]
        crowded += any(
            a.distance_to(b) < 4.0 for i, a in enumerate(points) for b in points[i + 1 :]
        )
    assert crowded < 0.1 * frames
    swords = [g for g in world.goblins if g.kind == "sword"]
    assert len(swords) == 6
    assert len(strikers) >= 4 and strikers <= set(swords)
    assert sum(g._in_reach(quarry, SWORD_START_REACH) for g in swords) >= 4
