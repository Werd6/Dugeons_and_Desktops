"""Public exports for this game feature."""

from dungeons_desktops.game.defenders.aboleth.actor import ABOLETH_HP, Aboleth

__all__ = ["Aboleth", "ABOLETH_HP", "draw_aboleth", "draw_aboleths"]


def __getattr__(name: str):
    if name in {"draw_aboleth", "draw_aboleths"}:
        from dungeons_desktops.game.defenders.aboleth.render import draw_aboleth, draw_aboleths

        return draw_aboleth if name == "draw_aboleth" else draw_aboleths
    raise AttributeError(name)
