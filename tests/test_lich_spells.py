from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind, TerrainChange
from dungeons_desktops.systems.lich import SPELLBOOK
from dungeons_desktops.systems.necromancy import (
    CHAIN_DAMAGE,
    FIREBALL_RADIUS,
    MISSILES,
    SPELLS,
    TENTACLE_TIME,
    WORD_DELAY,
)
from dungeons_desktops.systems.world import SimWorld

STEP = 1 / 60
FLOOR = 700.0


def world_with(*boxes: Rect) -> SimWorld:
    return SimWorld(list(boxes), FLOOR, 1400.0, ceiling=20.0, seed=3)


def run(world: SimWorld, seconds: float) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)


def idle(world: SimWorld, x: float, variant: str = "wizard", y: float = FLOOR):
    man = world.add_stickman(Vec2(x, y), variant)
    man.wander = False
    return man


ORIGIN = Vec2(200, 670)


def cast(world: SimWorld, spell: str, foe) -> None:
    world.necromancy.cast(spell, None, ORIGIN, foe)


def frozen(world: SimWorld, seconds: float = 10.0) -> None:
    """Nobody fights anybody (a thrall and the free adventurers would otherwise)."""
    for man in world.stickmen:
        man.paralyze(seconds)


def test_the_spellbook_is_the_five_spells_in_order():
    assert (
        SPELLBOOK
        == SPELLS
        == (
            "fireball",
            "power_word_kill",
            "magic_missiles",
            "chain_lightning",
            "black_tentacles",
        )
    )


def test_fireball_burns_everyone_in_the_blast_but_not_thralls_or_bystanders():
    world = world_with()
    foe = idle(world, 500)
    near = idle(world, 530, "ranger")
    tough = idle(world, 470, "barbarian")
    thrall = idle(world, 520, "cleric")
    thrall.enthrall()
    far = idle(world, 500 + FIREBALL_RADIUS + 60)
    frozen(world)
    cast(world, "fireball", foe)
    run(world, 2.0)
    assert not foe.animated and not near.animated
    assert tough.animated and tough.damage == 4
    assert thrall.damage == 0 and far.damage == 0
    assert world.necromancy.kills["fireball"] == 2 and world.necromancy.scorches


def test_power_word_kill_slays_outright_whatever_his_hit_points():
    world = world_with()
    foe = idle(world, 500, "barbarian")
    beside = idle(world, 520)
    assert foe.max_hp == 8
    cast(world, "power_word_kill", foe)
    run(world, WORD_DELAY - 0.1)
    assert foe.animated
    run(world, 0.3)
    assert not foe.animated and beside.damage == 0
    assert world.necromancy.wisps


def test_magic_missiles_split_between_the_foe_and_those_near_him():
    world = world_with()
    foe = idle(world, 500, "barbarian")
    others = [idle(world, 580, "paladin"), idle(world, 650, "barbarian")]
    thrall = idle(world, 540, "cleric")
    thrall.enthrall()
    far = idle(world, 900, "paladin")
    frozen(world)
    cast(world, "magic_missiles", foe)
    run(world, 3.0)
    assert foe.damage >= 3
    assert all(o.damage >= 1 for o in others)
    assert foe.damage + sum(o.damage for o in others) == MISSILES
    assert far.damage == 0 and thrall.damage == 0


def test_magic_missiles_all_go_to_a_lone_foe():
    world = world_with()
    foe = idle(world, 500, "barbarian")
    cast(world, "magic_missiles", foe)
    run(world, 3.0)
    assert foe.damage == MISSILES - 0 or not foe.animated


def test_magic_missiles_can_kill_several():
    world = world_with()
    men = [idle(world, x) for x in (500, 560, 620)]
    for man in men:
        man.damage = 3
    cast(world, "magic_missiles", men[0])
    run(world, 3.0)
    assert sum(not m.animated for m in men) >= 2


def test_chain_lightning_arcs_to_three_more_near_each_other():
    world = world_with()
    line = [idle(world, 500 + 120 * i, "barbarian") for i in range(5)]
    thrall = idle(world, 560, "cleric")
    thrall.enthrall()
    frozen(world)
    cast(world, "chain_lightning", line[0])
    assert thrall not in [arc.target for arc in world.necromancy.arcs]
    run(world, 0.6)
    assert [m.damage for m in line[:4]] == list(CHAIN_DAMAGE)
    assert line[4].damage == 0 and thrall.damage == 0


def test_chain_lightning_stuns_briefly():
    world = world_with()
    foe = idle(world, 500, "barbarian")
    cast(world, "chain_lightning", foe)
    run(world, 0.2)
    assert foe.stun > 0


def test_chain_lightning_kills_several():
    world = world_with()
    men = [idle(world, 500 + 60 * i) for i in range(3)]
    for man in men:
        man.damage = 1
    cast(world, "chain_lightning", men[0])
    run(world, 0.6)
    assert sum(not m.animated for m in men) >= 2


def perch(world: SimWorld, kind: SurfaceKind, box, along: float, variant: str = "wizard"):
    """An adventurer climbing a window side or hanging under it."""
    surface = next(s for s in world.planner.surfaces if s.kind is kind and s.box == box)
    man = idle(world, 50, variant)
    man.follower.reset(Anchor(surface, surface.point_at(along)))
    man.locomotion.teleport(man.follower.command())
    return man


def faces(world: SimWorld) -> set:
    return {(arm.box, (arm.normal.x, arm.normal.y)) for arm in world.necromancy.tentacles[0].arms}


def test_black_tentacles_erupt_from_every_surface_near_the_foe():
    world = world_with(Rect(500, 450, 260, 150))
    foe = idle(world, 470)
    idle(world, 1200)
    cast(world, "black_tentacles", foe)
    found = faces(world)
    assert (None, (0.0, -1.0)) in found  # the floor
    assert (0, (-1.0, 0.0)) in found  # the window's left side
    assert (0, (0.0, 1.0)) in found  # its underside
    assert all(
        arm.base.distance_to(foe.center()) <= 130.0 for arm in world.necromancy.tentacles[0].arms
    )


def test_black_tentacles_grow_from_the_screen_edge_too():
    world = world_with()
    foe = idle(world, 40)
    cast(world, "black_tentacles", foe)
    assert (None, (1.0, 0.0)) in faces(world)


def test_black_tentacles_grab_and_crush_floor_climber_and_hanger_but_no_thrall():
    world = world_with(Rect(500, 450, 260, 150))
    foe = idle(world, 470, "barbarian")
    climber = perch(world, SurfaceKind.LEFT, 0, 585, "ranger")
    hanger = perch(world, SurfaceKind.CEILING, 0, 545)
    thrall = idle(world, 520, "cleric")
    thrall.enthrall()
    far = idle(world, 1000)
    frozen(world, 0.5)
    thrall.paralyze(10.0)
    cast(world, "black_tentacles", foe)
    run(world, 2.0)
    held = world.necromancy.tentacles[0].held
    assert foe in held and climber in held and hanger in held and thrall not in held
    assert all(m.stun > 0 and m.damage >= 2 for m in (foe, climber, hanger))
    assert far.damage == 0 and thrall.damage == 0
    run(world, TENTACLE_TIME)
    assert not world.necromancy.tentacles
    assert not climber.animated and not hanger.animated and foe.animated
    assert world.necromancy.kills["black_tentacles"] == 2


def test_black_tentacles_ride_a_moving_window_and_vanish_with_it():
    world = world_with(Rect(400, 620, 300, 60))
    foe = idle(world, 550, y=620)
    cast(world, "black_tentacles", foe)
    spell = world.necromancy.tentacles[0]
    on_window = [a for a in spell.arms if a.box == 0]
    on_floor = [a for a in spell.arms if a.box is None]
    assert on_window and on_floor
    before = [a.base for a in on_window]
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(430, 600, 300, 60)])
    assert [a.base for a in on_window] == [b + Vec2(30, -20) for b in before]
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert world.necromancy.tentacles and all(a.box is None for a in spell.arms)
    assert len(spell.arms) == len(on_floor)


def test_the_lich_casts_his_spells_for_real():
    world = world_with()
    lich = world.add_lich(Vec2(200, FLOOR))
    lich.door_wait = 1e9
    foe = idle(world, 420)
    run(world, 6.0)
    assert lich.casts >= 1 and (foe.damage > 0 or not foe.animated)
    assert world.necromancy.hits["fireball"] >= 1
