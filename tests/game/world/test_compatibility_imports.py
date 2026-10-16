"""One-release legacy imports preserve canonical object identity."""

from __future__ import annotations

import importlib
import warnings


def legacy(name: str):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = importlib.import_module(name)
    assert any(item.category is DeprecationWarning for item in caught)
    return module


def test_systems_actor_identity():
    old = legacy("dungeons_desktops.systems.actors")
    from dungeons_desktops.game.adventurers.actor import Stickman

    assert old.Stickman is Stickman


def test_creature_model_identity():
    old = legacy("dungeons_desktops.creatures.stick_figure")
    from dungeons_desktops.game.adventurers.model import Calling

    assert old.Calling is Calling


def test_render_draw_identity():
    old = legacy("dungeons_desktops.render.draw")
    from dungeons_desktops.render.scene import draw_actors

    assert old.draw_actors is draw_actors


def test_rig_weapon_identity():
    old = legacy("dungeons_desktops.rig.weapons")
    from dungeons_desktops.rig.equipment import Sword

    assert old.Sword is Sword
