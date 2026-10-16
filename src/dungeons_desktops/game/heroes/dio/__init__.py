"""Public exports for Dio without eager actor/weapon import cycles."""

from __future__ import annotations

from importlib import import_module

__all__ = ["Dio", "HeroFighter", "DioMove", "draw_dio_effects"]


def __getattr__(name: str):
    if name in {"Dio", "HeroFighter", "DioMove"}:
        return getattr(import_module("dungeons_desktops.game.heroes.dio.actor"), name)
    if name == "draw_dio_effects":
        return getattr(import_module("dungeons_desktops.game.heroes.dio.render"), name)
    raise AttributeError(name)
