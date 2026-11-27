"""The Paladin hero's model and shared adventurer combat."""

from importlib import import_module

__all__ = ["HeroPaladin"]


def __getattr__(name: str):
    if name == "HeroPaladin":
        return import_module("dungeons_desktops.game.heroes.hero_paladin.actor").HeroPaladin
    raise AttributeError(name)
