"""The Slayer, the rogue hero."""

from importlib import import_module

__all__ = ["TheSlayer"]


def __getattr__(name: str):
    if name == "TheSlayer":
        return import_module("dungeons_desktops.game.heroes.the_slayer.actor").TheSlayer
    raise AttributeError(name)
