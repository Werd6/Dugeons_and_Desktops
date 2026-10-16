"""PySide6 preview window. Paints the controller's state; all motion lives in the controller."""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.model import CLASSES
from dungeons_desktops.game.defenders.chimera.render import draw_chimeras
from dungeons_desktops.game.defenders.drakes.render import draw_drakes, draw_kobolds, draw_traps
from dungeons_desktops.game.defenders.drow.render import draw_darkness, draw_drow, draw_lizards
from dungeons_desktops.game.defenders.elementals.render import draw_elementals
from dungeons_desktops.game.defenders.hydra.render import draw_hydras
from dungeons_desktops.game.defenders.lich.render import draw_liches
from dungeons_desktops.game.defenders.lich.spell_render import draw_necromancy, draw_scorches
from dungeons_desktops.game.defenders.mimic.render import draw_mimics
from dungeons_desktops.game.defenders.ooze.render import draw_oozes
from dungeons_desktops.navigation.planner import Move
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.render.hud import draw_kill_marks
from dungeons_desktops.render.scene import (
    BACKGROUND,
    GROUND,
    draw_actors,
    draw_debris,
    draw_dio_effects,
    draw_displacers,
    draw_dragon,
    draw_fallen,
    draw_gore,
    draw_holes,
    draw_mindflayers,
    draw_minotaurs,
    draw_projectiles,
    draw_skeletons,
    draw_spears,
    draw_spells,
    draw_surfaces,
    draw_vials,
    draw_worm,
    pen,
    qt,
)

BOX_FILL = QColor(44, 48, 60)
BOX_TITLE = QColor(58, 63, 78)
BOX_EDGE = QColor(84, 90, 108)
HUD = QColor(170, 176, 190)
GOAL = QColor(120, 220, 160)
NO_ROUTE = QColor(230, 100, 100)
MOVE_COLORS = {
    Move.WALK: QColor(120, 220, 160),
    Move.CLIMB: QColor(240, 170, 90),
    Move.HANG: QColor(220, 130, 220),
    Move.SWING: QColor(220, 130, 220),
    Move.MANTLE: QColor(250, 220, 120),
    Move.GRAB: QColor(250, 220, 120),
    Move.JUMP: QColor(150, 170, 255),
    Move.DROP: QColor(150, 170, 255),
}
HELP = (
    "click empty space: go there    drag a box: move a 'window'    click the figure: knock over    "
    "drag a goblin: move it\n"
    "selected (green marker), Tab to switch:  W wander  S stop  R ragdoll  Space get up  "
    "1-9 barbarian/wizard/rogue/paladin/ranger/cleric/alchemist/druid/sorcerer  "
    "0 fighter  Y Dio  F attack\n"
    "N add adventurer  G add goblin  M add worm  B add dragon  V dragon colour  I add mind flayer  "
    "P add displacer beast  T add minotaur  U add ooze  L add lich  C add mimic  H add hydra  "
    "K add kobold drake  Z add drow lizard rider  X add chimera  E add elemental  "
    "J shift elemental  D surfaces"
)


class RigCanvas(QWidget):
    def __init__(self, controller: RigPreviewController, zoom: float = 1.15) -> None:
        super().__init__()
        self.controller = controller
        self.zoom = zoom
        self.show_surfaces = True
        self.setMinimumSize(800, 500)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.fps = 0.0

    def _world(self, event: QMouseEvent) -> Vec2:
        return Vec2(event.position().x() / self.zoom, event.position().y() / self.zoom)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.controller.resize(self.width() / self.zoom, self.height() / self.zoom)
        super().resizeEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.controller.press(self._world(event))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.controller.drag(self._world(event))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.controller.drop(self._world(event))

    def focusNextPrevChild(self, next: bool) -> bool:  # noqa: N802, A002
        return False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        controller = self.controller
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), BACKGROUND)
        painter.scale(self.zoom, self.zoom)

        self._draw_boxes(painter)
        painter.setPen(pen(GROUND, 2))
        painter.drawLine(
            QPointF(0, controller.floor_y), QPointF(controller.width, controller.floor_y)
        )
        if self.show_surfaces:
            draw_surfaces(painter, controller.surfaces)
        self._draw_route(painter)
        draw_holes(painter, controller.debris, controller.boxes)
        draw_scorches(painter, controller.necromancy)
        draw_traps(painter, controller.traps)
        draw_fallen(painter, controller.fallen)
        for worm in controller.worms:
            draw_worm(painter, worm)
        draw_minotaurs(painter, controller.minotaurs)
        draw_chimeras(painter, controller.chimeras)
        draw_elementals(painter, controller.elementals)
        draw_hydras(painter, controller.hydras)
        draw_drakes(painter, controller.drakes)
        draw_kobolds(painter, controller.kobolds)
        draw_liches(painter, controller.liches)
        draw_mimics(painter, controller.mimics)
        draw_skeletons(painter, controller.skeletons)
        draw_actors(painter, controller.goblins, controller.stickmen, controller.selected)
        draw_oozes(painter, controller.oozes)
        draw_darkness(painter, controller.darkness, controller.stickmen)
        draw_lizards(painter, controller.lizards)
        draw_drow(painter, controller.drow)
        for dragon in controller.dragons:
            draw_dragon(painter, dragon)
        draw_mindflayers(painter, controller.mindflayers, controller.devourers)
        draw_displacers(painter, controller.displacers)
        draw_dio_effects(painter, controller.heroes)
        draw_projectiles(painter, controller.projectiles)
        draw_spells(painter, controller.spells)
        draw_necromancy(painter, controller.necromancy)
        draw_vials(painter, controller.vials)
        draw_spears(painter, controller.spears)
        draw_debris(painter, controller.debris, [*controller.boxes, controller.bottom_border])
        draw_gore(painter, controller.gore)
        draw_kill_marks(painter, controller.kill_marks)

        painter.resetTransform()
        painter.setPen(HUD)
        painter.drawText(
            12,
            20,
            f"{controller.mode.value}   {controller.variant}   {self.fps:4.0f} fps   "
            f"{controller.status}",
        )
        for i, line in enumerate(HELP.split("\n")):
            painter.drawText(12, 38 + 16 * i, line)

    def _draw_boxes(self, painter: QPainter) -> None:
        for box in self.controller.boxes:
            rect = QRectF(box.x, box.y, box.width, box.height)
            painter.setPen(pen(BOX_EDGE, 1.5))
            painter.setBrush(BOX_FILL)
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(BOX_TITLE)
            painter.drawRect(QRectF(box.x + 1, box.y + 1, box.width - 2, min(14.0, box.height - 2)))
            painter.setBrush(QColor(200, 110, 100))
            painter.drawEllipse(QPointF(box.x + 8, box.y + 8), 2.5, 2.5)

    def _draw_route(self, painter: QPainter) -> None:
        controller = self.controller
        steps = controller.route_steps()
        if steps:
            points = [controller.contact()] + [step.end for step in steps]
            for step, a, b in zip(steps, points, points[1:], strict=False):
                painter.setPen(pen(MOVE_COLORS.get(step.move, GOAL), 2, Qt.PenStyle.DashLine))
                painter.drawLine(qt(a), qt(b))
        if controller.goal is not None:
            color = GOAL if controller.goal_reachable else NO_ROUTE
            painter.setPen(pen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(controller.goal), 6, 6)
            g = controller.goal
            painter.drawLine(qt(g - Vec2(9, 0)), qt(g + Vec2(9, 0)))
            painter.drawLine(qt(g - Vec2(0, 9)), qt(g + Vec2(0, 9)))


class RigPreviewWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Dungeons & Desktops - rig preview")
        self.controller = RigPreviewController(1100, 650)
        self.canvas = RigCanvas(self.controller)

        buttons = QHBoxLayout()
        for label, action in (
            ("Add stickman", self.controller.spawn_stickman),
            ("Add Dio", self.controller.spawn_dio),
            ("Add goblin", self.controller.spawn_goblin),
            ("Add worm", self.controller.spawn_worm),
            ("Add dragon", self.controller.spawn_dragon),
            ("Add mind flayer", self.controller.spawn_mindflayer),
            ("Add displacer beast", self.controller.spawn_displacer),
            ("Add minotaur", self.controller.spawn_minotaur),
            ("Add ooze", self.controller.spawn_ooze),
            ("Add lich", self.controller.spawn_lich),
            ("Add mimic", self.controller.spawn_mimic),
            ("Add hydra", self.controller.spawn_hydra),
            ("Add drake", self.controller.spawn_drake),
            ("Add drow", self.controller.spawn_drow),
            ("Add chimera", self.controller.spawn_chimera),
            ("Add elemental", self.controller.spawn_elemental),
            ("Shift elemental", self.controller.shift_elementals),
            ("Wander", self.controller.toggle_wander),
            ("Stop", self.controller.stop),
            ("Ragdoll", self.controller.go_ragdoll),
            ("Get up", self.controller.get_up),
            ("Surfaces", self._toggle_surfaces),
            ("Class", self.controller.next_class),
            ("Attack", self.controller.attack),
        ):
            button = QPushButton(label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(action)
            buttons.addWidget(button)
        buttons.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addLayout(buttons)
        root.addWidget(self.canvas, 1)
        self.resize(1280, 820)

        self._last = time.perf_counter()
        self._frame_times: list[float] = []
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _toggle_surfaces(self) -> None:
        self.canvas.show_surfaces = not self.canvas.show_surfaces

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        actions = {
            Qt.Key.Key_W: self.controller.toggle_wander,
            Qt.Key.Key_S: self.controller.stop,
            Qt.Key.Key_R: self.controller.go_ragdoll,
            Qt.Key.Key_Space: self.controller.get_up,
            Qt.Key.Key_D: self._toggle_surfaces,
            **{
                Qt.Key(Qt.Key.Key_0.value + (i + 1) % 10): (
                    lambda c=name: self.controller.set_variant(c)
                )
                for i, name in enumerate(CLASSES)
            },
            Qt.Key.Key_F: self.controller.attack,
            Qt.Key.Key_N: self.controller.spawn_stickman,
            Qt.Key.Key_Y: self.controller.spawn_dio,
            Qt.Key.Key_G: self.controller.spawn_goblin,
            Qt.Key.Key_M: self.controller.spawn_worm,
            Qt.Key.Key_B: self.controller.spawn_dragon,
            Qt.Key.Key_V: self.controller.next_dragon_variant,
            Qt.Key.Key_I: self.controller.spawn_mindflayer,
            Qt.Key.Key_P: self.controller.spawn_displacer,
            Qt.Key.Key_T: self.controller.spawn_minotaur,
            Qt.Key.Key_U: self.controller.spawn_ooze,
            Qt.Key.Key_L: self.controller.spawn_lich,
            Qt.Key.Key_C: self.controller.spawn_mimic,
            Qt.Key.Key_H: self.controller.spawn_hydra,
            Qt.Key.Key_K: self.controller.spawn_drake,
            Qt.Key.Key_Z: self.controller.spawn_drow,
            Qt.Key.Key_X: self.controller.spawn_chimera,
            Qt.Key.Key_E: self.controller.spawn_elemental,
            Qt.Key.Key_J: self.controller.shift_elementals,
            Qt.Key.Key_Tab: self.controller.select_next,
            Qt.Key.Key_Escape: self.close,
        }
        action = actions.get(Qt.Key(event.key()))
        if action is None:
            super().keyPressEvent(event)
        else:
            action()

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last
        self._last = now
        self.controller.advance(dt)

        self._frame_times.append(dt)
        if len(self._frame_times) > 30:
            self._frame_times.pop(0)
        average = sum(self._frame_times) / len(self._frame_times)
        self.canvas.fps = 1.0 / average if average > 0 else 0.0
        self.canvas.update()


def run_preview(quit_after: float | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    window = RigPreviewWindow()
    window.show()
    window.canvas.setFocus()
    if quit_after is not None:
        QTimer.singleShot(int(quit_after * 1000), app.quit)
    return app.exec()
