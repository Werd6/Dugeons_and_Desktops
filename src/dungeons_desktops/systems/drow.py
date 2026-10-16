"""Compatibility alias for :mod:`dungeons_desktops.game.defenders.drow.actor`."""

from dungeons_desktops._compat import moved_module

_target = moved_module(__name__, "dungeons_desktops.game.defenders.drow.actor")
globals().update(_target.__dict__)
