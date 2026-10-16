"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.displacer.actor import (
    DISPLACER_HP,
    Displacer,
)

__all__ = ['Displacer', 'DISPLACER_HP', 'draw_displacer', 'draw_displacers']

def __getattr__(name: str):
    if name in {'draw_displacer', 'draw_displacers'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.displacer.render"), name)
    raise AttributeError(name)
