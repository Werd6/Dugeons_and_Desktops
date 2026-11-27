"""Aboleth psychic dominate and rotating tentacle whip."""

from __future__ import annotations

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.aboleth.actor import (
    DOMINATE_TIME,
    PSYCHIC_WINDUP,
    SLIME_DAMAGE,
    TENTACLE_COUNT,
    WHIP_RECOVER,
    WHIP_STRIKE,
    WHIP_WINDUP,
    Action,
    Aboleth,
)
from dungeons_desktops.game.world.simulation import SimWorld

FLOOR = 400.0
STEP = 1 / 60


def run(world: SimWorld, seconds: float) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)


def test_psychic_ray_dominates_then_brain_bursts_into_slime():
    world = SimWorld([], FLOOR, 700, ceiling=0.0, seed=7)
    aboleth = world.add_aboleth(Vec2(200, 160), facing=1)
    prey = world.add_stickman(Vec2(260, FLOOR), "unarmed")
    bystander = world.add_stickman(Vec2(280, FLOOR), "unarmed")
    prey.stop()
    bystander.stop()

    aboleth.psychic_wait = 0.0
    aboleth.whip_wait = 99.0
    aboleth._start_psychic(prey)
    run(world, PSYCHIC_WINDUP + 0.05)
    assert aboleth.bolts or prey.thrall

    run(world, 1.0)
    assert prey.thrall
    assert prey in [d.victim for d in aboleth.dominations]
    assert not prey.prey

    before = bystander.damage
    run(world, DOMINATE_TIME + 0.5)
    assert not prey.animated
    assert not world.devourers  # aboleth dominate must not hatch a mind-flayer devourer
    assert aboleth.slime_bursts or bystander.damage >= before + SLIME_DAMAGE - 1
    assert bystander.damage >= before


def test_tentacle_whip_rotates_and_damages():
    world = SimWorld([], FLOOR, 700, ceiling=0.0, seed=8)
    aboleth = world.add_aboleth(Vec2(250, FLOOR - 40), facing=1)
    prey = world.add_stickman(Vec2(280, FLOOR), "unarmed")
    prey.stop()

    aboleth.whip_wait = 0.0
    aboleth.psychic_wait = 99.0
    first = aboleth.next_tentacle
    aboleth._start_whip(prey)
    assert aboleth.action is Action.WHIP
    assert aboleth.whip is not None
    assert aboleth.whip.index == first % TENTACLE_COUNT

    run(world, WHIP_WINDUP + WHIP_STRIKE + 0.02)
    assert prey.damage >= 1

    run(world, WHIP_RECOVER + 0.05)
    assert aboleth.action is None
    assert aboleth.next_tentacle == (first + 1) % TENTACLE_COUNT

    aboleth.whip_wait = 0.0
    aboleth._start_whip(prey)
    assert aboleth.whip is not None
    assert aboleth.whip.index == (first + 1) % TENTACLE_COUNT


def test_draw_with_combat_fx_does_not_crash():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    from dungeons_desktops.game.defenders.aboleth.render import draw_aboleth

    world = SimWorld([], FLOOR, 700, ceiling=0.0, seed=9)
    aboleth = world.add_aboleth(Vec2(200, 150), facing=1)
    prey = world.add_stickman(Vec2(250, FLOOR), "unarmed")
    aboleth.eye_charge = 1.0
    aboleth._start_whip(prey)
    image = QImage(400, 300, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw_aboleth(painter, aboleth)
    painter.end()


def test_lethal_hit_opens_deep_portal_and_banishes():
    from dungeons_desktops.game.defenders.aboleth.actor import (
        ABOLETH_HP,
        BANISH_CLOSE,
        BANISH_OPEN,
        BANISH_SWIM,
    )

    world = SimWorld([], FLOOR, 700, ceiling=0.0, seed=11)
    aboleth = world.add_aboleth(Vec2(220, 180), facing=1)
    assert aboleth.max_hp == ABOLETH_HP
    killed = world.hurt_monster(aboleth, ABOLETH_HP, aboleth.center(), Vec2(40.0, -10.0))
    assert killed
    assert aboleth not in world.aboleths
    assert aboleth in world.fallen
    assert aboleth.banishing
    assert aboleth.portal is not None
    run(world, BANISH_OPEN + BANISH_SWIM + BANISH_CLOSE + 0.1)
    assert aboleth.gone
    assert aboleth.portal is None
    assert not aboleth.banishing
