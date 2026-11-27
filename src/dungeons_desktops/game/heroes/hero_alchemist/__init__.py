"""The Hero Alchemist."""

from importlib import import_module

__all__ = ["HeroAlchemist"]


def __getattr__(name: str):
    if name == "HeroAlchemist":
        return import_module(
            "dungeons_desktops.game.heroes.hero_alchemist.actor"
        ).HeroAlchemist
    raise AttributeError(name)
