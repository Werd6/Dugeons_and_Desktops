"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.hydra.actor import (
    HYDRA_HP,
    Hydra,
)

__all__ = ['Hydra', 'HYDRA_HP', 'draw_hydra', 'draw_hydras']

def __getattr__(name: str):
    if name in {'draw_hydras', 'draw_hydra'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.hydra.render"), name)
    raise AttributeError(name)
