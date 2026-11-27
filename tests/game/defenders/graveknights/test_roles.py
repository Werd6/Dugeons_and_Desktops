"""The Graveknight squad's four permanent, independently tunable roles."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.graveknights import actor as graveknight_actor
from dungeons_desktops.game.defenders.graveknights.actor import (
    GRAVEKNIGHT_ROSTER,
    GRAVEKNIGHT_STATS,
    GraveknightRole,
    GraveknightStats,
)
from dungeons_desktops.game.defenders.graveknights.equipment import GraveSwordAndShield
from dungeons_desktops.game.defenders.graveknights.render import (
    BREASTPLATE,
    BREASTPLATE_DARK,
    BREASTPLATE_SILVER,
    FAR,
    SKIN,
    draw_graveknight,
    draw_graveknights,
)
from dungeons_desktops.game.heroes.hero_sorcerer.weapon import SkullFocus
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.rig.equipment import Axe, Bow

DT = 1 / 60
FLOOR = 600.0
SQUAD_POINT = Vec2(200.0, FLOOR)
ROLES = (
    GraveknightRole.ARCHER,
    GraveknightRole.FIGHTER,
    GraveknightRole.MAGE,
    GraveknightRole.BARBARIAN,
)
STAT_FIELDS = {
    "HP": "hp",
    "DAMAGE": "damage",
    "COOLDOWN": "cooldown",
    "RANGE": "attack_range",
    "PUSH": "push",
    "MOVE_SPEED": "move_speed",
    "STANDOFF": "standoff",
}


def squad(world: SimWorld, point: Vec2 = SQUAD_POINT):
    knights = world.add_graveknights(point)
    return {knight.role: knight for knight in knights}


def advance_until(world: SimWorld, condition, seconds: float = 6.0) -> None:
    for _ in range(round(seconds / DT)):
        world.advance(DT)
        if condition():
            return
    pytest.fail("condition did not become true")


def test_squad_musters_one_of_each_role_in_fixed_order_with_independent_stats():
    world = SimWorld([], FLOOR, 1400, seed=31)
    knights = world.add_graveknights(Vec2(200.0, FLOOR))

    assert GRAVEKNIGHT_ROSTER == ROLES
    assert tuple(knight.role for knight in knights) == ROLES
    assert set(GRAVEKNIGHT_STATS) == set(ROLES)
    assert len({id(GRAVEKNIGHT_STATS[role]) for role in ROLES}) == len(ROLES)

    for knight in knights:
        stats = GRAVEKNIGHT_STATS[knight.role]
        expected = {
            field: getattr(graveknight_actor, f"{knight.role.name}_{constant}")
            for constant, field in STAT_FIELDS.items()
        }
        assert stats == GraveknightStats(**expected)
        assert knight.stats is stats
        assert knight.max_hp == knight.hp == stats.hp
        assert knight.attack_damage == stats.damage
        assert knight.attack_cooldown == stats.cooldown
        assert knight.attack_range == stats.attack_range
        assert knight.attack_push == stats.push
        assert knight.move_speed == stats.move_speed
        assert knight.standoff == stats.standoff
        assert stats.damage > 0
        assert stats.cooldown > 0.0
        assert stats.attack_range > 0.0
        assert stats.push > 0.0
        assert stats.move_speed > 0.0


def test_each_role_keeps_its_own_weapon():
    world = SimWorld([], FLOOR, 1400, seed=32)
    knights = squad(world)
    expected = {
        GraveknightRole.ARCHER: Bow,
        GraveknightRole.FIGHTER: GraveSwordAndShield,
        GraveknightRole.MAGE: SkullFocus,
        GraveknightRole.BARBARIAN: Axe,
    }
    original_weapons = {role: knight.weapon for role, knight in knights.items()}

    prey = world.add_stickman(Vec2(230.0, FLOOR))
    prey.paralyze(30.0)
    for _ in range(120):
        world.advance(DT)

    for role, weapon_type in expected.items():
        assert isinstance(knights[role].weapon, weapon_type)
        assert knights[role].weapon is original_weapons[role]


def test_all_four_role_loadouts_render_together():
    world = SimWorld([], FLOOR, 1400, seed=43)
    knights = world.add_graveknights(Vec2(300.0, FLOOR))
    image = QImage(800, 700, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)

    draw_graveknights(painter, knights)

    assert painter.end()
    assert not image.isNull()


@pytest.mark.parametrize("role", ROLES)
def test_every_role_wears_the_hero_fighters_breastplate(role):
    world = SimWorld([], FLOOR, 800, seed=44)
    knight = world.add_graveknight(Vec2(300.0, FLOOR), role)
    image = QImage(800, 700, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)

    draw_graveknight(painter, knight)
    painter.end()

    colors = {
        image.pixelColor(x, y).name()
        for x in range(250, 350)
        for y in range(520, 620)
        if image.pixelColor(x, y).alpha()
    }
    plate_colors = {
        BREASTPLATE.name(),
        BREASTPLATE_DARK.name(),
        BREASTPLATE_SILVER.name(),
    }
    assert plate_colors <= colors
    assert plate_colors.isdisjoint({SKIN.name(), FAR.name()})


def test_archer_fires_while_advancing_and_never_switches_to_melee():
    world = SimWorld([], FLOOR, 1400, seed=33)
    knights = squad(world, Vec2(100.0, FLOOR))
    archer = knights[GraveknightRole.ARCHER]
    prey = world.add_stickman(Vec2(400.0, FLOOR))
    prey.paralyze(30.0)
    archer.cooldown = 0.0
    for role, knight in knights.items():
        if role is not GraveknightRole.ARCHER:
            knight.cooldown = 99.0
    weapon = archer.weapon
    start = archer.contact()
    moved_while_drawing = 0.0
    previous = start

    def fired_and_advanced() -> bool:
        nonlocal moved_while_drawing, previous
        if weapon.busy:
            moved_while_drawing += archer.contact().distance_to(previous)
        previous = archer.contact()
        fired = any(arrow.owner is archer for arrow in world.spells.arrows)
        return fired and archer.contact().x > start.x + 15.0

    advance_until(world, fired_and_advanced)

    assert isinstance(archer.weapon, Bow)
    assert archer.weapon is weapon
    assert moved_while_drawing > 5.0


def test_mage_casts_the_hero_sorcerers_harming_bolt_at_prey():
    world = SimWorld([], FLOOR, 1400, seed=34)
    knights = squad(world, Vec2(200.0, FLOOR))
    mage = knights[GraveknightRole.MAGE]
    prey = world.add_stickman(Vec2(400.0, FLOOR))
    prey.paralyze(30.0)
    for knight in knights.values():
        knight.cooldown = 99.0
    mage.cooldown = 0.0
    missile = None

    def bolt_released() -> bool:
        nonlocal missile
        missile = next(
            (candidate for candidate in world.spells.missiles if candidate.owner is mage),
            None,
        )
        return missile is not None

    advance_until(world, bolt_released)

    assert isinstance(mage.weapon, SkullFocus)
    assert missile is not None
    assert missile.kind == "life_drain"
    assert missile.hostile
    assert missile.monster is prey

    advance_until(world, lambda: prey.damage > 0)
    assert prey.damage == mage.stats.damage


@pytest.mark.parametrize(
    ("role", "weapon_type"),
    (
        (GraveknightRole.FIGHTER, GraveSwordAndShield),
        (GraveknightRole.BARBARIAN, Axe),
    ),
)
def test_melee_roles_close_and_hit_with_their_permanent_weapon(role, weapon_type):
    world = SimWorld([], FLOOR, 900, seed=35)
    knights = squad(world, Vec2(400.0, FLOOR))
    attacker = knights[role]
    prey = world.add_stickman(Vec2(attacker.contact().x + 18.0, FLOOR))
    prey.paralyze(30.0)
    for knight in knights.values():
        knight.cooldown = 99.0
    attacker.cooldown = 0.0
    weapon = attacker.weapon

    advance_until(world, lambda: prey.damage > 0, seconds=3.0)

    assert isinstance(attacker.weapon, weapon_type)
    assert attacker.weapon is weapon
    assert prey.damage == attacker.stats.damage
