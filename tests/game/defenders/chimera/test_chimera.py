from dungeons_desktops.core.geometry import Rect, Vec2, wrap_angle
from dungeons_desktops.desktop.overlay import DEFENDER_BARS
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.defenders.chimera.actor import CHIMERA_HP, Chimera
from dungeons_desktops.game.defenders.chimera.goat import FIRE_BURST, FIRE_COOLDOWN, NECK_CONE, Fire
from dungeons_desktops.game.defenders.chimera.lion import POUNCE_COOLDOWN
from dungeons_desktops.game.defenders.chimera.snake import BEHIND_RANGE, FRONT_RANGE, Strike
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import SurfaceKind, TerrainChange

STEP = 1 / 60
WINDOW = Rect(300, 300, 400, 200)
TALL = Rect(600, 650, 250, 250)
"""A window standing on the floor (900), its left side a wall to climb."""


def run(world, seconds: float, each=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None and each():
            return


def on_window(facing: int = 1) -> tuple[SimWorld, Chimera]:
    world = SimWorld([WINDOW], 800.0, 1000.0, ceiling=0.0, seed=2)
    return world, world.add_chimera(Vec2(500, WINDOW.top), facing)


def on_a_top(x: float, prey: list[float], seed: int = 2) -> tuple[SimWorld, Chimera, list]:
    """The chimera on a wide window top at `x`, a man standing at each of `prey`."""
    world = SimWorld([Rect(200, 600, 600, 300)], 900.0, 1200.0, ceiling=0.0, seed=seed)
    chimera = world.add_chimera(Vec2(x, 600), 1)
    return world, chimera, [world.add_stickman(Vec2(px, 600)) for px in prey]


def calm(chimera: Chimera, lion: bool = True, goat: bool = True) -> None:
    """Hold back the lion's leaps and the goat's fire, to watch the rest."""
    if lion:
        chimera.prowl.leap_wait = 1000.0
    if goat:
        chimera.goat.state, chimera.goat.timer = Fire.COOLDOWN, 1000.0


def test_the_chimera_prowls_in_first_on_the_front_window():
    world = DesktopSession(
        Rect(0, 0, 1400, 900),
        Rect(0, 30, 1400, 800),
        FakeWindowSource([WindowRecord(1, WINDOW)]),
        seed=3,
        max_stickmen=0,
    )
    assert DEFENDERS[0] == "chimera" and world.defender == "chimera"
    assert DEFENDER_BARS["chimera"][0] == "Chimera"
    assert len(world.chimeras) == 1
    chimera = world.chimeras[0]
    assert chimera.support is not None and chimera.support.start.y == WINDOW.top
    assert world.chimera_planner.owns(chimera.support)
    assert world.defender_max_hp == CHIMERA_HP and world.defender_health == 1.0


def test_it_climbs_walls_but_never_hangs_under_anything():
    world, _ = on_window()
    surfaces = world.chimera_planner.surfaces
    assert not any(s.hanging for s in surfaces)
    walls = [s for s in surfaces if not s.walkable]
    assert any(s.box == 0 for s in walls), "the window's sides"
    assert any(s.box is None for s in walls), "the screen's sides"


def test_it_wanders_about_on_its_own():
    world, chimera = on_window()
    start = chimera.body
    places = set()

    def watch():
        if chimera.support is not None:
            places.add((chimera.support.kind, chimera.support.box))

    run(world, 40.0, watch)
    assert chimera.body.distance_to(start) > 50.0 or len(places) > 1
    assert len(places) > 1


def test_it_stalks_and_pounces_on_prey_then_waits_to_pounce_again():
    world, chimera, (man,) = on_a_top(300, [480])
    calm(chimera, lion=False)
    chimera.prowl.leap_wait = 0.0
    run(world, 6.0, lambda: chimera.prowl.leap is not None)
    leap = chimera.prowl.leap
    assert leap is not None and leap.kind == "pounce" and leap.quarry is man
    assert chimera.prowl.leap_wait > POUNCE_COOLDOWN - 0.1
    run(world, 2.0, lambda: not man.prey)
    assert not man.prey, "the pounce mauled him"
    assert leap.struck


def test_it_climbs_a_wall_to_get_at_prey_on_a_higher_window():
    world = SimWorld([TALL], 900.0, 1200.0, ceiling=0.0, seed=2)
    chimera = world.add_chimera(Vec2(500, 900), -1)
    calm(chimera, lion=False)
    man = world.add_stickman(Vec2(760, TALL.top))
    on_wall = []

    def watch():
        support = chimera.support
        if support is not None and support.kind is SurfaceKind.LEFT and support.box == 0:
            on_wall.append(chimera.prowl.position)
            for leg in chimera.legs:
                if leg.lift == 0.0:
                    assert abs(leg.foot.x - TALL.left) < 1.0, "feet planted on the wall"
        return not man.prey

    run(world, 30.0, watch)
    assert on_wall and min(p.y for p in on_wall) < TALL.bottom - 40.0, "it climbed"
    assert not man.prey


def test_it_climbs_a_narrow_slot_without_belly_crawling():
    """A tight gutter between windows used to squash the body flat against the wall.
    Walls stay whole and the body keeps its hip height, clipping the neighbor."""
    from dungeons_desktops.game.defenders.chimera.lion import HIP_HEIGHT

    gap = 22.0
    left = Rect(200, 300, 280, 400)
    right = Rect(200 + 280 + gap, 300, 300, 400)
    world = SimWorld([left, right], 900.0, 1400.0, ceiling=0.0, seed=4)
    wall_x = left.right
    walls = [
        s
        for s in world.chimera_planner.surfaces
        if s.wall and s.box == 0 and abs(s.start.x - wall_x) < 0.5
    ]
    assert walls, "narrow slot still has a climbable side"
    assert max(s.length for s in walls) > 200.0, "wall is not truncated by clearance"

    chimera = world.add_chimera(Vec2(100, 900), 1)
    calm(chimera, lion=False)
    # Plant it mid-wall in the slot and settle one frame.
    wall = max(walls, key=lambda s: s.length)
    chimera.prowl._attach(world.chimera_planner.anchor_at(wall, wall.low + wall.length * 0.5))
    run(world, STEP)
    support = chimera.support
    assert support is not None and not support.walkable
    # Body sits a full hip-height out from the wall — not crushed into it by the neighbor.
    out = (chimera.body - chimera.prowl.position).dot(support.normal)
    assert abs(out - HIP_HEIGHT) < 1.5


def test_its_planted_feet_stay_on_its_surface():
    world, chimera = on_window(facing=1)
    run(world, 1.0)
    for _ in range(600):
        world.advance(STEP)
        support = chimera.support
        if support is None or chimera.prowl.follower.in_transition:
            continue
        for leg in chimera.legs:
            if leg.lift == 0.0:
                height = (leg.foot - chimera.prowl.position).dot(support.normal)
                assert abs(height) < 0.5


def test_its_heads_and_tail_keep_their_places_as_it_turns():
    world, chimera = on_window(facing=1)
    calm(chimera)
    run(world, 1.0)
    ahead = chimera.forward
    assert (chimera.lion_head - chimera.shoulder).dot(ahead) > 0.0
    assert (chimera.goat_head - chimera.body).dot(chimera.up) > 15.0
    assert max((p - chimera.body).dot(chimera.up) for p in chimera.tail) > (
        (chimera.goat_head - chimera.body).dot(chimera.up)
    ), "the serpent arches over"
    lion = (chimera.lion_head - chimera.body).dot(ahead)
    chimera._turn(-chimera.facing)
    assert abs((chimera.lion_head - chimera.body).dot(chimera.forward) - lion) < 1e-6


def test_the_goat_breathes_fire_at_prey_behind_and_burns_him():
    world, chimera, (man,) = on_a_top(520, [390])
    calm(chimera, goat=False)
    chimera.prowl.turn_wait = 1000.0
    seen = {}

    def watch():
        if chimera.goat.state is Fire.WINDUP and "behind" not in seen:
            seen["behind"] = (man.center() - chimera.body).dot(chimera.forward) < 0.0
        return not man.prey

    run(world, 3.0, watch)
    assert seen["behind"], "it turned to him behind the lion"
    assert not man.prey and man.burn is not None
    assert chimera.goat.catches == 1


def test_the_goats_beam_sweeps_across_its_target_and_carries_far_past_him():
    world = SimWorld([], 900.0, 1400.0, ceiling=0.0, seed=2)
    chimera = world.add_chimera(Vec2(1000, 900), 1)
    calm(chimera, goat=False)
    chimera.prowl.turn_wait = 1000.0
    man = world.add_stickman(Vec2(700, 900))
    reach = man.center().distance_to(chimera.goat_head)
    aims, farthest = [], 0.0

    def watch():
        nonlocal farthest
        goat = chimera.goat
        if goat.state is Fire.BREATHE:
            aims.append(wrap_angle(goat.aim.angle() - chimera.up.angle()))
        for flame in goat.flames:
            farthest = max(farthest, flame.position.distance_to(chimera.goat_head))
        return goat.state is Fire.COOLDOWN and not goat.flames

    run(world, 6.0, watch)
    assert not man.prey
    assert farthest > reach + 150.0
    assert max(aims) - min(aims) > 0.6, "it swept"


def test_the_goat_waits_out_its_cooldown_between_breaths():
    world, chimera, _men = on_a_top(520, [390, 650, 380, 660])
    calm(chimera, goat=False)
    states = []
    run(world, 12.0, lambda: states.append(chimera.goat.state))
    starts = [
        i
        for i, (a, b) in enumerate(zip(states, states[1:], strict=False))
        if b is Fire.BREATHE and a is not Fire.BREATHE
    ]
    assert starts, "it breathed"
    for a, b in zip(starts, starts[1:], strict=False):
        assert (b - a) * STEP >= FIRE_BURST + FIRE_COOLDOWN - 0.05


def test_the_goats_neck_only_turns_so_far():
    world, chimera = on_window()
    calm(chimera, goat=False)
    world.add_stickman(Vec2(500, world.floor_y))
    for _ in range(120):
        world.advance(STEP)
        off = wrap_angle(chimera.goat.aim.angle() - chimera.up.angle())
        assert abs(off) <= NECK_CONE + 1e-6


def test_the_serpent_strikes_farther_behind_than_in_front():
    world, chimera = on_window(facing=1)
    calm(chimera)
    run(world, 0.2)
    back, front = -chimera.forward, chimera.forward
    behind = world.add_stickman(chimera.hip + back * (BEHIND_RANGE - 15.0) + Vec2(0, 18))
    assert chimera.snake._spot(chimera) is behind
    world.stickmen.remove(behind)
    ahead = world.add_stickman(chimera.shoulder + front * (FRONT_RANGE + 15.0) + Vec2(0, 18))
    assert chimera.snake._spot(chimera) is None, "too far in front"
    world.stickmen.remove(ahead)
    near = world.add_stickman(chimera.shoulder + front * (FRONT_RANGE - 15.0) + Vec2(0, 18))
    assert chimera.snake._spot(chimera) is near


def test_the_serpent_dashes_bites_and_recoils_to_rest():
    world, chimera, (man,) = on_a_top(520, [460])
    calm(chimera)
    states = []

    def watch():
        if not states or states[-1] != chimera.snake.state:
            states.append(chimera.snake.state)
        return chimera.snake.state is Strike.COOLDOWN

    run(world, 3.0, watch)
    assert states[-4:] == [Strike.COIL, Strike.STRIKE, Strike.RECOIL, Strike.COOLDOWN]
    assert man.hp < man.max_hp or not man.prey, "bitten"
    rest = chimera._rest_tail()[-1]
    assert chimera.snake_head.distance_to(rest) < 10.0, "back at rest"


def test_it_rides_its_window_and_falls_when_it_closes():
    world, chimera = on_window()
    calm(chimera)
    run(world, 0.2)
    assert chimera.support is not None
    before = chimera.body
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(330, 280, 400, 200)])
    run(world, STEP)
    assert chimera.body.distance_to(before + Vec2(30, -20)) < 3.0
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    run(world, 3.0)
    support = chimera.support
    assert support is not None and support.start.y == world.floor_y
    assert all(abs(leg.foot.y - world.floor_y) < 6.0 for leg in chimera.legs)


def test_it_can_be_hit_and_slumps_when_killed():
    world, chimera = on_window()
    calm(chimera)
    run(world, 0.5)
    for part in chimera.parts():
        assert world.monster_at(part) is chimera
    assert world.hurt_monster(chimera, CHIMERA_HP, chimera.body, Vec2(40, -40))
    assert chimera in world.fallen and not world.chimeras
    run(world, 2.0)
    assert abs(chimera.body.y - (WINDOW.top - 7.0)) < 1.0
    run(world, 10.0)
    assert chimera not in world.fallen


def test_primal_heads_breathe_different_colored_fire():
    from dungeons_desktops.game.defenders.chimera.goat import Fire

    world = SimWorld([], 900.0, 1400.0, ceiling=0.0, seed=5)
    chimera = world.add_chimera(Vec2(700, 900), 1, legendary=True)
    calm(chimera, lion=True, goat=False)
    chimera.lion_breath.state = chimera.snake_breath.state = Fire.COOLDOWN
    chimera.lion_breath.timer = chimera.snake_breath.timer = 1000.0
    chimera.prowl.turn_wait = 1000.0
    world.add_stickman(Vec2(450, 900))

    def watching_goat():
        return bool(chimera.goat.flames)

    run(world, 4.0, watching_goat)
    assert chimera.goat.flames
    assert all(f.palette == "blue" for f in chimera.goat.flames)

    # Force lion and snake breaths so we don't wait on their cooldowns/AI.
    for breath, tint in ((chimera.lion_breath, "orange"), (chimera.snake_breath, "green")):
        breath.state = Fire.BREATHE
        breath.timer = 0.2
        breath.aim = chimera.forward
        breath.flames.clear()
        breath.update(STEP, chimera)
        assert breath.flames
        assert all(f.palette == tint for f in breath.flames)
