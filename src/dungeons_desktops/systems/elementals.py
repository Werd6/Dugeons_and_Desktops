"""Compatibility alias for :mod:`dungeons_desktops.game.defenders.elementals.actor`."""

from dungeons_desktops._compat import moved_module

_target = moved_module(__name__, "dungeons_desktops.game.defenders.elementals.actor")
globals().update(_target.__dict__)
