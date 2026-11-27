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
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QKeySequence, QPainter, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QToolTip, QWidget

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.instance import (
    acquire_desktop_instance,
    notify_running_desktop,
)
from dungeons_desktops.desktop.menu import DefenderMenu, load_defenders, load_legendaries
from dungeons_desktops.desktop.progression import ProgressionStore
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.theme import apply_board
from dungeons_desktops.desktop.windows import (
    FakeWindowSource,
    MacWindowSource,
    WinWindowSource,
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
from dungeons_desktops.game.defenders.graveknights.render import (
    SKIN as GRAVEKNIGHT_SKIN,
)
from dungeons_desktops.game.defenders.graveknights.render import draw_graveknights
from dungeons_desktops.game.defenders.hydra.render import CREST, draw_hydras
from dungeons_desktops.game.defenders.legendary import LEGENDARY_GOLD, legendary_name
from dungeons_desktops.game.defenders.lich.render import GLOW, draw_liches
from dungeons_desktops.game.defenders.lich.spell_render import draw_necromancy, draw_scorches
from dungeons_desktops.game.defenders.mimic.render import WOOD_LIGHT, draw_mimics
from dungeons_desktops.game.defenders.mindflayer.render import draw_mindflayers
from dungeons_desktops.game.defenders.minotaur.render import HIDE_LIGHT
from dungeons_desktops.game.defenders.aboleth.render import draw_aboleths
from dungeons_desktops.game.defenders.zombies.render import SKIN as ZOMBIE_SKIN
from dungeons_desktops.game.defenders.zombies.render import draw_zombies
from dungeons_desktops.game.heroes.hero_cleric.render import draw_divine_judgements
from dungeons_desktops.game.heroes.hero_fighter.render import draw_hero_fighter_effects
from dungeons_desktops.game.heroes.hero_paladin.render import draw_paladin_effects
from dungeons_desktops.game.heroes.natures_wrath.spell_render import draw_nature_spells
from dungeons_desktops.game.heroes.the_inquisitive.spell_render import draw_iggy_spells
from dungeons_desktops.game.heroes.the_mighty.render import draw_mighty_effects
from dungeons_desktops.game.heroes.the_slayer.render import draw_slayer_effects
from dungeons_desktops.game.progression import Progression
from dungeons_desktops.game.unlocks import HERO_NAMES, UNLOCKS
from dungeons_desktops.render.chromatic import draw_chromatic_effects
from dungeons_desktops.render.hud import (
    HEALTH_BAR_HEIGHT,
    draw_health_bar,
    draw_kill_counter,
    draw_kill_marks,
    draw_menu_hint,
    kill_counter_skull_center,
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
MENU_HINT_KEY = "ui/menu_reopen_hint_shown"
MENU_HINT_SECONDS = 14.0
MENU_HINT_TEXT = "Open the app again to show the menu"
UNLOCK_ALERT_TIP = "Unlocks available"
UNLOCK_HIT = 22
HEADLESS_QT_PLATFORMS = frozenset({"minimal", "offscreen", "vnc"})
DEFENDER_BARS = {
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
    "zombies": ("Zombies", ZOMBIE_SKIN),
    "graveknights": ("Graveknights", GRAVEKNIGHT_SKIN),
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
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.session = session
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle("Dungeons & Desktops overlay")
        geometry = screen.geometry()
        self.setGeometry(geometry)
        self.origin = Vec2(geometry.x(), geometry.y())
        self.show_terrain = False
        self.show_kills = True
        self._kills_seen = session.progression.skulls_earned
        self._kill_time = -KILL_BUMP_TIME
        self.menu_hint_until = 0.0
        self.unlock_alert = False
        self._kill_corner = Vec2(0.0, 0.0)
        self.unlock_hit = _UnlockAlertHit(self._show_unlock_tip)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        _float_above_everything(self)
        # Cocoa can finish replacing/configuring the native NSWindow after Qt's
        # show event. Reapply on the next event-loop turn so the overlay keeps
        # its all-Spaces behavior, including other apps' fullscreen Spaces.
        QTimer.singleShot(0, lambda: _float_above_everything(self))

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.unlock_hit.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _show_unlock_tip(self) -> None:
        QToolTip.showText(QCursor.pos(), UNLOCK_ALERT_TIP, self.unlock_hit)

    def sync_unlock_alert(self) -> None:
        """Refresh the bang + click target when claimable unlocks change."""
        ready = any(self.session.progression.can_unlock(unlock.key) for unlock in UNLOCKS)
        self.unlock_alert = ready and self.show_kills
        if not self.unlock_alert or not self.isVisible():
            self.unlock_hit.hide()
            return
        skull = kill_counter_skull_center(
            self.session.progression.skulls_earned, self._kill_corner
        )
        # Counter corner is already in global screen space (same as session.usable).
        self.unlock_hit.setGeometry(
            int(skull.x - UNLOCK_HIT / 2),
            int(skull.y - UNLOCK_HIT / 2 - 4),
            UNLOCK_HIT,
            UNLOCK_HIT,
        )
        if not self.unlock_hit.isVisible():
            self.unlock_hit.show()
        _float_above_everything(self.unlock_hit)

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
        draw_hydras(painter, session.hydras, outline=OUTLINE)
        draw_drakes(painter, session.drakes, outline=OUTLINE)
        draw_kobolds(painter, session.kobolds, outline=OUTLINE)
        draw_liches(painter, session.liches, outline=OUTLINE)
        draw_mimics(painter, session.mimics, outline=OUTLINE)
        draw_zombies(painter, session.zombies, outline=OUTLINE)
        draw_graveknights(painter, session.graveknights, outline=OUTLINE)
        draw_skeletons(painter, session.skeletons, outline=OUTLINE)
        draw_actors(painter, session.goblins, session.stickmen, outline=OUTLINE)
        draw_aboleths(painter, session.aboleths, outline=OUTLINE)
        draw_darkness(painter, session.darkness, session.stickmen)
        draw_lizards(painter, session.lizards, outline=OUTLINE)
        draw_drow(painter, session.drow, outline=OUTLINE)
        for dragon in session.dragons:
            draw_dragon(painter, dragon, outline=OUTLINE)
        draw_mindflayers(painter, session.mindflayers, session.devourers, outline=OUTLINE)
        draw_displacers(painter, session.displacers, outline=OUTLINE)
        draw_divine_judgements(painter, session.heroes)
        draw_hero_fighter_effects(painter, session.heroes, outline=OUTLINE)
        draw_nature_spells(painter, session.heroes)
        draw_mighty_effects(painter, session.heroes)
        draw_iggy_spells(painter, session.stickmen)
        draw_slayer_effects(painter, session.heroes)
        draw_paladin_effects(painter, session.heroes)
        draw_chromatic_effects(painter, session.chromatic)
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
        kills = self.session.progression.skulls_earned
        now = time.perf_counter()
        if kills != self._kills_seen:
            self._kills_seen = kills
            self._kill_time = now
        bump = max(0.0, 1.0 - (now - self._kill_time) / KILL_BUMP_TIME)
        usable = self.session.usable
        corner = Vec2(usable.right - COUNTER_MARGIN, usable.bottom - COUNTER_MARGIN)
        health = self.session.defender_health
        defender = self.session.defender or ""
        bar = DEFENDER_BARS.get(defender)
        if bar is not None and self.session.is_legendary(defender):
            bar = (legendary_name(defender), LEGENDARY_GOLD)
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
        self._kill_corner = corner
        draw_kill_counter(painter, kills, corner, bump * bump, alert=self.unlock_alert)
        if self.menu_hint_until > now:
            draw_menu_hint(painter, corner, MENU_HINT_TEXT)


class _UnlockAlertHit(QWidget):
    """Tiny clickable chip over the skull bang; the main overlay stays click-through."""

    def __init__(self, on_click) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._on_click = on_click
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(UNLOCK_HIT, UNLOCK_HIT)
        self.hide()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() is Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        # Invisible hit target — the bang is painted on the overlay itself.
        return


def _supports_native_macos_overlay(qt_platform: str) -> bool:
    """Whether *qt_platform* exposes a real native macOS window handle."""
    return sys.platform == "darwin" and qt_platform.lower() not in HEADLESS_QT_PLATFORMS


def _native_overlay_collection_behavior(appkit, current: int) -> int:
    """Build the AppKit role for an overlay that follows other apps fullscreen."""
    behavior = int(current)
    # Qt.Tool creates an NSPanel with MoveToActiveSpace. AppKit rejects that
    # role when CanJoinAllSpaces is also present, so choose the all-Spaces role.
    behavior &= ~int(getattr(appkit, "NSWindowCollectionBehaviorMoveToActiveSpace", 0))
    cross_app = getattr(appkit, "NSWindowCollectionBehaviorCanJoinAllApplications", None)
    if cross_app is not None:
        # The modern full-screen/Stage Manager roles are mutually exclusive.
        # Remove any role Qt supplied before choosing the overlay-specific one.
        for name in (
            "NSWindowCollectionBehaviorPrimary",
            "NSWindowCollectionBehaviorAuxiliary",
            "NSWindowCollectionBehaviorCanJoinAllApplications",
            "NSWindowCollectionBehaviorFullScreenPrimary",
            "NSWindowCollectionBehaviorFullScreenNone",
        ):
            behavior &= ~int(getattr(appkit, name, 0))
        behavior |= int(cross_app)
    # CanJoinAllApplications crosses app ownership; FullScreenAuxiliary makes
    # this non-primary panel eligible to inhabit the fullscreen Space.
    behavior |= int(appkit.NSWindowCollectionBehaviorFullScreenAuxiliary)
    return behavior | int(
        appkit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | appkit.NSWindowCollectionBehaviorStationary
        | appkit.NSWindowCollectionBehaviorIgnoresCycle
    )


def _float_above_everything(widget: QWidget) -> None:
    """macOS: stay visible on every Space, over the menu bar (characters on a maximized
    window's top stand in that strip) and while other apps are active, and never take the
    mouse. Qt's flags cover most of this; AppKit makes it explicit where available."""
    # AppKit cannot wrap the synthetic window handles supplied by Qt's headless
    # platforms, which are used by smoke tests and CI. Avoid an exact "cocoa"
    # check: alternate native platform names should still receive these flags.
    if not _supports_native_macos_overlay(QApplication.platformName()):
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
    if hasattr(window, "setFloatingPanel_"):
        window.setFloatingPanel_(True)
    window.setStyleMask_(window.styleMask() | AppKit.NSWindowStyleMaskNonactivatingPanel)
    window.setIgnoresMouseEvents_(True)
    window.setHidesOnDeactivate_(False)
    window.setCanHide_(False)
    window.setLevel_(AppKit.NSScreenSaverWindowLevel)
    window.setHasShadow_(False)
    window.setCollectionBehavior_(
        _native_overlay_collection_behavior(AppKit, window.collectionBehavior())
    )
    window.orderFrontRegardless()


def _configure_macos_overlay_application() -> None:
    """Allow the overlay panel to coexist with another app's fullscreen Space."""
    if not _supports_native_macos_overlay(QApplication.platformName()):
        return
    try:
        import AppKit
    except ImportError:
        return
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)


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

    def __init__(
        self,
        app: QApplication,
        source: WindowSource,
        show_terrain: bool,
        persist_progress: bool = True,
    ) -> None:
        super().__init__()
        self.app = app
        screen = app.primaryScreen()
        self.settings = QSettings()
        self.progress_store = ProgressionStore(self.settings) if persist_progress else None
        progression = (
            self.progress_store.progression if self.progress_store is not None else Progression()
        )
        self.session = DesktopSession(
            _rect(screen.geometry()),
            _rect(screen.availableGeometry()),
            source,
            defenders=load_defenders(self.settings, progression),
            legendary_prefs=load_legendaries(self.settings, progression),
            progression=progression,
            enforce_unlocks=True,
        )
        self.overlay = DesktopOverlay(self.session, screen)
        self.defender_menu = DefenderMenu(self.session, self.settings)
        self.overlay.show_terrain = show_terrain
        if persist_progress and not self.settings.value(MENU_HINT_KEY, False, type=bool):
            self.settings.setValue(MENU_HINT_KEY, True)
            self.settings.sync()
            self.overlay.menu_hint_until = time.perf_counter() + MENU_HINT_SECONDS
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

        self.save_timer = QTimer(self)
        self.save_timer.setInterval(5000)
        if self.progress_store is not None:
            self.save_timer.timeout.connect(self.progress_store.flush)
            self.app.aboutToQuit.connect(self.progress_store.flush)

        self.hero_actions: dict[str, QAction] = {}
        self.tray = self._make_tray()
        self.defender_menu.bind_host(self)
        self.defender_menu.unlocks_changed.connect(self._sync_hero_actions)
        self.defender_menu.unlocks_changed.connect(self.overlay.sync_unlock_alert)
        self.app.installEventFilter(self)

    def start(self) -> None:
        self.overlay.show()
        self.frame_timer.start(FRAME_MS)
        self.poll_timer.start(POLL_FAST_MS)
        if self.progress_store is not None:
            self.save_timer.start()
        QTimer.singleShot(750, self._arm_activation_menu)

    # ----- controls ------------------------------------------------------------

    def _make_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("No menu bar tray available; press Ctrl+C in this terminal to quit.")
            return None
        menu = QMenu()
        apply_board(menu)
        self._action(menu, "Command Board…", self.show_defender_menu)
        menu.addSeparator()
        self.pause_action = self._action(menu, "Pause", self.set_paused, checkable=True)
        self.hide_action = self._action(menu, "Hide", self.set_hidden, checkable=True)
        self.terrain_action = self._action(
            menu, "Show terrain", self.set_show_terrain, checkable=True
        )
        self.terrain_action.setChecked(self.overlay.show_terrain)
        self.kills_action = self._action(
            menu, "Show skull counter", self.set_show_kills, checkable=True
        )
        self.kills_action.setChecked(self.overlay.show_kills)
        menu.addSeparator()
        self._action(menu, "Spawn a stickman now", lambda: self.session.spawn_at_edge())
        self._action(menu, "Next monster now", lambda: self.session.rotate())
        for variant, name in HERO_NAMES.items():
            self.hero_actions[variant] = self._action(
                menu,
                f"Spawn {name}",
                lambda _checked=False, kind=variant: self.defender_menu.spawn_hero(kind),
            )
        self._sync_hero_actions()
        menu.aboutToShow.connect(self._sync_hero_actions)
        menu.addSeparator()
        self._action(menu, "Unlocks…", self.defender_menu.show_unlocks)
        self._action(menu, "Lifetime progress…", self.defender_menu.show_progress)
        self._action(menu, "Reset lifetime progress…", self.defender_menu.reset_progress)
        menu.addSeparator()
        self._action(menu, "Quit game", self.app.quit)
        tray = QSystemTrayIcon(_goblin_icon(), self)
        tray.setToolTip("Dungeons & Desktops")
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        self._menu = menu
        return tray

    def _sync_hero_actions(self) -> None:
        for variant, action in self.hero_actions.items():
            action.setEnabled(self.session.can_spawn_hero(variant))

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
            and not self.defender_menu.progress_dialog.isVisible()
            and not self.defender_menu.unlocks_dialog.isVisible()
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
        self.overlay.sync_unlock_alert()
        self.overlay.update()

    # ----- timers --------------------------------------------------------------

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(now - self._last, MAX_FRAME_DT)
        self._last = now
        if not self.paused:
            self.session.advance(dt)
        if self.overlay.isVisible():
            self.overlay.sync_unlock_alert()
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
        if sys.platform == "darwin":
            return MacWindowSource(), False
        if sys.platform == "win32":
            return WinWindowSource(), False
        raise WindowSourceError(f"no real window source for {sys.platform}")
    except WindowSourceError as error:
        print(f"{error}\nFalling back to the screen edges only.", file=sys.stderr)
        return FakeWindowSource(), False


def run_desktop(quit_after: float | None = None, mock: bool = False) -> int:
    menu_requested = False

    def request_menu(*_args) -> None:
        nonlocal menu_requested
        menu_requested = True

    instance = None
    if not mock and quit_after is None:
        instance = acquire_desktop_instance(request_menu)
        if instance is None:
            notify_running_desktop()
            return 0
        # Unix secondary launches from older builds still send SIGUSR1.
        if hasattr(signal, "SIGUSR1"):
            signal.signal(signal.SIGUSR1, request_menu)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("Dungeons & Desktops")
    app.setApplicationName("Dungeons & Desktops")
    app.setQuitOnLastWindowClosed(False)
    _configure_macos_overlay_application()
    # Merge into the macOS app menu so Cmd+Q works without a terminal / Dock focus.
    quit_action = QAction("Quit game", app)
    quit_action.setShortcut(QKeySequence.StandardKey.Quit)
    quit_action.setMenuRole(QAction.MenuRole.QuitRole)
    quit_action.triggered.connect(app.quit)
    app.setProperty("_dnd_quit_action", quit_action)
    source, show_terrain = _window_source(app, mock)
    pet = DesktopPet(app, source, show_terrain, persist_progress=not mock)
    pet.start()

    signal.signal(signal.SIGINT, lambda *_: app.quit())

    def wake_up() -> None:
        nonlocal menu_requested
        if menu_requested:
            menu_requested = False
            pet.show_defender_menu()

    wake = QTimer()
    wake.timeout.connect(wake_up)
    wake.start(200)
    if quit_after is not None:
        QTimer.singleShot(int(quit_after * 1000), app.quit)
    code = app.exec()
    del instance
    return code
