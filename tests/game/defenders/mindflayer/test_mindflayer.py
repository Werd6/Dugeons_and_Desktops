import math

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.actors.mortal import FADE_TIME
from dungeons_desktops.game.defenders.mindflayer.actor import (
    BLAST_DAMAGE,
    CEILING_GAP,
    GRAB_TIME,
    HOVER,
    MAX_LEAN,
    MIND_FLAYER_HP,
    PULSE_DOWN,
    PULSE_STUN,
    PULSE_WINDUP,
    WALL_GAP,
    Bolt,
    Power,
)
from dungeons_desktops.game.defenders.mindflayer.devourer import (
    DEVOURER_DAMAGE,
    DEVOURER_HP,
    Devourer,
)
from dungeons_desktops.navigation.planner import Move
from dungeons_desktops.rig.biped import UP

STEP = 1 / 60
FLOOR = 700.0
WINDOW = Rect(300, 300, 300, 200)
LOW_WINDOW = Rect(300, 420, 300, 256)
"""Its sides reach down within a jump of the floor."""


def world_with(boxes=(WINDOW,), seed=4):
    from dungeons_desktops.game.world.simulation import SimWorld

    return SimWorld(list(boxes), FLOOR, 1000.0, ceiling=20.0, seed=seed)


def run(world, seconds, until=None, each=None) -> bool:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()
        if until is not None and until():
            return True
    return until is None


def thrall_in(world, point, variant="barbarian"):
    stickman = world.add_stickman(point, variant)
    stickman.enthrall()
    return stickman


# ----- powers -------------------------------------------------------------------


def test_the_mind_blast_bolt_paralyses_without_damage():
    world = world_with()
    flayer = world.add_mindflayer(Vec2(450, WINDOW.top))
    flayer.blast_cooldown = flayer.pulse_cooldown = 99.0
    victim = world.add_stickman(Vec2(150, FLOOR), "barbarian")
    flayer.bolts.append(Bolt(victim.center() + Vec2(60, -20), victim))
    assert run(world, 2.0, until=lambda: victim.paralysed)
    assert victim.damage == BLAST_DAMAGE == 0
    assert victim.prey
    assert not flayer.bolts


def test_it_grabs_a_paralysed_adventurer_in_reach_and_enthralls_him():
    world = world_with()
    flayer = world.add_mindflayer(Vec2(430, WINDOW.top))
    run(world, 0.5)
    victim = world.add_stickman(flayer.contact() + Vec2(12, 0), "paladin")
    victim.paralyze(5.0)
    assert run(world, 0.5, until=lambda: flayer.power is Power.GRAB)
    assert flayer.victim is victim and flayer.grab_reach >= 0.0
    assert run(world, GRAB_TIME + 0.5, until=lambda: victim.thrall)
    assert flayer.thralls == 1 and victim in world.thralls and not victim.prey


def test_free_adventurers_hunt_the_thrall_but_monsters_ignore_him():
    world = world_with()
    thrall = thrall_in(world, Vec2(150, FLOOR))
    hero = world.add_stickman(Vec2(250, FLOOR), "wizard")
    found = world.nearest_monster(hero.center(), 300.0)
    assert found is not None and found[0] is thrall
    assert world.monster_at(thrall.center()) is thrall

    world.stickmen.remove(hero)
    goblin = world.add_goblin(Vec2(190, FLOOR - 5.0), "sword")
    run(world, 4.0)
    assert goblin.target is not thrall
    assert thrall.damage == 0


def test_a_thrall_attacks_the_other_adventurers():
    world = world_with()
    thrall_in(world, Vec2(150, FLOOR))
    victim = world.add_stickman(Vec2(260, FLOOR))
    assert run(world, 12.0, until=lambda: victim.damage > 0)


def _ranged_thrall_hits(variant, seed=4):
    world = world_with([], seed=seed)
    thrall_in(world, Vec2(150, FLOOR), variant)
    victim = world.add_stickman(Vec2(150 + 50.0, FLOOR), "paladin")
    victim.paralyze(30.0)
    return world, victim


@pytest.mark.parametrize("variant", ["wizard", "sorcerer"])
def test_a_caster_thrall_casts_missiles_at_the_others(variant):
    world, victim = _ranged_thrall_hits(variant)
    assert run(world, 6.0, until=lambda: bool(world.spells.missiles))
    assert world.spells.missiles[0].hostile and world.spells.missiles[0].monster is victim
    assert run(world, 3.0, until=lambda: victim.damage > 0)


def test_a_ranger_thrall_shoots_the_others():
    world, victim = _ranged_thrall_hits("ranger")
    assert run(world, 6.0, until=lambda: bool(world.spells.arrows))
    assert all(a.hostile for a in world.spells.arrows)
    assert run(world, 3.0, until=lambda: victim.damage > 0)


def test_an_alchemist_thrall_bombs_the_others():
    world, victim = _ranged_thrall_hits("alchemist")
    assert run(world, 6.0, until=lambda: bool(world.vials.flying))
    assert all(v.hostile for v in world.vials.flying)
    assert run(world, 3.0, until=lambda: victim.damage > 0)


def test_a_druid_thrall_lashes_the_others_with_vines():
    world, victim = _ranged_thrall_hits("druid")
    assert run(world, 6.0, until=lambda: bool(world.spells.vines))
    assert all(v.hostile for v in world.spells.vines)
    assert run(world, 3.0, until=lambda: victim.damage > 0)


def test_free_adventurers_spells_still_spare_each_other():
    world = world_with([])
    hero = world.add_stickman(Vec2(150, FLOOR), "alchemist")
    friend = world.add_stickman(Vec2(200, FLOOR), "barbarian")
    world.vials.throw(friend.center() + Vec2(-10, -10), Vec2(40, 0))
    world.spells.shoot(friend.center() + Vec2(-10, 0), Vec2(200, 0))
    run(world, 1.0)
    assert friend.damage == 0 and hero.damage == 0


def test_the_flayer_and_its_thralls_switch_to_whoever_is_nearest():
    world = world_with([], seed=5)
    flayer = world.add_mindflayer(Vec2(500, FLOOR))
    flayer.blast_cooldown = flayer.pulse_cooldown = 99.0
    thrall = thrall_in(world, Vec2(500, FLOOR))
    far = world.add_stickman(Vec2(900, FLOOR))
    far.paralyze(30.0)
    run(world, 0.2)
    assert flayer.target is far and thrall.hunt.target is far
    near = world.add_stickman(Vec2(380, FLOOR))
    near.paralyze(30.0)
    run(world, 0.5)
    assert flayer.target is near and thrall.hunt.target is near


def test_killing_a_thrall_releases_an_intellect_devourer():
    world = world_with()
    thrall = thrall_in(world, Vec2(150, FLOOR))
    for _ in range(thrall.max_hp):
        world.hurt_monster(thrall, 1, thrall.center(), Vec2(50, -50))
    assert not thrall.animated and thrall not in world.thralls
    assert len(world.devourers) == 1


def test_mindflayer_thralls_die_after_one_minute():
    from dungeons_desktops.game.adventurers.actor import THRALL_LIFETIME

    world = world_with()
    thrall = thrall_in(world, Vec2(150, FLOOR))
    assert thrall.mind_devoured and thrall.thrall_age == 0.0
    assert run(world, THRALL_LIFETIME + 0.2, until=lambda: not thrall.animated)
    assert thrall not in world.thralls
    assert len(world.devourers) == 1


# ----- intellect devourers ---------------------------------------------------------


def test_the_devourer_bites_for_one_and_dies_after_three_hits():
    world = world_with()
    victim = world.add_stickman(Vec2(200, FLOOR), "barbarian")
    victim.paralyze(30.0)
    devourer = world.spawn_devourer(Vec2(320, FLOOR - 30))
    assert run(world, 8.0, until=lambda: victim.damage > 0)
    assert victim.damage == DEVOURER_DAMAGE
    assert devourer.hp == DEVOURER_HP == 3
    for _ in range(3):
        assert devourer in world.devourers
        world.hurt_monster(devourer, 1, devourer.center(), Vec2(40, -40))
    assert devourer.dead and devourer in world.fallen and devourer not in world.devourers
    run(world, 1.5)
    assert not devourer.airborne and devourer.position.y == FLOOR


def test_the_devourer_climbs_a_window_side_to_reach_prey_on_top():
    world = world_with([LOW_WINDOW])
    victim = world.add_stickman(Vec2(450, LOW_WINDOW.top), "barbarian")
    victim.paralyze(60.0)
    devourer = Devourer(world, Vec2(200, FLOOR))
    devourer.leap_wait = 99.0
    world.devourers.append(devourer)
    sides = []

    def watch() -> None:
        step = devourer.follower.step if devourer.follower is not None else None
        if step is not None and step.move is Move.CLIMB:
            sides.append(devourer.up)

    assert run(world, 20.0, until=lambda: victim.damage > 0, each=watch)
    assert sides and all(abs(up.y) < 1e-6 and abs(abs(up.x) - 1.0) < 1e-6 for up in sides)


def test_the_devourer_clings_upside_down_under_a_window():
    world = world_with()
    devourer = Devourer(world, Vec2(200, FLOOR))
    world.devourers.append(devourer)
    under = next(s for s in world.goblin_planner.surfaces if s.hanging and s.box == 0)
    from dungeons_desktops.navigation.planner import Anchor

    devourer._attach(Anchor(under, under.point_at(450)))
    assert devourer.up == Vec2(0.0, 1.0)
    assert devourer.position.y == WINDOW.bottom
    assert devourer.center().y > WINDOW.bottom


# ----- psychic pulse ----------------------------------------------------------------


def test_the_pulse_knocks_adventurers_flat_then_leaves_them_paralysed():
    world = world_with()
    flayer = world.add_mindflayer(Vec2(450, WINDOW.top))
    run(world, 0.5)
    near = [world.add_stickman(flayer.contact() + Vec2(dx, 0), "wizard") for dx in (-35.0, 30.0)]
    far = world.add_stickman(Vec2(150, FLOOR), "wizard")
    flayer._start(Power.PULSE, None)
    run(world, PULSE_WINDUP + 2 * STEP)
    world.mindflayers.clear()
    assert all(s.knocked and not s.animated for s in near)
    assert far.animated and not far.paralysed
    run(world, PULSE_DOWN + 0.1)
    assert all(s.animated and s.paralysed and s.stun > 0.0 for s in near)
    run(world, PULSE_STUN + 0.2)
    assert all(s.animated and not s.paralysed for s in near)
    assert all(s in world.stickmen for s in near)


def test_knocked_or_paralysed_adventurers_never_despawn():
    world = world_with()
    lying = world.add_stickman(Vec2(150, FLOOR))
    lying.knock_down(Vec2(140, FLOOR), 200.0, 6.0, 1.0)
    frozen = world.add_stickman(Vec2(250, FLOOR))
    frozen.paralyze(6.0)
    run(world, 5.5)
    assert lying in world.stickmen and lying.fade == 0.0 and lying.knocked
    assert frozen in world.stickmen and frozen.paralysed


# ----- the mind flayer itself ---------------------------------------------------------


def test_it_has_twelve_hp_and_dies_as_a_ragdoll_into_fallen():
    world = world_with()
    flayer = world.add_mindflayer(Vec2(450, WINDOW.top))
    assert flayer.hp == MIND_FLAYER_HP
    for _ in range(MIND_FLAYER_HP - 1):
        assert not world.hurt_monster(flayer, 1, flayer.center(), Vec2(30, -30))
    assert world.hurt_monster(flayer, 1, flayer.center(), Vec2(30, -30))
    assert flayer.dead and flayer.ragdoll is not None and flayer in world.fallen
    assert world.monster_kills == 1
    run(world, flayer.linger + FADE_TIME + 0.5)
    assert flayer not in world.fallen


def _upright(flayer) -> bool:
    torso = flayer.transforms()[flayer.layout.torso]
    return abs(torso.angle - UP) <= MAX_LEAN + 1e-6


def test_it_glides_at_a_fixed_height_leaning_into_the_way_it_goes():
    world = world_with()
    flayer = world.add_mindflayer(Vec2(320, WINDOW.top))
    flayer._wander_wait = 99.0
    run(world, 0.5)
    flayer._go(Vec2(480, WINDOW.top))
    heights, leans = set(), []

    def watch() -> None:
        if flayer.follower.moving and flayer.follower.step.move is Move.WALK:
            heights.add(round(flayer.feet.y, 6))
            leans.append(flayer.lean)
        assert _upright(flayer)

    run(world, 6.0, each=watch)
    assert not flayer.follower.moving
    assert heights == {WINDOW.top - HOVER}
    assert max(leans) > MAX_LEAN * 0.5 and min(leans) >= 0.0
    run(world, 2.0)
    assert abs(flayer.lean) < 0.02


def test_it_floats_up_beside_a_window_side_without_climbing():
    world = world_with([LOW_WINDOW])
    flayer = world.add_mindflayer(Vec2(200, FLOOR))
    flayer._wander_wait = 99.0
    assert flayer._go(Vec2(450, LOW_WINDOW.top))
    beside = []

    def watch() -> None:
        step = flayer.follower.step
        if step is not None and step.move is Move.CLIMB:
            beside.append(abs(flayer.feet.x - LOW_WINDOW.left))
        assert _upright(flayer)

    run(world, 20.0, until=lambda: not flayer.follower.moving, each=watch)
    assert beside and min(beside) > WALL_GAP - 1.0
    assert flayer.contact().y == LOW_WINDOW.top


def test_it_floats_upright_just_under_a_window_underside():
    world = world_with()
    flayer = world.add_mindflayer(Vec2(450, WINDOW.top))
    under = next(s for s in world.planner.surfaces if s.hanging and s.box == 0)
    from dungeons_desktops.navigation.planner import Anchor

    flayer.follower.reset(Anchor(under, under.point_at(360)))
    flayer.feet = flayer._float_target()
    flayer._go(under.point_at(560))
    run(world, 1.0)
    assert flayer.follower.step.move is Move.HANG
    head = flayer.transforms()[flayer.layout.head].end
    top = head.y - flayer.layout.head_radius
    assert _upright(flayer)
    assert WINDOW.bottom < top < WINDOW.bottom + CEILING_GAP + 2.0


# ----- the desktop rotation -------------------------------------------------------------


def test_the_desktop_rotates_once_the_flayer_dies_leaving_its_minions_fighting():
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(400, 400, 400, 200))])
    world = DesktopSession(
        screen, usable, source, seed=2, max_stickmen=0, defenders=("mindflayer", "worm")
    )
    assert world.defender == "mindflayer" and len(world.mindflayers) == 1
    flayer = world.mindflayers[0]
    thrall = thrall_in(world, Vec2(100, usable.bottom))
    world.spawn_devourer(Vec2(1200, usable.bottom - 30))
    assert world.defender_health == 1.0
    world.hurt_monster(flayer, 3, flayer.center(), Vec2(0, -40))
    assert world.defender_health == (MIND_FLAYER_HP - 3) / MIND_FLAYER_HP
    world.hurt_monster(flayer, MIND_FLAYER_HP - 3, flayer.center(), Vec2(0, -40))
    run(world, 0.1)
    assert world.defender == "worm" and len(world.worms) == 1
    assert world.defender_health == 1.0
    assert thrall.thrall and thrall in world.thralls and len(world.devourers) == 1
    assert not math.isnan(world.defender_health or 0.0)


def test_rotating_on_early_frees_the_thralls():
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    world = DesktopSession(
        screen,
        usable,
        FakeWindowSource([]),
        seed=2,
        max_stickmen=0,
        defenders=("mindflayer", "worm"),
    )
    thrall = thrall_in(world, Vec2(100, usable.bottom))
    world.rotate()
    assert world.defender == "worm" and not world.mindflayers
    assert not thrall.thrall and thrall.prey and thrall.wander


def test_legendary_blast_blinks_in_and_starts_a_grab():
    from dungeons_desktops.game.defenders.legendary import apply_legendary

    world = world_with()
    flayer = world.add_mindflayer(Vec2(450, WINDOW.top), legendary=True)
    apply_legendary(flayer)
    flayer.blast_cooldown = flayer.pulse_cooldown = 99.0
    victim = world.add_stickman(Vec2(150, FLOOR), "barbarian")
    before = flayer.center()
    flayer.bolts.append(Bolt(victim.center() + Vec2(10, 0), victim))
    assert run(world, 1.0, until=lambda: flayer.power is Power.GRAB)
    assert victim.paralysed and flayer.victim is victim
    assert flayer.center().distance_to(before) > 40.0
    assert flayer.center().distance_to(victim.center()) < 80.0


def _open_ritual_rift(world, flayer, offset: float = 0.0):
    group = [thrall_in(world, Vec2(140 + offset + i * 35, FLOOR)) for i in range(3)]
    assert run(world, 1.0, until=lambda: flayer.ritual_point is not None)
    point = flayer.ritual_point
    assert point is not None
    for thrall in group:
        thrall.follower.reset(world.planner.anchor_near(point, walk_only=True))
        thrall.goal = point
    before = len(flayer.rifts)
    assert run(world, 5.0, until=lambda: len(flayer.rifts) > before)
    return flayer.rifts[-1]


def test_legendary_thrall_ritual_opens_a_sentry_rift():
    from dungeons_desktops.game.defenders.legendary import apply_legendary
    from dungeons_desktops.game.defenders.mindflayer.rift import RIFT_OPEN_TIME

    world = world_with([], seed=2)
    flayer = world.add_mindflayer(Vec2(200, FLOOR), legendary=True)
    apply_legendary(flayer)
    rift = _open_ritual_rift(world, flayer)
    assert run(world, RIFT_OPEN_TIME + 0.2, until=lambda: rift.opened)
    assert rift.strike is None
    assert rift.eaten == 0


def _force_seize(rift, victim, world):
    from dungeons_desktops.game.defenders.mindflayer.rift import RiftStrike, _seize

    strike = RiftStrike(tip=victim.center(), phase=0.0)
    rift.strike = strike
    _seize(rift, strike, victim, world)


def test_rift_sentry_drags_adventurers_through_and_spawns_aboleth_after_five():
    from dungeons_desktops.game.defenders.aboleth.actor import ABOLETH_HP, EMERGE_TIME
    from dungeons_desktops.game.defenders.legendary import apply_legendary
    from dungeons_desktops.game.defenders.mindflayer.rift import (
        ABOLETH_DELIVER_HOLD,
        RIFT_MEALS,
        RIFT_OPEN_TIME,
    )

    world = world_with([], seed=4)
    flayer = world.add_mindflayer(Vec2(200, FLOOR), legendary=True)
    apply_legendary(flayer)
    rift = _open_ritual_rift(world, flayer)
    assert run(world, RIFT_OPEN_TIME + 0.2, until=lambda: rift.opened)
    victims = [world.add_stickman(Vec2(300 + i * 20, FLOOR), "fighter") for i in range(RIFT_MEALS)]
    start_x = victims[0].center().x

    _force_seize(rift, victims[0], world)
    assert not victims[0].animated and not victims[0].prey
    assert victims[0].rift_held_by is rift
    assert run(world, 3.0, until=lambda: abs(victims[0].center().x - start_x) > 20.0)
    assert victims[0].center().x < start_x
    assert run(world, 8.0, until=lambda: rift.eaten >= 1)
    assert victims[0].swallowed and victims[0].gone
    assert victims[0] not in world.stickmen
    for victim in victims[1:]:
        assert rift.strike is None
        _force_seize(rift, victim, world)
        before = rift.eaten
        assert run(world, 10.0, until=lambda eaten=before: rift.eaten > eaten)
        assert victim.swallowed and victim.gone
    assert rift.eaten >= RIFT_MEALS == 5
    assert rift.delivered
    assert flayer.herald_aboleth is not None
    assert flayer.herald_aboleth in world.aboleths
    assert flayer.herald_aboleth.max_hp == ABOLETH_HP
    assert flayer.herald_aboleth.emerge is not None
    assert run(world, ABOLETH_DELIVER_HOLD + EMERGE_TIME + 0.2, until=lambda: rift not in flayer.rifts)
    assert flayer.herald_aboleth.emerge is None


def test_rift_lashes_within_reach_and_eats_thralls():
    from dungeons_desktops.game.actors.hunting import nearest
    from dungeons_desktops.game.defenders.legendary import apply_legendary
    from dungeons_desktops.game.defenders.mindflayer.rift import (
        RIFT_OPEN_TIME,
        SENTRY_REACH,
    )

    world = world_with([], seed=6)
    flayer = world.add_mindflayer(Vec2(200, FLOOR), legendary=True)
    apply_legendary(flayer)
    rift = _open_ritual_rift(world, flayer)
    assert run(world, RIFT_OPEN_TIME + 0.2, until=lambda: rift.opened)
    thrall = world.add_stickman(Vec2(rift.center.x + SENTRY_REACH * 0.4, FLOOR), "fighter")
    thrall.enthrall()
    free = world.add_stickman(Vec2(rift.center.x + SENTRY_REACH + 80.0, FLOOR), "fighter")
    assert run(world, 2.0, until=lambda: rift.strike is not None and rift.strike.victim is thrall)
    assert thrall.rift_held_by is rift and not thrall.prey
    hunt = nearest()
    assert hunt.update(0.0, rift.center, world.stickmen) is free
    before = rift.eaten
    assert run(world, 8.0, until=lambda: rift.eaten > before)
    assert thrall.swallowed and thrall.gone
    assert thrall not in world.stickmen


def test_thralls_wait_for_aboleth_banish_before_opening_another_rift():
    from dungeons_desktops.game.defenders.aboleth.actor import (
        BANISH_CLOSE,
        BANISH_OPEN,
        BANISH_SWIM,
    )
    from dungeons_desktops.game.defenders.legendary import apply_legendary

    world = world_with([], seed=3)
    flayer = world.add_mindflayer(Vec2(200, FLOOR), legendary=True)
    apply_legendary(flayer)
    _open_ritual_rift(world, flayer, 0.0)
    assert len(flayer.rifts) == 1

    # Extra thralls cannot tear a second rift while the first is still open.
    group = [thrall_in(world, Vec2(400 + i * 35, FLOOR)) for i in range(3)]
    run(world, 2.0)
    assert flayer.ritual_point is None
    assert len(flayer.rifts) == 1

    # Deliver an aboleth directly (as the fifth meal would) and seal the tear.
    from dungeons_desktops.game.defenders.mindflayer.rift import RIFT_MEALS

    rift = flayer.rifts[0]
    rift.eaten = RIFT_MEALS
    assert run(world, 0.1, until=lambda: rift.delivered and flayer.herald_aboleth is not None)
    aboleth = flayer.herald_aboleth
    assert aboleth is not None
    rift.close_after = rift.age
    assert run(world, 1.0, until=lambda: rift not in flayer.rifts)
    assert flayer.herald_aboleth is aboleth

    # Still blocked while the aboleth lives.
    for thrall in group:
        if thrall in world.stickmen:
            thrall.ritual_bound = False
            thrall.ritual_goal = None
    run(world, 1.5)
    assert flayer.ritual_point is None
    assert not flayer.rifts

    # Banishing the aboleth frees the herald to open another tear.
    world.hurt_monster(aboleth, aboleth.max_hp, aboleth.center(), Vec2(0.0, 0.0))
    assert aboleth.banishing and aboleth.portal is not None
    assert flayer.herald_aboleth is aboleth
    assert run(
        world,
        BANISH_OPEN + BANISH_SWIM + BANISH_CLOSE + 0.2,
        until=lambda: aboleth.gone and flayer.herald_aboleth is None,
    )

    fresh = [thrall_in(world, Vec2(160 + i * 35, FLOOR)) for i in range(3)]
    assert run(world, 1.0, until=lambda: flayer.ritual_point is not None)
    point = flayer.ritual_point
    for thrall in fresh:
        thrall.follower.reset(world.planner.anchor_near(point, walk_only=True))
        thrall.goal = point
    assert run(world, 5.0, until=lambda: len(flayer.rifts) >= 1)
