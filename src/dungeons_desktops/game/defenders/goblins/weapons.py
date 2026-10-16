"""Goblin swords, spears, and banner animation layers."""

from dungeons_desktops.rig.equipment import Banner, GoblinSword, SpearThrower

__all__ = ["Banner", "GoblinSword", "SpearThrower"]
for _name in __all__:
    globals()[_name].__module__ = __name__
del _name
