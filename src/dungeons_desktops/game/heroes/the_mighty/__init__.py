"""The Mighty, the barbarian hero."""

from importlib import import_module

__all__ = ["TheMighty"]


def __getattr__(name: str):
    if name == "TheMighty":
        return import_module("dungeons_desktops.game.heroes.the_mighty.actor").TheMighty
    raise AttributeError(name)
