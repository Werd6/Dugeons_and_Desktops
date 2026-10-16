"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.mimic.actor import (
    MIMIC_HP,
    Mimic,
)

__all__ = ['Mimic', 'MIMIC_HP', 'draw_mimic', 'draw_mimics']

def __getattr__(name: str):
    if name in {'draw_mimics', 'draw_mimic'}:
        from importlib import import_module

        return getattr(import_module("dungeons_desktops.game.defenders.mimic.render"), name)
    raise AttributeError(name)
