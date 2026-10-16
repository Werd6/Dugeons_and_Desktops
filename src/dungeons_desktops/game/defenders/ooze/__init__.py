"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.ooze.actor import (
    OOZE_HP,
    Ooze,
)

__all__ = ['Ooze', 'OOZE_HP', 'draw_ooze', 'draw_oozes']

def __getattr__(name: str):
    if name in {'draw_ooze', 'draw_oozes'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.ooze.render"), name)
    raise AttributeError(name)
