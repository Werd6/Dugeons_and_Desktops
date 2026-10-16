"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.mindflayer.actor import (
    MIND_FLAYER_HP,
    MindFlayer,
)

__all__ = ["MindFlayer", "MIND_FLAYER_HP", "draw_mindflayer", "draw_mindflayers"]


def __getattr__(name: str):
    if name in {"draw_mindflayer", "draw_mindflayers"}:
        from importlib import import_module

        module = import_module("dungeons_desktops.game.defenders.mindflayer.render")
        return getattr(module, name)
    raise AttributeError(name)
