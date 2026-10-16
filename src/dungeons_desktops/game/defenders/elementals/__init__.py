"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.elementals.actor import (
    ELEMENTAL_HP,
    Elemental,
)

__all__ = ['Elemental', 'ELEMENTAL_HP', 'draw_elemental', 'draw_elementals']

def __getattr__(name: str):
    if name in {'draw_elementals', 'draw_elemental'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.elementals.render"), name)
    raise AttributeError(name)
