"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.dragon.actor import (
    DRAGON_HP,
    Dragon,
    DragonMode,
)

__all__ = ['Dragon', 'DragonMode', 'DRAGON_HP', 'draw_dragon', 'draw_flames']

def __getattr__(name: str):
    if name in {'draw_flames', 'draw_dragon'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.dragon.render"), name)
    raise AttributeError(name)
