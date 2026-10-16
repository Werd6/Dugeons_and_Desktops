import os

import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import StickMode
from dungeons_desktops.game.defenders.dragon.actor import Flame
from dungeons_desktops.game.effects.breath import BREATHS, DEATH_MESSAGES, DEATH_TIME, VARIANTS
from dungeons_desktops.game.world.simulation import SimWorld

STEP = 1 / 60


def world_with(seed=3) -> SimWorld:
    return SimWorld([], 700.0, 1200.0, ceiling=20.0, seed=seed)


def run(world: SimWorld, seconds: float, each=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()


def test_a_new_dragon_gets_a_random_colour():
    seen = {world_with(seed).add_dragon().variant for seed in range(60)}
    assert seen == set(VARIANTS)


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_colour_can_be_chosen(variant):
    assert world_with().add_dragon(variant=variant).variant == variant


def strafing_run(variant: str) -> tuple[list, list]:
    """Every hit (and the breath stream itself) of a dragon making passes over two
    adventurers who never go down."""
    world = world_with()
    dragon = world.add_dragon(Vec2(700, 450), 1, variant=variant)
    dragon.flight_timer = 1e9
    hits: list = []
    stream: list = []
    for x in (450, 560):
        stickman = world.add_stickman(Vec2(x, 700))
        stickman.update = lambda dt: None

        def hurt(amount, point, push, source, death, bleed=True, x=x):
            hits.append((len(stream), x, amount, source, round(push.x, 3), bleed))
            return False

        stickman.hurt = hurt

    def record() -> None:
        stream.append(
            (
                round(dragon.body.x, 3),
                round(dragon.body.y, 3),
                tuple((round(f.position.x, 3), round(f.position.y, 3)) for f in dragon.flames),
            )
        )

    run(world, 6.0, record)
    return hits, stream


def test_every_colour_fights_exactly_the_same():
    red_hits, red_stream = strafing_run("red")
    assert red_hits and any(flames for *_, flames in red_stream)
    assert all(source == "dragon" for _, _, _, source, _, _ in red_hits)
    for variant in VARIANTS[1:]:
        hits, stream = strafing_run(variant)
        assert hits == red_hits, variant
        assert stream == red_stream, variant


@pytest.mark.parametrize("variant", VARIANTS)
def test_each_colour_kills_with_its_own_death(variant):
    world = world_with()
    dragon = world.add_dragon(Vec2(100, 150), 1, variant=variant)
    dragon.flight_timer = dragon.fire_cooldown = 1e9
    stickman = world.add_stickman(Vec2(600, 700))
    said, sources = [], []
    say, hurt = stickman.say, stickman.hurt
    stickman.say = lambda message: said.append(message) or say(message)
    stickman.hurt = lambda *args, **kwargs: sources.append(args[3]) or hurt(*args, **kwargs)
    run(world, 0.2)
    dragon.flames.append(Flame(stickman.center(), Vec2(150, 80)))
    run(world, STEP)

    assert world.kills == 1 and dragon.catches == 1
    assert sources == ["dragon"]
    assert DEATH_MESSAGES[variant] in said
    assert stickman.mode is StickMode.RAGDOLL
    if variant == "red":
        assert stickman.burn is not None and stickman.demise is None
    else:
        assert stickman.burn is None and stickman.demise.kind == BREATHS[variant]
    run(world, DEATH_TIME * 0.7)
    assert stickman in world.stickmen
    run(world, DEATH_TIME * 0.3 + 0.1)
    assert stickman not in world.stickmen


def test_a_frozen_adventurer_stays_put_then_shatters():
    world = world_with()
    dragon = world.add_dragon(Vec2(100, 150), 1, variant="white")
    dragon.flight_timer = dragon.fire_cooldown = 1e9
    stickman = world.add_stickman(Vec2(600, 700))
    run(world, 0.2)
    dragon.flames.append(Flame(stickman.center(), Vec2(150, 80)))
    run(world, STEP)
    where = stickman.center()
    run(world, 1.5)
    assert stickman.center().distance_to(where) < 1.5
    assert not stickman.demise.shattered
    run(world, 1.5)
    assert stickman.demise.shattered
    assert any(mote.kind == "shard" for mote in stickman.demise.motes)


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_colour_breath_and_death_draws(qt_app, variant):
    from PySide6.QtGui import QColor, QImage, QPainter

    from dungeons_desktops.render.draw import OUTLINE, draw_actors, draw_dragon, draw_fallen

    world = world_with()
    dragon = world.add_dragon(Vec2(380, 500), 1, variant=variant)
    dragon.flight_timer = 1e9
    for x in (450, 500, 560):
        world.add_stickman(Vec2(x, 700))
    image = QImage(400, 240, QImage.Format.Format_ARGB32)

    def paint() -> None:
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.scale(1 / 3, 1 / 3)
        draw_actors(painter, world.goblins, world.stickmen, outline=OUTLINE)
        for body in world.dragons:
            draw_dragon(painter, body, outline=OUTLINE)
        draw_fallen(painter, world.fallen)
        painter.end()

    for step in range(round(3.6 / STEP)):
        world.advance(STEP)
        if step % 10 == 0:
            paint()
    assert world.kills >= 1
    dragon.die(dragon.body, Vec2(0, 0))
    for _ in range(30):
        dragon.update_dead(STEP)
    painter = QPainter(image)
    draw_fallen(painter, [dragon])
    painter.end()
