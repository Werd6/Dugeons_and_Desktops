"""Adventurer weapon models and animation layers."""

from dungeons_desktops.rig.equipment import (
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

__all__ = [
    "Axe",
    "Bombs",
    "Bow",
    "Daggers",
    "DruidStaff",
    "FighterSword",
    "FireOrb",
    "HammerAndShield",
    "HolyStaff",
    "Wand",
]

for _name in __all__:
    globals()[_name].__module__ = __name__
del _name
