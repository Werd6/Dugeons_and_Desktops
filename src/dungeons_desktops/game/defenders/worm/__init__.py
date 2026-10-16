"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.worm.actor import (
    WORM_HP,
    Worm,
    WormMode,
)

__all__ = ["Worm", "WormMode", "WORM_HP", "draw_worm"]


def __getattr__(name: str):
    if name == "draw_worm":
        from dungeons_desktops.game.defenders.worm.render import draw_worm

        return draw_worm
    raise AttributeError(name)
