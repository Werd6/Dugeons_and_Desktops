"""World protocol and concrete simulation."""

from dungeons_desktops.game.world.api import World

__all__ = ["SimWorld", "World"]

def __getattr__(name: str):
    if name == "SimWorld":
        from dungeons_desktops.game.world.simulation import SimWorld
        return SimWorld
    raise AttributeError(name)
