"""Stick-figure adventurer: bone data, limb chains and classes, viewed from the side
facing +x.

A small, bobble-headed figure: stubby limbs and a head about a third of its height.
Every length below (bones, gait, navigation reach) is the reference size times
`SCALE`, so the whole figure, its timing and its weapons resize together.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dungeons_desktops.game.adventurers.weapons import (
    Axe,
    Bombs,
    Bow,
    Daggers,
    DruidStaff,
    FighterSword,
    FireOrb,
    HammerAndShield,
    HolyStaff,
    Wand,
)
from dungeons_desktops.game.heroes.dio.weapon import HeroTridentAndShield
from dungeons_desktops.navigation.planner import MoveSettings
from dungeons_desktops.rig.biped import UP, BipedLayout
from dungeons_desktops.rig.climb import ClimbSettings
from dungeons_desktops.rig.equipment import Weapon
from dungeons_desktops.rig.ik import IkChain
from dungeons_desktops.rig.skeleton import BoneDef, Skeleton
from dungeons_desktops.rig.walk import WalkSettings

SCALE = 0.5

RUN = WalkSettings(
    speed=100.0 * SCALE,
    stride=40.0 * SCALE,
    stance_fraction=0.35,
    step_height=7.0 * SCALE,
    hip_bob=1.5 * SCALE,
    lean=0.22,
    arm_swing=0.9,
    arm_reach=0.6,
    stance_width=1.5 * SCALE,
    acceleration=6.0,
    crouch=0.08,
    heel_kick=0.7,
    arm_forward=0.25,
)
CLIMB = ClimbSettings(
    stride=18.0 * SCALE,
    hip_offset=12.0 * SCALE,
    hip_above_contact=12.0 * SCALE,
    hand_above_hip=27.0 * SCALE,
    grip_inset=1.5 * SCALE,
    pull_off=2.5 * SCALE,
    lean=0.0,
    ledge_reach=3.0 * SCALE,
    head_tilt=-0.2,
)
MOVES = MoveSettings(
    walk_speed=100.0 * SCALE,
    climb_speed=28.0 * SCALE,
    hang_speed=56.0 * SCALE,
    max_jump=50.0 * SCALE,
    edge_clearance=6.0 * SCALE,
)
HANG_REACH = 16.0 * SCALE
MANTLE_DEPTH = 26.0 * SCALE
HANG_DEPTH = 52.0 * SCALE
"""Hands to feet when hanging from a ceiling (matches `hang.hang_depth` of the figure)."""


BASE_HP = 4
"""Every adventurer's HP unless its class says otherwise."""


@dataclass(frozen=True)
class Calling:
    """An adventurer's class: what it carries and how it fights."""

    weapon: type[Weapon] | None
    hp: int = BASE_HP
    speed: float = 1.0
    """Multiplier on how fast it gets through its routes."""
    reach: float = 0.0
    """How close a monster must be before it attacks (0: never does)."""
    cooldown: float = 1.0


WIZARD_REACH = 280.0
CAST_COOLDOWN = 2.2
PALADIN_COOLDOWN = 1.0


CLASSES: dict[str, Calling] = {
    "barbarian": Calling(Axe, hp=2 * BASE_HP, reach=30.0, cooldown=0.9),
    "wizard": Calling(Wand, reach=WIZARD_REACH, cooldown=CAST_COOLDOWN),
    "rogue": Calling(Daggers, speed=1.5, reach=24.0, cooldown=0.5),
    "paladin": Calling(HammerAndShield, hp=2 * BASE_HP, reach=30.0, cooldown=PALADIN_COOLDOWN),
    "ranger": Calling(Bow, reach=340.0, cooldown=1.6),
    "cleric": Calling(HolyStaff, cooldown=3.0),
    "alchemist": Calling(Bombs, reach=230.0, cooldown=1.8),
    "druid": Calling(DruidStaff, reach=60.0, cooldown=1.4),
    "sorcerer": Calling(FireOrb, reach=WIZARD_REACH, cooldown=CAST_COOLDOWN),
    "fighter": Calling(FighterSword, hp=2 * BASE_HP, reach=30.0, cooldown=PALADIN_COOLDOWN / 2),
}
"""The adventurer classes that invade the desktop."""
HEROES: dict[str, Calling] = {
    "hero_fighter": Calling(
        HeroTridentAndShield,
        hp=60,
        reach=38.0,
        cooldown=0.8,
    ),
}
"""Named heroes, available explicitly rather than in the ordinary invader pool."""
CALLINGS: dict[str, Calling] = {"unarmed": Calling(None), **CLASSES, **HEROES}


def make_weapon(variant: str, layout: BipedLayout) -> Weapon | None:
    weapon = CALLINGS[variant].weapon
    return weapon(layout) if weapon is not None else None


def _limbs(side: str) -> tuple[BoneDef, ...]:
    s = SCALE
    return (
        BoneDef(f"upper_arm_{side}", "torso", 9.0 * s, math.pi, -3.0, 3.0, mass=0.6),
        BoneDef(f"lower_arm_{side}", f"upper_arm_{side}", 8.0 * s, 0.0, -2.6, 0.0, mass=0.45),
        BoneDef(
            f"upper_leg_{side}",
            "pelvis",
            10.0 * s,
            math.pi,
            -2.0,
            0.6,
            mass=1.5,
            from_parent_start=True,
        ),
        BoneDef(f"lower_leg_{side}", f"upper_leg_{side}", 10.0 * s, 0.0, 0.0, 2.6, mass=1.1),
    )


def build_stick_figure() -> BipedLayout:
    s = SCALE
    bones = (
        BoneDef("pelvis", None, 5.0 * s, UP, mass=2.0),
        BoneDef("torso", "pelvis", 14.0 * s, 0.0, -0.6, 0.6, mass=3.0),
        BoneDef("head", "torso", 10.0 * s, 0.0, -0.8, 0.8, mass=3.0),
        *_limbs("l"),
        *_limbs("r"),
    )
    return BipedLayout(
        skeleton=Skeleton(bones),
        pelvis="pelvis",
        torso="torso",
        head="head",
        legs=(
            IkChain("leg_l", ("upper_leg_l", "lower_leg_l"), bend=1),
            IkChain("leg_r", ("upper_leg_r", "lower_leg_r"), bend=1),
        ),
        arms=(
            IkChain("arm_l", ("upper_arm_l", "lower_arm_l"), bend=-1),
            IkChain("arm_r", ("upper_arm_r", "lower_arm_r"), bend=-1),
        ),
        head_radius=9.0 * s,
        walk=RUN,
        climb=CLIMB,
        scale=s,
    )
