"""The Hero Sorcerer."""

from importlib import import_module

__all__ = ["HeroSorcerer"]


def __getattr__(name: str):
    if name == "HeroSorcerer":
        return import_module(
            "dungeons_desktops.game.heroes.hero_sorcerer.actor"
        ).HeroSorcerer
    raise AttributeError(name)
