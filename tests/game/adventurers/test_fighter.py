"""Fighter appearance, sword combat cadence, and tenth-class preview controls."""

import os
import subprocess
import sys
from statistics import mean
from textwrap import dedent

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.render.scene import draw_stickman
from dungeons_desktops.rig.equipment import FighterSword, Sword

DT = 1 / 60


def scene(variant="fighter", facing=1):
    world = SimWorld([], 200.0, 600.0, ceiling=0.0, seed=3)
    fighter = world.add_stickman(Vec2(100, 200), variant)
    fighter.follower.facing = facing
    return world, fighter


def strikes(variant):
    world, man = scene(variant)
    goblin = world.add_goblin(Vec2(118, 200), "flag")
    goblin.update = lambda dt: None
    hits, now = [], [0.0]

    def record(monster, amount, point, push, **kwargs):
        hits.append((now[0], monster, amount))
        return False

    world.hurt_monster = record
    for _ in range(360):
        now[0] += DT
        world.advance(DT)
    assert hits and all(monster is goblin and amount == 1 for _, monster, amount in hits)
    return man, [at for at, _, _ in hits]


def test_fighter_has_eight_hp_and_lands_blows_twice_as_often_as_paladin():
    fighter, fast = strikes("fighter")
    _, slow = strikes("paladin")
    assert fighter.max_hp == 8
    assert isinstance(fighter.weapon, FighterSword) and isinstance(fighter.weapon, Sword)
    fast_interval = mean(b - a for a, b in zip(fast, fast[1:], strict=False))
    slow_interval = mean(b - a for a, b in zip(slow, slow[1:], strict=False))
    assert fast_interval == pytest.approx(0.5, abs=2 * DT)
    assert fast_interval == pytest.approx(slow_interval / 2, abs=2 * DT)


@pytest.mark.parametrize("facing", [-1, 1])
def test_red_fighter_and_helmet_render_facing_either_way_and_after_falling(facing):
    world, fighter = scene(facing=facing)
    for _ in range(15):
        world.advance(DT)
    assert fighter.facing == facing

    def paint():
        image = QImage(200, 220, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            draw_stickman(painter, fighter)
        finally:
            painter.end()
        return image

    image = paint()
    colors = {image.pixelColor(x, y).name() for x in range(75, 125) for y in range(160, 205)}
    assert QColor(236, 64, 68).name() in colors
    assert QColor(70, 78, 94).name() in colors  # Helmet edges/visor.
    assert QColor(128, 134, 150).name() in colors  # Helmet metal.
    assert fighter.hurt(8, fighter.center(), Vec2(0, 0), "test", "fallen")
    world.advance(DT)
    assert paint() != image


def test_zero_selects_fighter_and_nine_still_selects_sorcerer():
    # Other rendering tests create QGuiApplication, which cannot host QWidget.
    # Keep this widget integration check in its own Qt application process.
    script = dedent("""
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.preview.window import RigPreviewWindow

        app = QApplication([])
        window = RigPreviewWindow()
        window.timer.stop()
        try:
            for key, variant in ((Qt.Key.Key_0, "fighter"), (Qt.Key.Key_9, "sorcerer")):
                event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
                app.sendEvent(window, event)
                assert window.controller.variant == variant
        finally:
            window.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
