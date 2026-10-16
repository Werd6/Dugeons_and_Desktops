from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import (
    GOBLIN_SPACING,
    GOBLIN_SQUAD,
    TITLE_BAR,
    DesktopSession,
    to_local,
    to_world,
)
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord, WindowTracker
from dungeons_desktops.game.adventurers.actor import StickMode
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind

SCREEN = Rect(0, 0, 1400, 900)
USABLE = Rect(0, 30, 1400, 800)
STEP = 1 / 60


def session(records, **kwargs) -> tuple[DesktopSession, FakeWindowSource]:
    source = FakeWindowSource(records)
    options = {"defenders": ("goblins",), "goblin_squad": 1, **kwargs}
    return DesktopSession(SCREEN, USABLE, source, seed=5, **options), source


def run(world: DesktopSession, seconds: float) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)


# ----- tracker -------------------------------------------------------------


def test_tracker_reports_moves_removals_and_new_windows():
    tracker = WindowTracker(USABLE)
    first = tracker.update(
        [WindowRecord(10, Rect(100, 300, 300, 200)), WindowRecord(20, Rect(600, 400, 300, 200))]
    )
    assert first is not None and first.boxes == [Rect(100, 300, 300, 200), Rect(600, 400, 300, 200)]
    assert (
        tracker.update(
            [
                WindowRecord(10, Rect(100.4, 300, 300, 200)),
                WindowRecord(20, Rect(600, 400, 300, 200)),
            ]
        )
        is None
    )

    update = tracker.update(
        [WindowRecord(30, Rect(900, 200, 200, 150)), WindowRecord(20, Rect(650, 380, 300, 200))]
    )
    assert update is not None
    assert update.boxes == [Rect(650, 380, 300, 200), Rect(900, 200, 200, 150)]
    assert update.change.removed(0)
    assert update.change.new_index(1) == 0
    assert update.change.delta_for(1) == Vec2(50, -20)
    assert update.front_to_back == [1, 0]


def test_tracker_clips_to_the_usable_area_and_skips_tiny_windows():
    tracker = WindowTracker(USABLE)
    update = tracker.update(
        [WindowRecord(1, Rect(-50, 0, 400, 300)), WindowRecord(2, Rect(500, 500, 60, 30))]
    )
    assert update is not None
    assert update.boxes == [Rect(0, 30, 350, 270)]


# ----- terrain and actors ------------------------------------------------------


def test_screen_edges_are_climbable_walls_with_routes():
    world, _ = session([WindowRecord(1, Rect(500, 600, 300, 230))])
    walls = [s for s in world.surfaces if s.wall and s.box is None]
    assert {s.kind for s in walls} == {SurfaceKind.LEFT, SurfaceKind.RIGHT}
    assert {s.start.x for s in walls} == {USABLE.left, USABLE.right}
    start = world.planner.anchor_near(Vec2(700, USABLE.bottom), walk_only=True)
    for wall in walls:
        middle = wall.point_at((wall.low + wall.high) / 2)
        assert world.planner.plan(start, Anchor(wall, middle)) is not None


def test_actor_on_a_moved_window_is_carried_and_loses_support_when_it_closes():
    world, source = session([WindowRecord(1, Rect(400, 500, 400, 330))])
    world.goblins.clear()
    rider = world.add_stickman(Vec2(600, 495))
    bystander = world.add_stickman(Vec2(200, USABLE.bottom))
    assert rider.follower.current_anchor().surface.box == 0
    assert rider.contact().y == 500

    source.move(1, 40, -10)
    assert world.poll()
    assert rider.contact().distance_to(Vec2(640, 490)) < 1.0
    assert bystander.contact().distance_to(Vec2(200, USABLE.bottom)) < 1.0

    source.remove(1)
    assert world.poll()
    assert rider.mode is StickMode.RAGDOLL
    assert bystander.animated


def test_goblin_falls_when_its_window_closes():
    world, source = session(
        [WindowRecord(1, Rect(300, 400, 400, 200)), WindowRecord(2, Rect(900, 500, 300, 330))],
        max_stickmen=0,
    )
    goblin = world.goblin
    assert goblin.follower.current_anchor().surface.box == 0
    source.remove(1)
    world.poll()
    run(world, 1.6)
    assert goblin.contact().y == USABLE.bottom
    assert goblin.follower.current_anchor().surface.kind is SurfaceKind.FLOOR


# ----- session ---------------------------------------------------------------


def test_exactly_one_goblin_on_the_frontmost_window_top():
    front, back = Rect(700, 300, 400, 300), Rect(200, 500, 400, 330)
    world, _ = session([WindowRecord(7, front), WindowRecord(3, back)])
    assert len(world.goblins) == 1
    assert world.goblin.contact().y == front.top
    assert front.left <= world.goblin.contact().x <= front.right


def test_goblin_uses_the_floor_when_there_are_no_windows():
    world, _ = session([])
    assert len(world.goblins) == 1
    assert world.goblin.contact().y == USABLE.bottom


def test_goblin_war_band_musters_together_on_the_frontmost_window():
    windows = [Rect(100, 300, 300, 200), Rect(500, 350, 300, 200), Rect(900, 400, 300, 200)]
    records = [WindowRecord(i + 1, rect) for i, rect in enumerate(windows)]
    world, _ = session(records, goblin_squad=GOBLIN_SQUAD)
    kinds = [g.kind for g in world.goblins]
    assert (kinds.count("flag"), kinds.count("sword"), kinds.count("spear")) == (1, 6, 4)
    front = windows[world.front_to_back[0]]
    assert all(g.contact().y == front.top for g in world.goblins)
    xs = sorted(g.contact().x for g in world.goblins)
    assert (
        all(a < b for a, b in zip(xs, xs[1:], strict=False))
        and xs[-1] - xs[0] < GOBLIN_SPACING * GOBLIN_SQUAD
    )


def test_goblin_pack_musters_on_the_floor_when_no_window_top_fits_it():
    records = [WindowRecord(1, Rect(500, 350, 50, 200))]
    world, _ = session(records, goblin_squad=GOBLIN_SQUAD)
    assert len(world.goblins) == GOBLIN_SQUAD
    assert all(g.contact().y == world.floor_y for g in world.goblins)


def test_next_monster_now_rotates_through_every_defender_from_the_chimera():
    world = DesktopSession(SCREEN, USABLE, FakeWindowSource([]), seed=5, max_stickmen=0)
    assert world.defender == "chimera" and len(world.chimeras) == 1 and not world.lizards
    assert not world.elementals
    world.rotate()
    assert world.defender == "drow" and len(world.lizards) == 2 and not world.drakes
    assert not world.chimeras
    world.rotate()
    assert world.defender == "drakes" and len(world.drakes) == 3 and not world.hydras
    assert not world.lizards and not world.drow
    world.rotate()
    assert world.defender == "hydra" and len(world.hydras) == 1 and not world.mimics
    assert not world.drakes
    world.rotate()
    assert world.defender == "mimic" and len(world.mimics) == 1 and not world.liches
    assert not world.hydras
    world.rotate()
    assert world.defender == "lich" and len(world.liches) == 1 and not world.minotaurs
    assert not world.mimics
    world.rotate()
    assert world.defender == "minotaur" and len(world.minotaurs) == 1 and not world.displacers
    assert not world.liches
    world.rotate()
    assert world.defender == "displacer" and len(world.displacers) == 1 and not world.mindflayers
    assert not world.minotaurs
    world.rotate()
    assert world.defender == "mindflayer" and len(world.mindflayers) == 1 and not world.worms
    assert not world.displacers
    world.rotate()
    assert world.defender == "worm" and len(world.worms) == 1
    assert not world.goblins and not world.mindflayers
    world.rotate()
    assert world.defender == "goblins"
    assert len(world.goblins) == GOBLIN_SQUAD and not world.worms
    world.rotate()
    assert world.defender == "dragon" and len(world.dragons) == 1
    assert not world.goblins and not world.worms
    world.rotate()
    assert world.defender == "chimera" and len(world.chimeras) == 1
    assert not world.elementals
    assert not world.dragons


def test_goblin_kills_count():
    world, _ = session([], max_stickmen=0)
    goblin = world.goblin
    world.add_stickman(goblin.contact() + Vec2(150, 0))
    run(world, 15.0)
    assert world.kills >= 1


def test_a_stickman_spawns_at_a_screen_edge_every_six_seconds_up_to_the_cap():
    world, _ = session([WindowRecord(1, Rect(500, 600, 300, 230))], max_stickmen=3, defenders=())
    spawned = []
    original = world.spawn_at_edge

    def spy(edge=None):
        stickman = original(edge)
        spawned.append(stickman)
        return stickman

    world.spawn_at_edge = spy
    run(world, 0.9)
    assert not spawned
    run(world, 0.2)
    assert len(spawned) == 1
    run(world, 6.0)
    assert len(spawned) == 2
    run(world, 30.0)
    assert len(world.stickmen) == 3 and len(spawned) == 3
    assert all(s.wander for s in world.stickmen)


def test_spawn_edges():
    world, _ = session([WindowRecord(1, Rect(500, 600, 300, 230))])
    left = world.spawn_at_edge("left")
    assert left.contact().x == USABLE.left
    right = world.spawn_at_edge("right")
    assert right.contact().x == USABLE.right

    top = world.spawn_at_edge("top")
    assert top.follower.in_transition
    assert top.contact().y <= SCREEN.top + 1.0
    run(world, 2.0)
    assert not top.follower.in_transition
    assert top.follower.current_anchor().surface.walkable


def test_fullscreen_window_leaves_climbable_sides_and_a_walkable_floor():
    world, _ = session([WindowRecord(1, Rect(0, 30, 1400, 800))])
    walls = [s for s in world.surfaces if s.wall and s.box is None]
    assert {s.start.x for s in walls} == {USABLE.left, USABLE.right}
    floor = [s for s in world.surfaces if s.kind is SurfaceKind.FLOOR]
    assert min(s.low for s in floor) == USABLE.left
    assert max(s.high for s in floor) == USABLE.right

    planner = world.planner
    left = planner.anchor_near(Vec2(USABLE.left + 5, USABLE.bottom), walk_only=True)
    right = planner.anchor_near(Vec2(USABLE.right - 5, USABLE.bottom), walk_only=True)
    top = planner.anchor_near(Vec2(700, USABLE.top + TITLE_BAR), walk_only=True)
    assert top.point.y == USABLE.top + TITLE_BAR
    for start, goal in ((left, right), (right, left), (top, left), (left, top)):
        assert planner.plan(start, goal) is not None
    for wall in walls:
        middle = wall.point_at((wall.low + wall.high) / 2)
        assert planner.plan(left, Anchor(wall, middle)) is not None

    stickman = world.spawn_at_edge("left")
    assert stickman.contact().x == USABLE.left


def test_world_overlay_round_trip():
    origin = Vec2(-1440, -120)
    point = Vec2(-300.5, 40.25)
    assert to_world(to_local(point, origin), origin) == point
    assert to_local(Vec2(-1440, -120), origin) == Vec2(0, 0)


def test_window_source_errors_keep_the_last_layout():
    class Broken(FakeWindowSource):
        fail = False

        def snapshot(self):
            if self.fail:
                raise RuntimeError("window server unavailable")
            return super().snapshot()

    source = Broken([WindowRecord(1, Rect(400, 500, 400, 200))])
    world = DesktopSession(SCREEN, USABLE, source, seed=1)
    assert not world.goblins and len(world.chimeras) == 1
    source.fail = True
    assert not world.poll()
    assert world.source_error == "window server unavailable"
    assert world.boxes == [Rect(400, 500, 400, 200)]


def test_only_windows_up_against_the_top_of_the_screen_drop_to_their_tab_bar():
    near, low = Rect(300, USABLE.top + 10, 500, 400), Rect(900, 300, 300, 300)
    world, _ = session([WindowRecord(1, near), WindowRecord(2, low)])
    tops = sorted(box.top for box in world.boxes)
    assert tops == [near.top + TITLE_BAR, low.top]
