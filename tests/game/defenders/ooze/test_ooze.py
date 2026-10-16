from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.menu import DEFENDER_NAMES
from dungeons_desktops.desktop.session import SUPPORTED_DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.actors.movement import RouteFollower
from dungeons_desktops.game.defenders.ooze.actor import OOZE_HP, SKELETON_FADE
from dungeons_desktops.game.defenders.ooze.render import BODY, draw_ooze
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor, Move, Route
from dungeons_desktops.navigation.terrain import SurfaceKind

FLOOR = 500.0
STEP = 1 / 60


def run(world: SimWorld, seconds: float, until=None) -> bool:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if until is not None and until():
            return True
    return False


def test_ooze_is_an_optional_30_hp_defender_and_a_monster_target():
    assert SUPPORTED_DEFENDERS[:2] == ("elementals", "ooze")
    assert DEFENDER_NAMES["ooze"] == "Ooze"

    world = SimWorld([], FLOOR, 700, seed=2)
    ooze = world.add_ooze(Vec2(200, FLOOR), facing=1)
    assert ooze.max_hp == OOZE_HP == 30
    assert ooze in world.monsters()
    assert world.locate(ooze) == ooze.center()
    assert world.monster_at(ooze.center()) is ooze

    session = DesktopSession(
        Rect(0, 0, 700, 540),
        Rect(0, 0, 700, FLOOR),
        FakeWindowSource(),
        seed=2,
        max_stickmen=0,
        defenders=("ooze",),
    )
    assert len(session.oozes) == 1
    assert session.defender_health == 1.0


def test_ooze_hunts_slowly_lurches_and_engulfs():
    world = SimWorld([], FLOOR, 700, seed=2)
    ooze = world.add_ooze(Vec2(100, FLOOR), facing=1)
    adventurer = world.add_stickman(Vec2(300, FLOOR), "unarmed")
    rest = ooze.rig.points()

    assert run(world, 12.0, lambda: adventurer.engulfed_by is ooze)
    assert ooze.position.x > 100
    assert adventurer in ooze.engulfed
    assert not adventurer.prey
    assert ooze.phase > 0.0
    assert any(
        current.distance_to(original) > 0.5
        for current, original in zip(ooze.rig.points(), rest, strict=True)
    )


def test_engulfed_adventurer_keeps_attacking_while_the_ooze_digests_them():
    world = SimWorld([], FLOOR, 700, seed=2)
    ooze = world.add_ooze(Vec2(300, FLOOR), facing=1)
    fighter = world.add_stickman(Vec2(300, FLOOR), "fighter")
    ooze._engulf(fighter)

    run(world, 2.2)
    assert ooze.damage > 0
    assert 0 < fighter.hp < fighter.max_hp
    assert fighter.engulfed_by is ooze
    assert fighter.animated


def test_digested_adventurer_becomes_a_fading_skeleton():
    world = SimWorld([], FLOOR, 700, seed=2)
    ooze = world.add_ooze(Vec2(300, FLOOR), facing=1)
    victim = world.add_stickman(Vec2(300, FLOOR), "unarmed")
    victim.damage = victim.max_hp - 1
    ooze._engulf(victim)

    assert run(world, 1.2, lambda: bool(ooze.skeletons))
    assert victim not in world.stickmen
    assert world.kills == 1
    run(world, SKELETON_FADE + 0.2)
    assert not ooze.skeletons


def test_ooze_routes_over_walls_and_ceilings_without_jump_or_drop_moves():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=2)
    ooze = world.add_ooze(Vec2(100, FLOOR), facing=1)
    ceiling = next(
        surface
        for surface in world.ooze_planner.surfaces
        if surface.kind is SurfaceKind.CEILING
    )

    assert ooze._route_to(ceiling.point_at(350))
    assert ooze.follower is not None
    moves = {step.move for step in ooze.follower.remaining_steps()}
    assert {Move.CLIMB, Move.HANG}.issubset(moves)
    assert Move.JUMP not in moves and Move.DROP not in moves


def test_ooze_bends_around_a_corner_one_body_section_at_a_time():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=2)
    ooze = world.add_ooze(Vec2(100, FLOOR), facing=1)
    wall = next(
        surface
        for surface in world.ooze_planner.surfaces
        if surface.kind is SurfaceKind.RIGHT
    )
    route = world.ooze_planner.plan(
        ooze.follower.current_anchor(), Anchor(wall, wall.point_at(300))
    )
    assert route is not None
    corner = next(step for step in route.steps if step.move is Move.GRAB)
    ooze.follower.set_route(Route((corner,)))
    ooze.follower.elapsed = corner.duration / 2
    ooze._settle()

    _, trailing_up = ooze.local_frame(-40.0)
    _, leading_up = ooze.local_frame(40.0)
    assert trailing_up.dot(corner.from_surface.normal) > 0.9
    assert leading_up.dot(corner.surface.normal) > 0.9
    assert trailing_up.dot(leading_up) < 0.2


def test_ooze_drops_from_the_ceiling_and_engulfs_adventurer_below():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=2)
    ooze = world.add_ooze(Vec2(100, FLOOR), facing=1)
    ceiling = next(
        surface
        for surface in world.ooze_planner.surfaces
        if surface.kind is SurfaceKind.CEILING
    )
    anchor = Anchor(ceiling, ceiling.point_at(350))
    ooze.follower = RouteFollower(anchor)
    ooze.position, ooze.up = anchor.point, ceiling.normal
    adventurer = world.add_stickman(Vec2(350, FLOOR), "unarmed")

    assert run(world, 2.0, lambda: adventurer.engulfed_by is ooze)
    assert ooze.support is not None and ooze.support.walkable
    assert ooze.position.y == FLOOR


def test_disabling_an_ooze_defender_releases_its_captive():
    session = DesktopSession(
        Rect(0, 0, 700, 540),
        Rect(0, 0, 700, FLOOR),
        FakeWindowSource(),
        seed=2,
        max_stickmen=0,
        defenders=("ooze",),
    )
    ooze = session.oozes[0]
    adventurer = session.add_stickman(ooze.position, "unarmed")
    ooze._engulf(adventurer)

    session.set_defenders(())
    assert adventurer.engulfed_by is None
    assert adventurer.animated


def test_ooze_renderer_is_a_flat_green_silhouette_on_any_surface():
    world = SimWorld([], 130, 220, ceiling=10, seed=2)
    ooze = world.add_ooze(Vec2(100, 130), facing=1)
    image = QImage(220, 160, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    draw_ooze(painter, ooze)
    painter.end()
    assert any(
        image.pixelColor(x, y).name() == BODY.name()
        for x in range(55, 145)
        for y in range(70, 135)
    )
