"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.chimera.actor import (
    CHIMERA_HP,
    Chimera,
)

__all__ = ['Chimera', 'CHIMERA_HP', 'draw_chimera', 'draw_chimeras']

def __getattr__(name: str):
    if name in {'draw_chimera', 'draw_chimeras'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.chimera.render"), name)
    raise AttributeError(name)
