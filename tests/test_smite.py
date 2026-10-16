from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.mortal import LICH_HP
from dungeons_desktops.game.defenders.lich.spells import (
    SMITE_DAMAGE,
    SMITE_DROP,
    SMITE_HANG,
    SMITE_LINGER,
    SMITE_STAGGER,
    WORD_DELAY,
)
from dungeons_desktops.game.world.simulation import SimWorld

STEP = 1 / 60
FLOOR = 700.0
STRIKE = SMITE_HANG + SMITE_DROP


def setup(*clerics: float, variant: str = "cleric"):
    world = SimWorld([], FLOOR, 1400.0, ceiling=20.0, seed=3)
    lich = world.add_lich(Vec2(200, FLOOR))
    lich.cast_wait = lich.door_wait = 1e9
    men = []
    for x in clerics:
        man = world.add_stickman(Vec2(x, FLOOR), variant)
        man.wander = False
        man.paralyze(30.0)
        men.append(man)
    return world, lich, men


def run(world: SimWorld, seconds: float, each=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()


def word(world: SimWorld, lich, foe) -> None:
    world.necromancy.cast("power_word_kill", lich, lich.flame_point(), foe)
    run(world, WORD_DELAY + 2 * STEP)


def test_slaying_a_cleric_brings_down_a_sword_of_light_for_smite_damage():
    world, lich, (cleric,) = setup(500)
    word(world, lich, cleric)
    assert not cleric.animated and len(world.necromancy.smites) == 1
    run(world, STRIKE - 0.1)
    assert lich.hp == LICH_HP
    smite = world.necromancy.smites[0]
    assert abs(smite.x - lich.center().x) < 1.0 and smite.top < lich.center().y - 150
    run(world, 0.2)
    assert lich.hp == LICH_HP - SMITE_DAMAGE and world.necromancy.smitten == 1
    run(world, SMITE_LINGER + 1.0)
    assert lich.hp == LICH_HP - SMITE_DAMAGE and not world.necromancy.smites
    assert world.necromancy.risings or world.skeletons


def test_slaying_anyone_else_brings_no_smite():
    world, lich, (wizard,) = setup(500, variant="wizard")
    word(world, lich, wizard)
    assert not wizard.animated
    run(world, 2.0)
    assert not world.necromancy.smites and lich.hp == LICH_HP


def test_a_cleric_slain_by_something_else_brings_no_smite():
    world, lich, (cleric,) = setup(500)
    cleric.hurt(99, cleric.center(), Vec2(0, 0), "skeleton", "Hacked down by a skeleton!")
    world.necromancy.cast("fireball", None, Vec2(300, 650), cleric)
    run(world, 3.0)
    assert not cleric.animated
    assert not world.necromancy.smites and lich.hp == LICH_HP


def test_the_sword_fades_harmlessly_if_the_lich_dies_first():
    world, lich, (cleric,) = setup(500)
    word(world, lich, cleric)
    assert world.necromancy.smites
    world.hurt_monster(lich, LICH_HP, lich.center(), Vec2(0, 0))
    assert lich.dead
    run(world, 2.0)
    assert not world.necromancy.smites and world.necromancy.smitten == 0


def test_two_clerics_two_smites_one_after_the_other():
    world, lich, clerics = setup(500, 515)
    drops: list[float] = []
    clock = [0.0]
    last = [lich.hp]

    def watch():
        clock[0] += STEP
        if lich.hp < last[0]:
            drops.append(clock[0])
        last[0] = lich.hp

    world.necromancy.cast("fireball", lich, lich.flame_point(), clerics[0])
    run(world, 4.0, each=watch)
    assert all(not c.animated for c in clerics)
    assert len(drops) == 2
    assert lich.dead if 2 * SMITE_DAMAGE >= LICH_HP else lich.hp == LICH_HP - 2 * SMITE_DAMAGE
    assert drops[1] - drops[0] >= SMITE_STAGGER - STEP


def test_it_waits_for_him_to_come_out_of_a_dimension_door():
    world, lich, _ = setup()
    far = world.add_stickman(Vec2(1300, FLOOR), "wizard")
    far.wander = False
    far.paralyze(30.0)
    lich.door_wait = 0.0
    assert run_until(world, lambda: lich.door is not None)
    world.necromancy.smite(lich)
    struck: list[bool] = []
    last = [lich.hp]

    def watch():
        if lich.hp < last[0]:
            struck.append(lich.door is None)
        last[0] = lich.hp

    run(world, 3.0, each=watch)
    assert lich.doors == 1 and struck == [True] and lich.hp == LICH_HP - SMITE_DAMAGE


def run_until(world: SimWorld, until, seconds: float = 3.0) -> bool:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if until():
            return True
    return False
