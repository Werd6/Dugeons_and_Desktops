"""Compatibility alias for :mod:`dungeons_desktops.game.actors.floating`."""

from dungeons_desktops._compat import moved_module

_target = moved_module(__name__, "dungeons_desktops.game.actors.floating")
globals().update(_target.__dict__)
