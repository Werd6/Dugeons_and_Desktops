from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.systems.world import SimWorld

STEP = 1 / 60
FLOOR = 700.0
WINDOW = Rect(300, 400, 200, 200)


def world_with_window():
    return SimWorld([WINDOW], FLOOR, 1000.0, seed=3)


def run(world, seconds, each):
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        each()


def test_arrows_fly_through_windows_and_stick_in_the_floor():
    world = world_with_window()
    world.spells.shoot(Vec2(250, 500), Vec2(300, 0))
    arrow = world.spells.arrows[0]
    inside = []
    run(world, 1.5, lambda: inside.append(WINDOW.contains(arrow.position)))
    assert any(inside)
    assert arrow.stuck is not None and arrow.position.y >= FLOOR


def test_bombs_fly_through_windows_and_burst_on_the_floor():
    world = world_with_window()
    world.vials.throw(Vec2(250, 500), Vec2(250, 0))
    vial = world.vials.flying[0]
    inside = []
    run(world, 1.5, lambda: inside.append(WINDOW.contains(vial.position)))
    assert any(inside)
    assert not world.vials.flying and vial.position.y >= FLOOR - 5.0


def test_spears_fly_through_windows():
    world = world_with_window()
    world.spears.throw(Vec2(250, 500), Vec2(300, 0), 12.0)
    spear = world.spears.spears[0]
    inside = []
    run(world, 0.6, lambda: inside.append(WINDOW.contains(spear.position)))
    assert any(inside)
