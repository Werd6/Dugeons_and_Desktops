"""The cleric hero."""

from importlib import import_module

__all__ = ["HeroCleric"]


def __getattr__(name: str):
    if name == "HeroCleric":
        return import_module("dungeons_desktops.game.heroes.hero_cleric.actor").HeroCleric
    raise AttributeError(name)
