"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.drow.actor import (
    DROW_HP,
    LIZARD_HP,
    Drow,
    DrowPack,
    Lizard,
)

__all__ = ['Drow', 'DrowPack', 'Lizard', 'DROW_HP', 'LIZARD_HP', 'draw_drow', 'draw_lizards']

def __getattr__(name: str):
    if name in {'draw_drow', 'draw_lizards'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.drow.render"), name)
    raise AttributeError(name)
