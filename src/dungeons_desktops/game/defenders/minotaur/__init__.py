"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.minotaur.actor import (
    MINOTAUR_HP,
    Minotaur,
)

__all__ = ['Minotaur', 'MINOTAUR_HP', 'draw_minotaur', 'draw_minotaurs']

def __getattr__(name: str):
    if name in {'draw_minotaurs', 'draw_minotaur'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.minotaur.render"), name)
    raise AttributeError(name)
