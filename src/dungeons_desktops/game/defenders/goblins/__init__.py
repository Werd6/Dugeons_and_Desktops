"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.goblins.actor import (
    GOBLIN_HP,
    Goblin,
    GoblinPack,
)

__all__ = ["Goblin", "GoblinPack", "GOBLIN_HP", "draw_goblin"]


def __getattr__(name: str):
    if name == "draw_goblin":
        from dungeons_desktops.game.defenders.goblins.render import draw_goblin

        return draw_goblin
    raise AttributeError(name)
