"""The ranger hero and his carried firearms."""

from importlib import import_module

__all__ = ["TheHunter"]


def __getattr__(name: str):
    if name == "TheHunter":
        return import_module("dungeons_desktops.game.heroes.the_hunter.actor").TheHunter
    raise AttributeError(name)
