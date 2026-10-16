"""Compatibility alias for :mod:`dungeons_desktops.game.defenders.drow.render`."""

from dungeons_desktops._compat import moved_module

_target = moved_module(__name__, "dungeons_desktops.game.defenders.drow.render")
globals().update(_target.__dict__)
