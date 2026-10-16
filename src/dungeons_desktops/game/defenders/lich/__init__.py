"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.lich.actor import (
    LICH_HP,
    Lich,
)

__all__ = ['Lich', 'LICH_HP', 'draw_lich', 'draw_liches']

def __getattr__(name: str):
    if name in {'draw_lich', 'draw_liches'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.lich.render"), name)
    raise AttributeError(name)
