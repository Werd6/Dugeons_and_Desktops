"""Compatibility alias for :mod:`dungeons_desktops.game.defenders.drakes.kobold`."""

from dungeons_desktops._compat import moved_module

_target = moved_module(__name__, "dungeons_desktops.game.defenders.drakes.kobold")
globals().update(_target.__dict__)
