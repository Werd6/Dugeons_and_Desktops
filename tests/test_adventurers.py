import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import DRAGON_DAMAGE, WORM_DAMAGE, StickMode
from dungeons_desktops.game.adventurers.model import BASE_HP, CLASSES
from dungeons_desktops.game.adventurers.spells import MISSILE_DARTS
from dungeons_desktops.game.world.simulation import KILL_MARK_TIME, SimWorld

DT = 1.0 / 60.0


def world_with(seed=3) -> SimWorld:
    return SimWorld([], 700.0, 1200.0, ceiling=20.0, seed=seed)


def run(world: SimWorld, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        world.advance(DT)


def test_base_hp_is_four_and_barbarians_paladins_and_fighters_have_double():
    world = world_with()
    hp = {name: world.add_stickman(Vec2(100, 700), name).max_hp for name in CLASSES}
    assert BASE_HP == 4
    assert hp == {
        "barbarian": 8,
        "wizard": 4,
        "rogue": 4,
        "paladin": 8,
        "ranger": 4,
        "cleric": 4,
        "alchemist": 4,
        "druid": 4,
        "sorcerer": 4,
        "fighter": 8,
    }


def test_a_dragon_hit_kills_a_wizard_but_a_barbarian_shrugs_it_off():
    world = world_with()
    wizard = world.add_stickman(Vec2(100, 700), "wizard")
    barbarian = world.add_stickman(Vec2(300, 700), "barbarian")
    push = Vec2(100, -50)
    assert wizard.hurt(DRAGON_DAMAGE, wizard.center(), push, "dragon", "dead")
    assert not barbarian.hurt(DRAGON_DAMAGE, barbarian.center(), push, "dragon", "dead")
    assert barbarian.animated and barbarian.hp == 8 - DRAGON_DAMAGE
    assert world.kills == 1


def test_one_burst_of_dragon_fire_only_lands_once():
    world = world_with()
    paladin = world.add_stickman(Vec2(300, 700), "paladin")
    for _ in range(5):
        paladin.hurt(DRAGON_DAMAGE, paladin.center(), Vec2(0, -50), "dragon", "dead")
        world.advance(DT)
    assert paladin.animated and paladin.damage == DRAGON_DAMAGE
    run(world, 1.1)
    assert paladin.hurt(DRAGON_DAMAGE, paladin.center(), Vec2(0, -50), "dragon", "dead")


def test_the_worm_kills_even_a_paladin_in_one_bite():
    world = world_with()
    paladin = world.add_stickman(Vec2(300, 700), "paladin")
    assert paladin.hurt(WORM_DAMAGE, paladin.center(), Vec2(0, -50), "worm", "eaten")
    assert paladin.mode is StickMode.RAGDOLL


def test_rogues_are_faster():
    world = world_with()
    rogue = world.add_stickman(Vec2(100, 700), "rogue")
    ranger = world.add_stickman(Vec2(100, 700), "ranger")
    for man in (rogue, ranger):
        man.set_goal(Vec2(1000, 700))
    run(world, 4.0)
    assert rogue.contact().x - 100 > 1.4 * (ranger.contact().x - 100)


def test_wizard_casts_a_weaving_three_dart_missile_at_a_goblin():
    world = world_with()
    wizard = world.add_stickman(Vec2(300, 700), "wizard", wander=True)
    goblin = world.add_goblin(Vec2(500, 700), "flag")
    cast = None
    swayed = 0.0
    for _ in range(int(3 / DT)):
        world.advance(DT)
        if world.spells.missiles:
            cast = world.spells.missiles[0]
            line_y = cast.origin.y + (cast.target.y - cast.origin.y) * 0.5
            swayed = max(swayed, *(abs(trail[-1].y - line_y) for trail in cast.darts))
        if cast is not None and not world.spells.missiles:
            break
    assert cast is not None and len(cast.darts) == MISSILE_DARTS
    assert cast.monster is goblin
    assert swayed > 5.0, "the darts should weave about the line"
    assert world.spells.sparks, "the missile bursts on arrival"
    assert wizard.facing == 1


def test_ranger_shoots_arrows_at_a_goblin():
    world = world_with()
    world.add_stickman(Vec2(300, 700), "ranger", wander=True)
    world.add_goblin(Vec2(560, 700), "flag")
    shot = False
    for _ in range(int(3 / DT)):
        world.advance(DT)
        shot |= any(a.velocity.x > 0 for a in world.spells.arrows)
    assert shot


@pytest.mark.parametrize("name", ["barbarian", "rogue", "paladin", "fighter"])
def test_melee_classes_swing_at_an_adjacent_goblin(name):
    world = world_with()
    fighter = world.add_stickman(Vec2(300, 700), name, wander=True)
    world.add_goblin(Vec2(318, 700), "flag")
    swung = False
    for _ in range(int(1.0 / DT)):
        world.advance(DT)
        swung |= fighter.weapon.busy
    assert swung


@pytest.mark.parametrize("name", ["barbarian", "wizard", "ranger", "sorcerer", "fighter"])
def test_turns_round_to_attack_a_monster_behind_it_even_when_not_wandering(name):
    world = world_with()
    fighter = world.add_stickman(Vec2(400, 700), name)
    fighter.follower.facing = 1
    world.add_goblin(Vec2(400 - (18 if name in ("barbarian", "fighter") else 150), 700), "flag")
    attacked = False
    for _ in range(int(1.0 / DT)):
        world.advance(DT)
        attacked |= fighter.weapon.busy
    assert attacked and fighter.facing == -1


def test_attacks_on_the_way_and_then_carries_on_to_its_goal():
    world = world_with()
    ranger = world.add_stickman(Vec2(200, 700), "ranger")
    world.add_goblin(Vec2(450, 700), "flag")
    ranger.set_goal(Vec2(800, 700))
    shot = False
    for _ in range(int(15 / DT)):
        world.advance(DT)
        if ranger.weapon.busy and world.goblins:
            shot = True
            world.goblins.clear()
        if ranger.contact().x > 790:
            break
    assert shot and ranger.contact().x > 790


def test_melee_reaches_the_dragon_body_not_just_its_middle():
    world = world_with()
    barbarian = world.add_stickman(Vec2(400, 700), "barbarian")
    dragon = world.add_dragon(Vec2(440, 690), facing=1)
    found = world.nearest_monster(barbarian.center(), 30.0)
    assert found is not None and found[0] is dragon


def test_cleric_heals_wounded_allies_with_a_pulse():
    world = world_with()
    world.add_stickman(Vec2(300, 700), "cleric", wander=True)
    hurt = world.add_stickman(Vec2(340, 700), "barbarian")
    far = world.add_stickman(Vec2(900, 700), "wizard")
    hurt.damage = far.damage = 3
    pulsed = False
    for _ in range(int(2 / DT)):
        world.advance(DT)
        pulsed |= bool(world.spells.pulses)
    assert pulsed
    assert hurt.damage < 3 and far.damage == 3


def test_a_kill_pops_a_skull_over_the_fallen_that_fades():
    world = world_with()
    stickman = world.add_stickman(Vec2(300, 700), "rogue")
    assert not stickman.hurt(1, stickman.center(), Vec2(0, -50), "goblin", "cut")
    assert not world.kill_marks, "only a kill pops one"
    assert stickman.hurt(99, stickman.center(), Vec2(0, -50), "goblin", "cut")
    assert len(world.kill_marks) == 1
    assert world.kill_marks[0].point.y < stickman.contact().y - 20
    run(world, KILL_MARK_TIME + 0.1)
    assert not world.kill_marks
