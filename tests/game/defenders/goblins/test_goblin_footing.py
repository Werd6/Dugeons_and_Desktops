from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1.0 / 60.0


def spear_goblin_versus(box: Rect, quarry: Vec2, start: Vec2, seconds: float):
    world = SimWorld([box], 700.0, 1200.0, ceiling=20.0, seed=5)
    stickman = world.add_stickman(quarry, "barbarian")
    stickman.update = lambda dt: None
    stickman.hurt = lambda *args, **kwargs: False
    goblin = world.add_goblin(start, "spear")
    throws = 0
    for _ in range(int(seconds / DT)):
        world.advance(DT)
        if goblin.weapon.time is not None and goblin.weapon.time < 1.5 * DT:
            throws += 1
    return goblin, throws


def test_spear_goblin_does_not_park_on_a_wall_beside_its_quarry():
    goblin, throws = spear_goblin_versus(
        Rect(400, 300, 200, 400), quarry=Vec2(420, 300), start=Vec2(300, 700), seconds=25.0
    )
    assert goblin.locomotion.mode is PoseMode.WALK
    assert goblin.follower.current_anchor().surface.walkable
    assert throws >= 2


def test_spear_goblin_throws_from_where_it_stands_when_it_can():
    goblin, throws = spear_goblin_versus(
        Rect(400, 500, 200, 200), quarry=Vec2(410, 500), start=Vec2(150, 700), seconds=12.0
    )
    assert goblin.contact().y == 700.0, "stayed on the floor"
    assert throws >= 3


def test_spear_goblin_can_throw_while_climbing_a_wall():
    from dungeons_desktops.navigation.planner import Anchor

    world = SimWorld([Rect(400, 300, 200, 400)], 700.0, 1200.0, ceiling=20.0, seed=5)
    prey = world.add_stickman(Vec2(360, 500), "barbarian")
    prey.update = lambda dt: None
    prey.hurt = lambda *args, **kwargs: False
    goblin = world.add_goblin(Vec2(400, 500), "spear")
    wall = next(
        surface
        for surface in world.goblin_planner.surfaces
        if not surface.walkable and abs(surface.start.x - 400) < 1
    )
    point = wall.point_at((wall.low + wall.high) / 2)
    goblin.follower.reset(Anchor(wall, point))
    goblin.locomotion.teleport(goblin.follower.command())
    goblin.cooldown = 0.0
    throws = 0
    for _ in range(180):
        world.advance(DT)
        if goblin.weapon.time is not None and goblin.weapon.time < 1.5 * DT:
            throws += 1
    assert goblin.locomotion.mode is PoseMode.CLIMB
    assert throws >= 1
