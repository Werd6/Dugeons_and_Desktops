"""The Soulforger hero fighter."""

from importlib import import_module

__all__ = ["HeroFighter", "draw_hero_fighter_effects"]


def __getattr__(name: str):
    if name == "HeroFighter":
        return import_module(
            "dungeons_desktops.game.heroes.hero_fighter.actor"
        ).HeroFighter
    if name == "draw_hero_fighter_effects":
        return import_module(
            "dungeons_desktops.game.heroes.hero_fighter.render"
        ).draw_hero_fighter_effects
    raise AttributeError(name)
