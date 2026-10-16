"""Compatibility alias for :mod:`dungeons_desktops.render.scene`."""

from dungeons_desktops._compat import moved_module

_target = moved_module(__name__, "dungeons_desktops.render.scene")
globals().update(_target.__dict__)
