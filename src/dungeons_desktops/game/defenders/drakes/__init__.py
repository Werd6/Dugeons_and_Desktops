"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.drakes.drake import (
    DRAKE_HP,
    Drake,
)

__all__ = ['Drake', 'DRAKE_HP', 'draw_drake', 'draw_drakes']

def __getattr__(name: str):
    if name in {'draw_drake', 'draw_drakes'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.drakes.render"), name)
    raise AttributeError(name)
