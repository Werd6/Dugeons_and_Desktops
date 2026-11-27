"""The maul lands with the paw, and nature magic follows the full bear body."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.heroes.natures_wrath.bear import (
    BEAR_DAMAGE,
    MAUL_HIT,
    MAUL_TIME,
    MAUL_WINDUP,
)
from dungeons_desktops.game.world.simulation import SimWorld


def maul_scene(facing=1):
    world = SimWorld([], 400, 1200, ceiling=0)
    hero = world.add_stickman(Vec2(500, 400), "hero_druid")
    target = world.add_minotaur(Vec2(500 + facing * 65, 400))
    hero._start_bear()
    hero.update(1 / 60)
    assert hero.bear.maul_time == 0
    return world, hero, target


@pytest.mark.parametrize("facing", [-1, 1])
def test_maul_lifts_the_paw_before_dealing_damage_once_on_the_strike(facing):
    _, hero, target = maul_scene(facing)
    bear = hero.bear
    feet = bear.contact()
    hero.update(MAUL_WINDUP)
    assert target.damage == 0 and bear.contact() == feet
    paw = next(leg for leg in bear.legs if leg.near and leg.front)
    assert paw.foot.y < bear.head.y - 20
    hero.update(MAUL_HIT - MAUL_WINDUP - 0.01)
    assert target.damage == 0
    hero.update(0.02)
    assert target.damage == BEAR_DAMAGE and bear.impact > 0
    assert paw.foot.distance_to(bear.maul_aim) < 1
    hero.update(MAUL_TIME - MAUL_HIT)
    assert target.damage == BEAR_DAMAGE and bear.maul_time is None
    assert paw.foot.y == bear.feet.y


def test_stun_freezes_the_windup_and_damage_until_the_strike_resumes():
    _, hero, target = maul_scene()
    hero.update(0.1)
    hero.paralyze(1)
    paw = hero.bear.legs[-1].foot
    hero.update(0.6)
    assert hero.bear.maul_time == pytest.approx(0.1)
    assert hero.bear.legs[-1].foot == paw and target.damage == 0
    hero.update(0.6)
    assert target.damage == 0
    hero.update(0.25)
    assert target.damage == BEAR_DAMAGE


@pytest.mark.parametrize("escape", ["move", "die"])
def test_maul_cannot_hit_a_target_that_escapes_or_dies_during_windup(escape):
    world, hero, target = maul_scene()
    hero.update(0.1)
    if escape == "move":
        target.position += Vec2(300, 0)
    else:
        world.hurt_monster(target, target.hp, target.center(), Vec2(0, 0))
    damage = target.damage
    hero.update(MAUL_TIME)
    assert target.damage == damage and hero.bear.maul_time is None


def test_bear_death_cancels_an_unreleased_maul():
    _, hero, target = maul_scene()
    hero.update(0.1)
    hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    hero.update(1)
    assert hero.form is None and target.damage == 0


def test_bear_leaves_cover_a_larger_area_and_render_without_advancing_simulation():
    world = SimWorld([], 400, 1200, ceiling=0)
    hero = world.add_stickman(Vec2(500, 400), "hero_druid")
    hero.nature_time = 1.5

    def render():
        image = QImage(600, 420, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(2, 2)
        painter.translate(-350, -250)
        draw_stickman(painter, hero)
        painter.end()
        return image

    def green_span(image):
        points = [
            x
            for x in range(image.width())
            for y in range(image.height())
            if (color := image.pixelColor(x, y)).alpha() > 60
            and color.green() > color.red() * 1.15
            and color.green() > color.blue() * 1.3
        ]
        assert points
        return max(points) - min(points)

    normal = green_span(render())
    world.add_minotaur(Vec2(565, 400))
    hero._start_bear()
    hero.update(1 / 60)
    hero.update(MAUL_HIT)
    rng = world.random.getstate()
    clock, maul = hero.nature_time, hero.bear.maul_time
    image = render()
    assert green_span(image) > normal * 3
    assert image == render()
    assert world.random.getstate() == rng
    assert (hero.nature_time, hero.bear.maul_time) == (clock, maul)
