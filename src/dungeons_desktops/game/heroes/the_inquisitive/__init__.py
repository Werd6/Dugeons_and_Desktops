"""Iggy the Inquisitive, the gnome wizard hero."""

from importlib import import_module

__all__ = ["Iggy"]


def __getattr__(name: str):
    if name == "Iggy":
        return import_module("dungeons_desktops.game.heroes.the_inquisitive.actor").Iggy
    raise AttributeError(name)
