"""The desktop overlay: a transparent, click-through, always-on-top window over the main screen.

It only draws; every click, scroll and keypress goes to the apps underneath.
Controls live in a menu-bar icon (Pause, Hide, Show terrain, Quit), and Ctrl+C
in the launching terminal quits too. Window rectangles are polled on a timer:
quickly while windows are moving, slowly once things have settled.
"""

from __future__ import annotations

import signal
import sys
import time

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.menu import DefenderMenu, load_defenders
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import (
    FakeWindowSource,
    MacWindowSource,
    WindowSource,
    WindowSourceError,
    demo_windows,
)
from dungeons_desktops.game.defenders.chimera.render import MANE, draw_chimeras
from dungeons_desktops.game.defenders.displacer.render import FUR_SHEEN
from dungeons_desktops.game.defenders.drakes.render import draw_drakes, draw_kobolds, draw_traps
from dungeons_desktops.game.defenders.drow.render import (
    FAERIE,
    draw_darkness,
    draw_drow,
    draw_lizards,
)
from dungeons_desktops.game.defenders.elementals.render import COLOURS as ELEMENT_COLOURS
from dungeons_desktops.game.defenders.elementals.render import WATER_LIGHT, draw_elementals
from dungeons_desktops.game.defenders.hydra.render import CREST, draw_hydras
from dungeons_desktops.game.defenders.lich.render import GLOW, draw_liches
from dungeons_desktops.game.defenders.lich.spell_render import draw_necromancy, draw_scorches
from dungeons_desktops.game.defenders.mimic.render import WOOD_LIGHT, draw_mimics
from dungeons_desktops.game.defenders.mindflayer.render import draw_mindflayers
from dungeons_desktops.game.defenders.minotaur.render import HIDE_LIGHT
from dungeons_desktops.game.defenders.ooze.render import BODY as OOZE_BODY
from dungeons_desktops.game.defenders.ooze.render import draw_oozes
from dungeons_desktops.game.heroes.dio.render import draw_dio_effects
from dungeons_desktops.render.hud import (
    HEALTH_BAR_HEIGHT,
    draw_health_bar,
    draw_kill_counter,
    draw_kill_marks,
)
from dungeons_desktops.render.scene import (
    DRAGON_SKIN,
    FLAYER_ROBE,
    GOBLIN_EYE,
    GOBLIN_HEAD,
    GOBLIN_SKIN,
    HERO_SILVER,
    OUTLINE,
    WORM_SKIN,
    draw_actors,
    draw_debris,
    draw_displacers,
    draw_dragon,
    draw_fallen,
    draw_gore,
    draw_holes,
    draw_minotaurs,
    draw_projectiles,
    draw_skeletons,
    draw_spears,
    draw_spells,
    draw_surfaces,
    draw_vials,
    draw_worm,
    pen,
)

FRAME_MS = 16
POLL_FAST_MS = 125
POLL_SLOW_MS = 500
SETTLE_TIME = 2.0
MAX_FRAME_DT = 0.1
WINDOW_EDGE = QColor(110, 190, 240, 160)
COUNTER_MARGIN = 12.0
COUNTER_GAP = 6.0
"""Between the health bar and the kill counter stacked above it."""
KILL_BUMP_TIME = 0.5
DEFENDER_BARS = {
    "elementals": ("Elemental", WATER_LIGHT),
    "ooze": ("Ooze", OOZE_BODY),
    "chimera": ("Chimera", MANE.lighter(130)),
    "drow": ("Drow lizard riders", FAERIE),
    "drakes": ("Kobold drake riders", QColor(214, 120, 64)),
    "hydra": ("Hydra", CREST),
    "mimic": ("Mimic", WOOD_LIGHT),
    "lich": ("Lich", GLOW),
    "minotaur": ("Minotaur", HIDE_LIGHT.lighter(130)),
    "displacer": ("Displacer beast", FUR_SHEEN.lighter(140)),
    "mindflayer": ("Mind flayer", FLAYER_ROBE.lighter(150)),
    "worm": ("Worm", WORM_SKIN),
    "goblins": ("Goblins", GOBLIN_SKIN),
    "dragon": ("Dragon", DRAGON_SKIN),
}
"""Health bar label and color for each defender."""


def _rect(qrect) -> Rect:
    return Rect(qrect.x(), qrect.y(), qrect.width(), qrect.height())


class DesktopOverlay(QWidget):
    def __init__(self, session: DesktopSession, screen: QScreen) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.session = session
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowTitle("Dungeons & Desktops overlay")
        geometry = screen.geometry()
        self.setGeometry(geometry)
        self.origin = Vec2(geometry.x(), geometry.y())
        self.show_terrain = False
        self.show_kills = True
        self._kills_seen = session.kills
        self._kill_time = -KILL_BUMP_TIME

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        _float_above_everything(self)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        session = self.session
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(-self.origin.x, -self.origin.y)
        if self.show_terrain:
            painter.setPen(pen(WINDOW_EDGE, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for box in session.boxes:
                painter.drawRect(QRectF(box.x, box.y, box.width, box.height))
            draw_surfaces(painter, session.surfaces)
        draw_holes(painter, session.debris, session.boxes)
        draw_scorches(painter, session.necromancy)
        draw_traps(painter, session.traps, outline=OUTLINE)
        draw_fallen(painter, session.fallen, outline=OUTLINE)
        for worm in session.worms:
            draw_worm(painter, worm, outline=OUTLINE)
        draw_minotaurs(painter, session.minotaurs, outline=OUTLINE)
        draw_chimeras(painter, session.chimeras, outline=OUTLINE)
        draw_elementals(painter, session.elementals, outline=OUTLINE)
        draw_hydras(painter, session.hydras, outline=OUTLINE)
        draw_drakes(painter, session.drakes, outline=OUTLINE)
        draw_kobolds(painter, session.kobolds, outline=OUTLINE)
        draw_liches(painter, session.liches, outline=OUTLINE)
        draw_mimics(painter, session.mimics, outline=OUTLINE)
        draw_skeletons(painter, session.skeletons, outline=OUTLINE)
        draw_actors(painter, session.goblins, session.stickmen, outline=OUTLINE)
        draw_oozes(painter, session.oozes, outline=OUTLINE)
        draw_darkness(painter, session.darkness, session.stickmen)
        draw_lizards(painter, session.lizards, outline=OUTLINE)
        draw_drow(painter, session.drow, outline=OUTLINE)
        for dragon in session.dragons:
            draw_dragon(painter, dragon, outline=OUTLINE)
        draw_mindflayers(painter, session.mindflayers, session.devourers, outline=OUTLINE)
        draw_displacers(painter, session.displacers, outline=OUTLINE)
        draw_dio_effects(painter, session.heroes, outline=OUTLINE)
        draw_projectiles(painter, session.projectiles)
        draw_spells(painter, session.spells)
        draw_necromancy(painter, session.necromancy)
        draw_vials(painter, session.vials)
        draw_spears(painter, session.spears)
        draw_debris(painter, session.debris, [*session.boxes, session.bottom_border])
        draw_gore(painter, session.gore)
        draw_kill_marks(painter, session.kill_marks)
        if self.show_kills:
            self._draw_kills(painter)

    def _draw_kills(self, painter: QPainter) -> None:
        kills = self.session.kills
        now = time.perf_counter()
        if kills != self._kills_seen:
            self._kills_seen = kills
            self._kill_time = now
        bump = max(0.0, 1.0 - (now - self._kill_time) / KILL_BUMP_TIME)
        usable = self.session.usable
        corner = Vec2(usable.right - COUNTER_MARGIN, usable.bottom - COUNTER_MARGIN)
        health = self.session.defender_health
        bar = DEFENDER_BARS.get(self.session.defender or "")
        if self.session.defender == "elementals" and self.session.elementals:
            form = self.session.elementals[0].kind
            bar = (f"{form.capitalize()} elemental", ELEMENT_COLOURS[form])
        for hero_name, hero_health in reversed(self.session.hero_health_bars):
            draw_health_bar(
                painter,
                hero_health,
                corner,
                HERO_SILVER,
                hero_name,
            )
            corner = corner - Vec2(0.0, HEALTH_BAR_HEIGHT + COUNTER_GAP)
        if health is not None and bar is not None:
            label, color = bar
            draw_health_bar(painter, health, corner, color, label)
            corner = corner - Vec2(0.0, HEALTH_BAR_HEIGHT + COUNTER_GAP)
        draw_kill_counter(painter, kills, corner, bump * bump)


def _float_above_everything(widget: QWidget) -> None:
    """macOS: stay visible on every Space, over the menu bar (characters on a maximized
    window's top stand in that strip) and while other apps are active, and never take the
    mouse. Qt's flags cover most of this; AppKit makes it explicit where available."""
    # AppKit cannot wrap the synthetic window handles supplied by Qt's headless
    # platforms, which are used by smoke tests and CI.
    if sys.platform != "darwin" or QApplication.platformName() != "cocoa":
        return
    try:
        import AppKit
        import objc
    except ImportError:
        return
    view = objc.objc_object(c_void_p=int(widget.winId()))
    window = view.window()
    if window is None:
        return
    window.setIgnoresMouseEvents_(True)
    window.setHidesOnDeactivate_(False)
    window.setLevel_(AppKit.NSStatusWindowLevel)
    window.setHasShadow_(False)
    window.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorIgnoresCycle
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
    )


def _goblin_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(pen(GOBLIN_SKIN, 4))
    painter.setBrush(GOBLIN_HEAD)
    painter.drawPolygon([QPointF(22, 24), QPointF(2, 12), QPointF(18, 38)])
    painter.drawEllipse(QPointF(36, 34), 22, 22)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(GOBLIN_EYE)
    painter.drawEllipse(QPointF(46, 30), 5, 5)
    painter.end()
    return QIcon(pixmap)


class DesktopPet(QObject):
    """Owns the session, overlay, timers and menu-bar controls."""

    def __init__(self, app: QApplication, source: WindowSource, show_terrain: bool) -> None:
        super().__init__()
        self.app = app
        screen = app.primaryScreen()
        self.settings = QSettings()
        self.session = DesktopSession(
            _rect(screen.geometry()),
            _rect(screen.availableGeometry()),
            source,
            defenders=load_defenders(self.settings),
        )
        self.overlay = DesktopOverlay(self.session, screen)
        self.defender_menu = DefenderMenu(self.session, self.settings)
        self.overlay.show_terrain = show_terrain
        self.paused = False
        self._activation_menu_ready = False
        self._reported_error: str | None = None

        self._last = time.perf_counter()
        self._last_change = self._last
        self.frame_timer = QTimer(self)
        self.frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.frame_timer.timeout.connect(self._tick)
        self.poll_timer = QTimer(self)
        self.poll_timer.setSingleShot(True)
        self.poll_timer.timeout.connect(self._poll)

        self.tray = self._make_tray()
        self.app.installEventFilter(self)

    def start(self) -> None:
        self.overlay.show()
        self.frame_timer.start(FRAME_MS)
        self.poll_timer.start(POLL_FAST_MS)
        QTimer.singleShot(750, self._arm_activation_menu)

    # ----- controls ------------------------------------------------------------

    def _make_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("No menu bar tray available; press Ctrl+C in this terminal to quit.")
            return None
        menu = QMenu()
        self._action(menu, "Defenders…", self.show_defender_menu)
        menu.addSeparator()
        self.pause_action = self._action(menu, "Pause", self.set_paused, checkable=True)
        self.hide_action = self._action(menu, "Hide", self.set_hidden, checkable=True)
        self.terrain_action = self._action(
            menu, "Show terrain", self.set_show_terrain, checkable=True
        )
        self.terrain_action.setChecked(self.overlay.show_terrain)
        self.kills_action = self._action(
            menu, "Show kill counter", self.set_show_kills, checkable=True
        )
        self.kills_action.setChecked(self.overlay.show_kills)
        self._action(menu, "Spawn a stickman now", lambda: self.session.spawn_at_edge())
        self._action(
            menu,
            "Spawn Dio",
            lambda: self.session.spawn_at_edge(variant="hero_fighter"),
        )
        self._action(menu, "Next monster now", lambda: self.session.rotate())
        menu.addSeparator()
        self._action(menu, "Quit Dungeons & Desktops", self.app.quit)
        tray = QSystemTrayIcon(_goblin_icon(), self)
        tray.setToolTip("Dungeons & Desktops")
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        self._menu = menu
        return tray

    @staticmethod
    def _action(menu: QMenu, label: str, slot, checkable: bool = False) -> QAction:
        action = QAction(label, menu)
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            watched is self.app
            and event.type() is QEvent.Type.ApplicationActivate
            and self._activation_menu_ready
            and not self.defender_menu.isVisible()
        ):
            QTimer.singleShot(0, self.show_defender_menu)
        return super().eventFilter(watched, event)

    def _arm_activation_menu(self) -> None:
        self._activation_menu_ready = True

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason is QSystemTrayIcon.ActivationReason.Trigger:
            self.show_defender_menu()

    def show_defender_menu(self) -> None:
        self.defender_menu.sync()
        self.defender_menu.show()
        self.defender_menu.raise_()
        self.defender_menu.activateWindow()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def set_hidden(self, hidden: bool) -> None:
        self.overlay.setVisible(not hidden)

    def set_show_terrain(self, show: bool) -> None:
        self.overlay.show_terrain = show
        self.overlay.update()

    def set_show_kills(self, show: bool) -> None:
        self.overlay.show_kills = show
        self.overlay.update()

    # ----- timers --------------------------------------------------------------

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(now - self._last, MAX_FRAME_DT)
        self._last = now
        if not self.paused:
            self.session.advance(dt)
        if self.overlay.isVisible():
            self.overlay.update()

    def _poll(self) -> None:
        now = time.perf_counter()
        if self.session.poll():
            self._last_change = now
        error = self.session.source_error
        if error is not None and error != self._reported_error:
            print(f"Window list unavailable, keeping the last layout: {error}", file=sys.stderr)
        self._reported_error = error
        settled = now - self._last_change > SETTLE_TIME
        self.poll_timer.start(POLL_SLOW_MS if settled else POLL_FAST_MS)


def _window_source(app: QApplication, mock: bool) -> tuple[WindowSource, bool]:
    """The window source to use, and whether to outline the terrain by default."""
    if mock:
        return FakeWindowSource(demo_windows(_rect(app.primaryScreen().availableGeometry()))), True
    try:
        return MacWindowSource(), False
    except WindowSourceError as error:
        print(f"{error}\nFalling back to the screen edges only.", file=sys.stderr)
        return FakeWindowSource(), False


def run_desktop(quit_after: float | None = None, mock: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("Dungeons & Desktops")
    app.setApplicationName("Dungeons & Desktops")
    app.setQuitOnLastWindowClosed(False)
    source, show_terrain = _window_source(app, mock)
    pet = DesktopPet(app, source, show_terrain)
    pet.start()

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(200)
    if quit_after is not None:
        QTimer.singleShot(int(quit_after * 1000), app.quit)
    return app.exec()
